import hashlib
import hmac
import io
import json
import time
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import select

from surveyor import codex_documents, codex_pilot
from surveyor.config import settings
from surveyor.db import Audit, Document, User
from surveyor.file_lock import locked_file
from surveyor.pilot_samples import FIELDS, SAMPLES, scan_png
from tests.test_codex_pilot import readings

TOKEN = "test-bot-credential"
OWNER = "123456789"


def proof(owner=OWNER, age=0):
    fields = {"auth_date": str(int(time.time()) - age), "user": json.dumps({"id": int(owner)})}
    key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def owner(admin, monkeypatch):
    monkeypatch.setattr(settings, "codex_telegram_enabled", True)
    monkeypatch.setattr(settings, "codex_telegram_owner_id", OWNER)
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(settings, "public_url", "https://example.trycloudflare.com")
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(codex_pilot, "connection", lambda: {"ready": True, "message": "Signed in"})
    with admin.factory() as db:
        db.scalar(select(User).where(User.login == "admin")).telegram_id = OWNER
        db.commit()
    with TestClient(admin.app, base_url=settings.public_url) as c:
        c.cookies.set("session", admin.cookies.get("session"))
        c.headers.update(admin.headers)
        c.headers["X-Telegram-Init-Data"] = proof()
        c.factory = admin.factory
        yield c


def upload(client, **kwargs):
    return client.post(
        "/api/ai-pilot/analyze",
        files={"file": ("contract.txt", b"contract", "text/plain")},
        data={"cloud_consent": "true"},
        **kwargs,
    )


def test_owner_only_preview_consent_and_no_document_storage(owner, monkeypatch):
    calls = []

    def recognize(data, filename):
        calls.append((data, filename))
        return {"fields": [], "saved": False}

    monkeypatch.setattr(codex_documents, "recognize_document", recognize)
    status = owner.get("/api/ai-pilot")
    assert status.status_code == 200 and status.json()["documents_enabled"]
    assert status.json()["sample_image"].startswith("data:image/png;base64,")
    assert owner.post("/api/ai-pilot/analyze", files={"file": ("a.txt", b"abc")}).status_code == 422
    assert upload(owner).json() == {"fields": [], "saved": False}
    assert calls == [(b"contract", "contract.txt")]
    with owner.factory() as db:
        assert db.scalar(select(Document)) is None
        audit = db.scalar(select(Audit).where(Audit.action == "codex.document_preview"))
        assert audit.data == {"cloud_consent": True, "saved": False}


@pytest.mark.parametrize("header", ["", "forged", proof("987654321"), proof(age=600)])
def test_rejects_missing_forged_other_and_expired_telegram_proof(owner, monkeypatch, header):
    monkeypatch.setattr(
        codex_documents, "recognize_document", lambda *a: pytest.fail("Unauthorized inference")
    )
    assert upload(owner, headers={"X-Telegram-Init-Data": header}).status_code in {403, 422}


def test_rejects_csrf_host_unlinked_admin_and_disabled_feature(owner, monkeypatch):
    monkeypatch.setattr(
        codex_documents, "recognize_document", lambda *a: pytest.fail("Unauthorized inference")
    )
    assert upload(owner, headers={"X-CSRF-Token": "bad"}).status_code == 403
    assert upload(owner, headers={"Host": "other.example"}).status_code == 404
    with owner.factory() as db:
        db.scalar(select(User).where(User.login == "admin")).telegram_id = "987654321"
        db.commit()
    assert upload(owner).status_code == 403
    monkeypatch.setattr(settings, "codex_telegram_enabled", False)
    assert upload(owner).status_code == 404


def test_serializes_requests_across_workers(owner, monkeypatch):
    monkeypatch.setattr(codex_documents, "recognize_document", lambda *a: pytest.fail("Concurrent inference"))
    with locked_file(settings.storage_dir.parent / "codex-request.lock"):
        assert upload(owner).status_code == 409


def test_pdf_all_pages_and_input_limits(tmp_path):
    output = io.BytesIO()
    pdf = Canvas(output)
    for _ in range(2):
        pdf.drawString(20, 700, "Test contract")
        pdf.showPage()
    pdf.save()
    text, images = codex_documents.prepare(output.getvalue(), "test.pdf", tmp_path)
    assert text.count("Test contract") == 2
    assert len(images) == 2 and all(p.is_file() for p in images)
    with pytest.raises(ValueError, match="60 000"):
        codex_documents.prepare(b"a" * 60001, "test.txt", tmp_path)
    with pytest.raises(ValueError):
        codex_documents.prepare(b"", "test.txt", tmp_path)
    output = io.BytesIO()
    pdf = Canvas(output)
    for _ in range(11):
        pdf.showPage()
    pdf.save()
    with pytest.raises(ValueError, match="10"):
        codex_documents.prepare(output.getvalue(), "test.pdf", tmp_path)


def test_untrusted_values_and_image_quotes_require_review():
    fields = readings()
    fields["declared_rate"]["value"] = "Infinity"
    fields["term_days"]["value"] = "NaN"
    fields["contract_start"]["value"] = "2026-02-31"
    fields["insured_organization"]["value"] = "Person Name"
    fields["object_value"]["quote"] = "Invented quote"
    rows = {r["field"]: r for r in codex_documents.assess(fields, SAMPLES["text"]["text"], False)}
    for name in ("declared_rate", "term_days", "contract_start", "insured_organization", "object_value"):
        assert rows[name]["value"] is None and rows[name]["status"] == "rejected"
    rows = codex_documents.assess(readings(), "", True)
    assert all(r["status"] == "needs_review" and not r["quote_found_in_text"] for r in rows)


def test_document_process_receives_only_rendered_file_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_pilot, "cli_path", lambda: tmp_path / "codex")
    monkeypatch.setattr(codex_pilot, "connection", lambda: {"ready": True})
    paths = []

    def run(args, **kwargs):
        paths.append(kwargs["cwd"])
        assert args.count("--image") == 1
        assert "malicious-name" not in " ".join(args)
        assert "FICTIONAL" not in kwargs["prompt"]
        assert kwargs["timeout"] == 90
        return (
            json.dumps(
                {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(readings())}}
            )
            + '\n{"type":"turn.completed"}'
        )

    monkeypatch.setattr(codex_pilot, "run_process", run)
    result = codex_documents.recognize_document(scan_png(), "../../malicious-name.png")
    assert result["saved"] is False and len(result["fields"]) == len(FIELDS)
    assert not paths[0].exists()
