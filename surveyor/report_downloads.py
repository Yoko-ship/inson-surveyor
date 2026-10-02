"""Short-lived, session-revocable file links for Telegram's native downloader."""

import base64
import hashlib
import hmac
import logging
import time
from datetime import UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from surveyor.api import report_file, report_for
from surveyor.auth import current_user
from surveyor.config import settings
from surveyor.db import Session, User, audit, get_db, now
from surveyor.schemas import Strict

router = APIRouter(prefix="/api")
LIFETIME = 300


class DownloadLogFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn's access tuple includes the complete request target.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, target, version, status = record.args
            if isinstance(target, str) and target.startswith("/api/report-downloads/"):
                record.args = (client, method, "/api/report-downloads/[redacted]", version, status)
        return True


class Ticket(Strict):
    session: str = Field(min_length=64, max_length=64)
    report: str = Field(min_length=36, max_length=36)
    format: Literal["pdf", "docx"]
    expires: int = Field(strict=True)


def signing_key():
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram не настроен")
    return hmac.digest(settings.telegram_bot_token.encode(), b"surveyor-report-download-v1", "sha256")


@router.post("/reports/{report_id}/export/{fmt}/download-link")
def download_link(
    report_id: str,
    fmt: Literal["pdf", "docx"],
    request: Request,
    user=Depends(current_user),
    db=Depends(get_db),
):
    report_for(db, report_id, user)
    if not settings.public_url.startswith("https://"):
        raise HTTPException(503, "Для загрузки через Telegram требуется HTTPS")
    session = request.state.session
    ticket = Ticket(
        session=session.token_hash,
        report=report_id,
        format=fmt,
        expires=min(int(time.time()) + LIFETIME, int(session.expires_at.replace(tzinfo=UTC).timestamp())),
    )
    payload = base64.urlsafe_b64encode(ticket.model_dump_json().encode()).decode().rstrip("=")
    signature = hmac.new(signing_key(), payload.encode(), hashlib.sha256).hexdigest()
    audit(db, user, "report.download_link_created", report_id, {"format": fmt})
    db.commit()
    return {
        "url": f"{settings.public_url.rstrip('/')}/api/report-downloads/{payload}.{signature}",
        "file_name": f"surveyor-{report_id}.{fmt}",
        "expires_in": max(0, ticket.expires - int(time.time())),
    }


@router.api_route("/report-downloads/{token}", methods=["GET", "HEAD"])
def download(token: str, db=Depends(get_db)):
    invalid = HTTPException(404, "Ссылка недействительна или истекла. Запросите загрузку снова.")
    if len(token) > 1024:
        raise invalid
    try:
        payload, signature = token.rsplit(".", 1)
        expected = hmac.new(signing_key(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            raise invalid
        ticket = Ticket.model_validate_json(
            base64.b64decode(payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True)
        )
    except (ValueError, UnicodeError):
        raise invalid from None
    if not int(time.time()) < ticket.expires <= int(time.time()) + LIFETIME:
        raise invalid
    session = db.get(Session, ticket.session)
    if not session or session.expires_at <= now():
        raise invalid
    user = db.get(User, session.user_id)
    if not user or not user.active or user.must_change_password:
        raise invalid
    response = report_file(report_for(db, ticket.report, user), ticket.format)
    # Telegram Web fetches the file outside the Mini App's cookie context.
    response.headers["Access-Control-Allow-Origin"] = "https://web.telegram.org"
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return response
