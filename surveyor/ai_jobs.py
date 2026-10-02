"""Durable, leased jobs. At-least-once inference; results are published once per lease."""

import json
import logging
import time
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update

from surveyor import ai_config, codex_documents, codex_pilot
from surveyor.config import settings
from surveyor.db import AIJob, ImportBatch, SessionLocal, Survey, User, audit, now, uid
from surveyor.inspection_ai import checked_bytes, owned_document, proposal_data
from surveyor.inspection_assistant import analyze, basis_hash, documents_for
from surveyor.pilot_api import single_request

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
LEASE_SECONDS = 180


def worker_status():
    try:
        data = json.loads((settings.storage_dir.parent / "ai-worker-status.json").read_text(encoding="utf-8"))
        return 0 <= time.time() - data["last_seen"] < LEASE_SECONDS
    except (OSError, ValueError, TypeError, KeyError):
        return False


def public_job(job):
    return {
        "id": job.id,
        "survey_id": job.survey_id,
        "kind": job.kind,
        "status": job.status,
        "attempts": job.attempts,
        "error": job.error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "available_at": job.available_at,
        "document_ids": job.request["document_ids"],
        "result": job.result if job.status in {"completed", "reviewed"} else {},
    }


def claim(db):
    clock = now()
    expired = and_(AIJob.status == "running", AIJob.lease_until < clock)
    ready = or_(and_(AIJob.status == "queued", AIJob.available_at <= clock), expired)
    db.execute(
        update(AIJob)
        .where(expired, AIJob.attempts >= MAX_ATTEMPTS)
        .values(status="failed", error="Обработка прервана. Подтвердите новый запуск.", updated_at=clock)
    )
    candidate = db.scalar(
        select(AIJob.id).where(ready, AIJob.attempts < MAX_ATTEMPTS).order_by(AIJob.created_at).limit(1)
    )
    if not candidate:
        db.commit()
        return None
    token = uid()
    changed = db.execute(
        update(AIJob)
        .where(AIJob.id == candidate, ready, AIJob.attempts < MAX_ATTEMPTS)
        .values(
            status="running",
            lease_token=token,
            lease_until=clock + timedelta(seconds=LEASE_SECONDS),
            attempts=AIJob.attempts + 1,
            updated_at=clock,
            error=None,
        )
    )
    db.commit()
    return (candidate, token) if changed.rowcount == 1 else None


def process_one(factory=SessionLocal):
    with factory() as db:
        claimed = claim(db)
    if not claimed:
        return False
    job_id, token = claimed
    result, status, error = {}, "completed", None
    try:
        with factory() as db:
            job = db.get(AIJob, job_id)
            user = db.get(User, job.user_id)
            survey = db.get(Survey, job.survey_id)
            config = ai_config.load()
            if not (
                user
                and user.active
                and user.role == "admin"
                and user.telegram_id == settings.codex_telegram_owner_id
                and settings.codex_telegram_enabled
                and survey
                and survey.owner_id == user.id
            ):
                raise HTTPException(403, "Доступ к ИИ изменился. Обработка остановлена.")
            if job.request["config_revision"] != ai_config.digest(config):
                raise HTTPException(409, "Настройки ИИ изменились. Подтвердите обработку снова.")
            if survey.revision != job.request["revision"]:
                raise HTTPException(409, "Осмотр изменился. Подтвердите новый анализ.")
            if job.kind == "document":
                document, _ = owned_document(db, job.request["document_ids"][0], user)
                data, filename, fingerprint = checked_bytes(document), document.filename, document.sha256
                db.commit()
                with single_request():
                    extracted = codex_documents.recognize_document(
                        data, filename, config=config, locale=job.request["locale"]
                    )
                db.expire_all()
                document, survey = owned_document(db, job.request["document_ids"][0], user)
                if document.sha256 != fingerprint or survey.revision != job.request["revision"]:
                    raise HTTPException(409, "Осмотр изменился. Повторите анализ.")
                result = proposal_data(document, job.request["revision"], config, extracted)

            else:
                # Snapshot objects before ending the read transaction; no model call holds a DB lock.
                with single_request():
                    result = analyze(
                        db, survey, job.request["document_ids"], job.kind, config, job.request["locale"]
                    )
                    db.rollback()
                    db.expire_all()
                    survey = db.get(Survey, job.survey_id)
                    if (
                        survey.revision != job.request["revision"]
                        or basis_hash(survey, documents_for(db, survey)) != result["basis_hash"]
                    ):
                        raise HTTPException(409, "Осмотр изменился во время анализа. Повторите анализ.")
    except HTTPException as exc:
        error = str(exc.detail)
        status = (
            "retry"
            if exc.status_code == 503 or "Другой запрос" in error
            else "stale"
            if exc.status_code == 409
            else "failed"
        )
    except codex_pilot.PilotError as exc:
        error, status = str(exc), "retry"
    except ValueError:
        error, status = "Проверьте формат файлов, лимиты и настройки ИИ.", "failed"
    except Exception as exc:
        log.error("AI job failed (%s)", type(exc).__name__)
        error, status = "Временная ошибка обработки. Повторный запуск запланирован.", "retry"
    with factory() as db:
        job = db.get(AIJob, job_id)
        if status == "retry":
            status = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
        if status == "completed" and job.kind == "document":
            batch = ImportBatch(user_id=job.user_id, kind="ai_document", data=result)
            db.add(batch)
            db.flush()
            result = {"id": batch.id, **result, "stale": False}
        changed = db.execute(
            update(AIJob)
            .where(AIJob.id == job_id, AIJob.status == "running", AIJob.lease_token == token)
            .values(
                status=status,
                result=result if status == "completed" else {},
                error=error,
                updated_at=now(),
                available_at=now() + timedelta(seconds=10 * job.attempts),
                lease_until=None,
                lease_token=None,
            )
        )
        if changed.rowcount:
            audit(db, None, "ai.job_" + status, job_id, {"attempts": job.attempts})
        else:
            db.rollback()
            return True
        db.commit()
    return True
