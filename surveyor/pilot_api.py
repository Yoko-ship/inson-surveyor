"""Local admin samples and code-configured access to the server's AI connection."""

import base64
import threading
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile

from surveyor import ai_config, ai_providers, codex_pilot
from surveyor.auth import current_user, validate_telegram
from surveyor.config import settings
from surveyor.db import audit, get_db
from surveyor.file_lock import locked_file
from surveyor.pilot_samples import SAMPLES, scan_png
from surveyor.schemas import Strict

router = APIRouter(prefix="/api/ai-pilot", dependencies=[Depends(current_user)])
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


def ai_user_allowed(user, config):
    """Shared by HTTP admission and durable workers; never grants document access."""
    if not (
        user
        and user.active
        and not user.must_change_password
        and user.role in {"employee", "underwriter", "actuary", "admin"}
        and user.telegram_id
        and user.telegram_id.isdecimal()
        and int(user.telegram_id) > 0
    ):
        return False
    return config.telegram_access == "linked_users" or (
        user.role == "admin" and user.telegram_id == settings.codex_telegram_owner_id
    )


def telegram_user(request: Request, user=Depends(current_user)):
    if not telegram_enabled() or request.url.hostname != urlsplit(settings.public_url).hostname:
        raise HTTPException(404, "Подключение ИИ недоступно.")
    proof = request.headers.get("x-telegram-init-data", "")
    if not proof or len(proof) > 10000:
        raise HTTPException(403, "Откройте Mini App заново в своём Telegram.")
    telegram_id = validate_telegram(proof, settings.telegram_bot_token)
    if user.telegram_id != telegram_id or not ai_user_allowed(user, ai_config.load()):
        raise HTTPException(403, "Для ИИ нужна разрешённая учётная запись, связанная с вашим Telegram.")
    return user


def access(request: Request, user=Depends(current_user)):
    if telegram_enabled():
        return telegram_user(request, user)
    if user.role != "admin":
        raise HTTPException(403, "Локальный пилот доступен только администратору.")
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
    from surveyor.ai_jobs import worker_status

    config = ai_config.load()
    return {
        **ai_providers.connection(config),
        "provider": config.provider,
        "provider_label": ai_providers.PROVIDERS[config.provider].label,
        "config_revision": ai_config.digest(config),
        "limits": config.limits.model_dump(),
        "display_mode": config.display_mode,
        "telegram_access": config.telegram_access,
        "documents_enabled": telegram_enabled(),
        "jobs_ready": worker_status(),
        "sample_image": "data:image/png;base64," + base64.b64encode(scan_png()).decode("ascii"),
        "samples": [
            {"id": key, "title": sample["title"], "text": sample["text"]} for key, sample in SAMPLES.items()
        ],
    }


@router.get("/sample.png", dependencies=[Depends(access)])
def sample_image():
    return Response(scan_png(), media_type="image/png")


@router.post("/run", dependencies=[Depends(access)])
def run(body: PilotInput, user=Depends(current_user), db=Depends(get_db)):
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
    config_revision: str = Form(...),
    locale: Literal["ru", "uz", "en"] = Form("ru"),
    user=Depends(telegram_user),
    db=Depends(get_db),
):
    if not cloud_consent:
        raise HTTPException(422, "Подтвердите обработку файла выбранным провайдером ИИ.")
    data = file.file.read(settings.max_upload_bytes + 1)
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(422, "Нужен непустой файл размером до 15 МБ.")
    from surveyor.codex_documents import recognize_document

    telegram_id = user.telegram_id
    with single_request():
        config = ai_config.load()
        if config_revision != ai_config.digest(config):
            raise HTTPException(
                409, "Настройки ИИ изменились. Обновите страницу и подтвердите обработку снова."
            )
        result = recognize_document(data, file.filename or "document", locale=locale, config=config)
        db.refresh(user)
        if not ai_user_allowed(user, ai_config.load()) or user.telegram_id != telegram_id:
            raise HTTPException(403, "Доступ к ИИ изменился. Результат не опубликован.")
        if ai_config.digest(ai_config.load()) != config_revision:
            raise HTTPException(409, "Настройки ИИ изменились. Повторите анализ.")
        audit(
            db,
            user,
            "codex.document_preview",
            user.id,
            {
                "cloud_consent": True,
                "saved": False,
                "config_revision": result.get("config_revision"),
                "provider": result.get("provider"),
            },
        )
        db.commit()
        return result
