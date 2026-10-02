import base64
import json
import logging
from datetime import timedelta
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select

from surveyor import report_downloads
from surveyor.config import settings
from surveyor.db import Session, Survey, User, now
from tests.conftest import switch_user
from tests.test_workflows import body, survey


@pytest.fixture
def report(admin, monkeypatch):
    sid = survey(admin)
    assert admin.put(f"/api/surveys/{sid}", json=body()).status_code == 200
    rid = admin.post(f"/api/surveys/{sid}/reports").json()["id"]
    monkeypatch.setattr(settings, "public_url", "https://surveyor.example.test")
    monkeypatch.setattr(settings, "telegram_bot_token", "fictional-download-signing-key")
    return admin, rid, sid


def issue(report, fmt="pdf"):
    client, rid, _ = report
    response = client.post(f"/api/reports/{rid}/export/{fmt}/download-link")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["file_name"] == f"surveyor-{rid}.{fmt}"
    assert 0 < data["expires_in"] <= 300
    return urlsplit(data["url"]).path


@pytest.mark.parametrize("fmt,magic", [("pdf", b"%PDF"), ("docx", b"PK")])
def test_telegram_download_without_cookies_and_with_head(report, fmt, magic):
    client = report[0]
    path = issue(report, fmt)
    client.cookies.clear()
    assert client.head(path).status_code == 200
    response = client.get(path, headers={"Origin": "https://web.telegram.org"})
    assert response.status_code == 200
    assert response.content.startswith(magic)
    assert response.headers["access-control-allow-origin"] == "https://web.telegram.org"
    assert response.headers["content-disposition"].endswith(f'.{fmt}"')
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert client.get(f"/api/reports/{report[1]}/export/{fmt}").status_code == 401


def test_download_ticket_cannot_change_report_or_format(report):
    client = report[0]
    path = issue(report)
    payload, signature = path.rsplit("/", 1)[1].split(".")
    original = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    client.cookies.clear()
    for key, value in [("format", "docx"), ("report", "0" * 36), ("expires", original["expires"] + 600)]:
        changed = base64.urlsafe_b64encode(json.dumps({**original, key: value}).encode()).decode().rstrip("=")
        assert client.get(f"/api/report-downloads/{changed}.{signature}").status_code == 404
    for malformed in ["invalid", "a.b", payload + ".подпись", "x" * 1025]:
        assert client.get(f"/api/report-downloads/{malformed}").status_code == 404


def test_download_ticket_expiry_and_key_rotation(report, monkeypatch):
    client = report[0]
    path = issue(report)
    client.cookies.clear()
    future = report_downloads.time.time() + 301
    with monkeypatch.context() as patch:
        patch.setattr(report_downloads.time, "time", lambda: future)
        assert client.get(path).status_code == 404
    monkeypatch.setattr(settings, "telegram_bot_token", "rotated-fictional-key")
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(
    "change", ["logout", "expired_session", "disabled_user", "password_reset", "access_removed"]
)
def test_download_ticket_rechecks_session_and_access(report, change):
    client = report[0]
    path = issue(report)
    if change == "logout":
        assert client.post("/api/auth/logout").status_code == 200
    else:
        with client.factory() as db:
            session = db.scalar(select(Session))
            user = db.get(User, session.user_id)
            if change == "expired_session":
                session.expires_at = now() - timedelta(seconds=1)
            elif change == "disabled_user":
                user.active = False
            elif change == "password_reset":
                user.must_change_password = True
            else:
                other = User(
                    login="other", phone="000", name="Other", password_hash="unused", role="employee"
                )
                db.add(other)
                db.flush()
                user.role = "employee"
                db.get(Survey, report[2]).owner_id = other.id
            db.commit()
    client.cookies.clear()
    assert client.get(path).status_code == 404


def test_download_link_requires_csrf_and_report_access(report):
    client, rid, _ = report
    endpoint = f"/api/reports/{rid}/export/pdf/download-link"
    assert client.post(endpoint, headers={"X-CSRF-Token": "invalid"}).status_code == 403
    switch_user(client)
    assert client.post(endpoint).status_code == 404
    client.cookies.clear()
    assert client.post(endpoint).status_code == 401


def test_access_log_redacts_download_capability():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", "/api/report-downloads/private-ticket?anything=secret", "1.1", 200),
        None,
    )
    assert report_downloads.DownloadLogFilter().filter(record)
    assert "private-ticket" not in record.getMessage()
    assert "secret" not in record.getMessage()
    assert "/api/report-downloads/[redacted]" in record.getMessage()
