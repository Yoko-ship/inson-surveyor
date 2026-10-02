"""Local samples and an explicitly enabled, Telegram-owner-only Codex connection."""

import base64
import threading
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile

from surveyor import codex_pilot
from surveyor.auth import roles, validate_telegram
from surveyor.config import settings
from surveyor.db import audit, get_db
from surveyor.file_lock import locked_file
from surveyor.pilot_samples import SAMPLES, scan_png
from surveyor.schemas import Strict

router = APIRouter(prefix="/api/ai-pilot", dependencies=[Depends(roles("admin"))])
RUNNING = threading.Lock()
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def enabled():
    return (
        settings.codex_local_pilot
        and settings.app_env == "development"
        and settings.data_mode == "synthetic"
        and urlsplit(settings.public_url).hostname in LOOPBACK
    )


def local_only(request: Request):
    if (
        not enabled()
        or not request.client
        or request.client.host not in LOOPBACK
        or request.url.hostname not in LOOPBACK
        or any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host", "cf-ray"))
    ):
        raise HTTPException(404, "Локальный пилот Codex недоступен.")


def telegram_enabled():
    return bool(
        settings.codex_telegram_enabled
        and settings.codex_telegram_owner_id.isdecimal()
        and int(settings.codex_telegram_owner_id) > 0
        and settings.telegram_bot_token
        and settings.public_url.startswith("https://")
        and settings.cookie_secure
    )


def telegram_owner(request: Request, user=Depends(roles("admin"))):
    if not telegram_enabled() or request.url.hostname != urlsplit(settings.public_url).hostname:
        raise HTTPException(404, "Личное подключение Codex недоступно.")
    proof = request.headers.get("x-telegram-init-data", "")
    if not proof or len(proof) > 10000:
        raise HTTPException(403, "Откройте Mini App заново в своём Telegram.")
    telegram_id = validate_telegram(proof, settings.telegram_bot_token)
    if telegram_id != settings.codex_telegram_owner_id or user.telegram_id != telegram_id:
        raise HTTPException(403, "Codex доступен только владельцу подписки.")
    return user


def access(request: Request, user=Depends(roles("admin"))):
    if telegram_enabled():
        return telegram_owner(request, user)
    local_only(request)
    return user


@contextmanager
def single_request():
    if not RUNNING.acquire(blocking=False):
        raise HTTPException(409, "Другой запрос Codex уже выполняется. Дождитесь результата.")
    try:
        # Also serializes separate local/tunnel workers sharing this storage directory.
        with locked_file(settings.storage_dir.parent / "codex-request.lock", blocking=False):
            yield
    except BlockingIOError:
        raise HTTPException(409, "Другой запрос Codex уже выполняется. Дождитесь результата.") from None
    except codex_pilot.PilotError as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        RUNNING.release()


class PilotInput(Strict):
    sample_id: Literal["text", "scan", "missing"]


@router.get("", dependencies=[Depends(access)])
def status():
    return {
        **codex_pilot.connection(),
        "documents_enabled": telegram_enabled(),
        "sample_image": "data:image/png;base64," + base64.b64encode(scan_png()).decode("ascii"),
        "samples": [
            {"id": key, "title": sample["title"], "text": sample["text"]} for key, sample in SAMPLES.items()
        ],
    }


@router.get("/sample.png", dependencies=[Depends(access)])
def sample_image():
    return Response(scan_png(), media_type="image/png")


@router.post("/run", dependencies=[Depends(access)])
def run(body: PilotInput, user=Depends(roles("admin")), db=Depends(get_db)):
    with single_request():
        result = codex_pilot.recognize(body.sample_id)
        audit(
            db,
            user,
            "codex.pilot",
            body.sample_id,
            {
                "synthetic_only": True,
                "matched_fields": sum(f["matches"] for f in result["fields"]),
                "total_fields": len(result["fields"]),
            },
        )
        db.commit()
        return result


@router.post("/analyze")
def analyze(
    file: UploadFile,
    cloud_consent: bool = Form(False),
    user=Depends(telegram_owner),
    db=Depends(get_db),
):
    if not cloud_consent:
        raise HTTPException(422, "Подтвердите отправку выбранного файла в OpenAI.")
    data = file.file.read(settings.max_upload_bytes + 1)
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(422, "Нужен непустой файл размером до 15 МБ.")
    from surveyor.codex_documents import recognize_document

    with single_request():
        result = recognize_document(data, file.filename or "document")
        audit(db, user, "codex.document_preview", user.id, {"cloud_consent": True, "saved": False})
        db.commit()
        return result
