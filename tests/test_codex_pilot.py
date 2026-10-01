import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from surveyor import codex_pilot as pilot
from surveyor.config import settings
from surveyor.pilot_api import RUNNING
from surveyor.pilot_samples import FIELDS, SAMPLES, scan_png
from tests.conftest import switch_user


def readings(sample_id="text"):
    sample = SAMPLES[sample_id]
    return {
        key: {
            "value": sample["expected"][key],
            "quote": sample["text"] if sample["expected"][key] is not None else "",
        }
        for key in FIELDS
    }


@pytest.fixture
def local_admin(admin, monkeypatch):
    monkeypatch.setattr(settings, "codex_local_pilot", True)
    monkeypatch.setattr(settings, "public_url", "http://localhost")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(pilot, "connection", lambda: {"ready": True, "message": "Вход через ChatGPT найден."})
    # Reuse the isolated test DB/session while representing a real loopback client.
    with TestClient(admin.app, base_url="http://localhost", client=("127.0.0.1", 41000)) as local:
        local.cookies.set("session", admin.cookies.get("session"))
        local.headers.update(admin.headers)
        local.factory = admin.factory
        yield local


def test_pilot_role_csrf_and_strict_sample_input(local_admin, monkeypatch):
    called = []
    monkeypatch.setattr(pilot, "recognize", lambda sample_id: called.append(sample_id))
    assert local_admin.get("/api/ai-pilot").json()["ready"]
    for payload in ({"sample_id": "../../.env"}, {"sample_id": "text", "text": "private data"}):
        assert local_admin.post("/api/ai-pilot/run", json=payload).status_code == 422
    assert (
        local_admin.post(
            "/api/ai-pilot/run", json={"sample_id": "text"}, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    local_admin.cookies.clear()
    switch_user(local_admin)
    assert local_admin.get("/api/ai-pilot").status_code == 403
    assert local_admin.post("/api/ai-pilot/run", json={"sample_id": "text"}).status_code == 403
    assert called == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_mode", "real"),
        ("app_env", "production"),
        ("public_url", "https://example.trycloudflare.com"),
        ("codex_local_pilot", False),
    ],
)
def test_pilot_rejects_shared_and_real_modes(local_admin, monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    assert local_admin.get("/api/ai-pilot").status_code == 404
    assert local_admin.get("/api/ai-pilot/sample.png").status_code == 404
    assert local_admin.post("/api/ai-pilot/run", json={"sample_id": "text"}).status_code == 404


@pytest.mark.parametrize(
    "header,value",
    [
        ("X-Forwarded-For", "127.0.0.1"),
        ("Forwarded", "for=127.0.0.1"),
        ("X-Forwarded-Host", "localhost"),
        ("CF-Ray", "example"),
        ("Host", "example.com"),
    ],
)
def test_pilot_rejects_tunnel_headers(local_admin, header, value):
    assert local_admin.get("/api/ai-pilot", headers={header: value}).status_code == 404


def test_pilot_result_is_preview_and_concurrent_calls_are_rejected(local_admin, monkeypatch):
    result = {"sample_id": "text", "fields": pilot.assess("text", readings()), "saved": False}
    monkeypatch.setattr(pilot, "recognize", lambda _: result)
    response = local_admin.post("/api/ai-pilot/run", json={"sample_id": "text"})
    assert response.status_code == 200, response.text
    assert response.json()["saved"] is False
    assert all(f["matches"] and f["status"] == "needs_review" for f in response.json()["fields"])
    RUNNING.acquire()
    try:
        assert local_admin.post("/api/ai-pilot/run", json={"sample_id": "text"}).status_code == 409
    finally:
        RUNNING.release()


def test_pilot_error_unlocks_next_request(local_admin, monkeypatch):
    def fail(_):
        raise pilot.PilotError("Codex не ответил вовремя. Попробуйте позже.")

    monkeypatch.setattr(pilot, "recognize", fail)
    assert local_admin.post("/api/ai-pilot/run", json={"sample_id": "text"}).status_code == 503
    assert not RUNNING.locked()


def test_missing_values_and_percent_fraction_are_not_accepted_as_correct():
    fields = readings("missing")
    assert all(row["matches"] for row in pilot.assess("missing", fields))
    fields = readings()
    fields["declared_rate"]["value"] = "0.005"
    fields["object_value"]["quote"] = "fabricated quote"
    fields["contract_start"]["value"] = "2026-02-31"
    fields["term_days"]["value"] = "NaN"
    rows = {r["field"]: r for r in pilot.assess("text", fields)}
    for key in ("declared_rate", "object_value", "contract_start", "term_days"):
        assert not rows[key]["matches"]


def test_result_requires_successful_turn_and_complete_schema():
    message = {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(readings())}}
    success = {"type": "turn.completed"}
    assert pilot.parse_result(json.dumps(message) + "\n" + json.dumps(success)) == readings()
    for output in (
        json.dumps(message),
        "not json",
        json.dumps(success),
        "{}",
        "[]",
        json.dumps(message) + '\n{"type":"turn.failed"}',
    ):
        with pytest.raises(pilot.PilotError):
            pilot.parse_result(output)


def test_child_receives_no_app_secrets_or_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "never-forward")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "never-forward")
    assert not (
        {"OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN", "BOOTSTRAP_ADMIN_PASSWORD"}
        & pilot.child_environment().keys()
    )
    args = pilot.command(tmp_path / "codex.exe", tmp_path, "scan")
    assert "--ignore-user-config" in args and "--ephemeral" in args and "read-only" in args
    assert 'approval_policy="never"' in args and 'web_search="disabled"' in args
    assert args[-1] == "-" and str(tmp_path / "sample.png") in args


def test_timeout_terminates_process_and_redacts_stderr(monkeypatch):
    class Process:
        returncode = 0
        calls = 0
        killed = False

        def communicate(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("codex", 1)
            return "", "private diagnostic"

        def kill(self):
            self.killed = True

    process = Process()
    monkeypatch.setattr(pilot.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(pilot.PilotError) as error:
        pilot.run_process(["codex"])
    assert process.killed and "private" not in str(error.value)


def test_scan_is_rendered_image_without_text_in_prompt(monkeypatch, tmp_path):
    from io import BytesIO

    from PIL import Image

    assert Image.open(BytesIO(scan_png())).size == (1250, 1000)
    monkeypatch.setattr(pilot, "cli_path", lambda: tmp_path / "codex.exe")
    monkeypatch.setattr(pilot, "connection", lambda: {"ready": True})
    seen = []

    def fake_run(args, **kwargs):
        seen.append(kwargs["prompt"])
        assert (kwargs["cwd"] / "sample.png").is_file()
        return (
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": json.dumps(readings("scan"))},
                }
            )
            + '\n{"type":"turn.completed"}'
        )

    monkeypatch.setattr(pilot, "run_process", fake_run)
    result = pilot.recognize("scan")
    assert all(row["matches"] for row in result["fields"])
    assert "60000000" not in seen[0] and "Sample Workshop" not in seen[0]
