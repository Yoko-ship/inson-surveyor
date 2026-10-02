"""Persist AI proposals separately from human-reviewed inspection evidence."""

import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, update

from surveyor import ai_config, codex_documents
from surveyor.config import settings
from surveyor.db import Document, ImportBatch, Survey, audit, get_db, now
from surveyor.document_api import DocumentReview, apply_review
from surveyor.pilot_api import ai_user_allowed, single_request, telegram_user
from surveyor.schemas import Strict
from surveyor.services import survey_for

router = APIRouter(prefix="/api/ai-pilot/documents")


class Analyze(Strict):
    revision: int = Field(ge=1)
    config_revision: str = Field(min_length=1, max_length=64)
    cloud_consent: Literal[True]
    locale: Literal["ru", "uz", "en"] = "ru"


class Review(DocumentReview):
    review_confirmed: Literal[True]


def owned_document(db, document_id, user):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Документ не найден")
    return document, survey_for(db, document.survey_id, user, write=True)


def checked_bytes(document):
    try:
        with Path(document.path).open("rb") as file:
            data = file.read(settings.max_upload_bytes + 1)
    except OSError:
        raise HTTPException(409, "Исходный файл недоступен. Загрузите документ заново.") from None
    if not data or len(data) > settings.max_upload_bytes:
        raise HTTPException(422, "Нужен непустой файл размером до 15 МБ.")
    if hashlib.sha256(data).hexdigest() != document.sha256:
        raise HTTPException(409, "Исходный файл изменился. Загрузите документ заново.")
    return data


@router.get("/{document_id}/proposal")
def latest(document_id: str, user=Depends(telegram_user), db=Depends(get_db)):
    document, survey = owned_document(db, document_id, user)
    batch = db.scalar(
        select(ImportBatch)
        .where(
            ImportBatch.user_id == user.id,
            ImportBatch.kind == "ai_document",
            ImportBatch.consumed.is_(False),
            ImportBatch.data["document_id"].as_string() == document.id,
        )
        .order_by(ImportBatch.created_at.desc())
    )
    if not batch:
        return None
    return {
        "id": batch.id,
        **batch.data,
        "stale": batch.data["revision"] != survey.revision or batch.data["sha256"] != document.sha256,
    }


@router.post("/{document_id}/analyze")
def analyze(document_id: str, body: Analyze, user=Depends(telegram_user), db=Depends(get_db)):
    document, survey = owned_document(db, document_id, user)
    if survey.revision != body.revision:
        raise HTTPException(409, "Осмотр изменён. Обновите страницу.")
    data = checked_bytes(document)
    filename, fingerprint, survey_id = document.filename, document.sha256, survey.id
    telegram_id = user.telegram_id
    with single_request():
        config = ai_config.load()
        if body.config_revision != ai_config.digest(config):
            raise HTTPException(
                409, "Настройки ИИ изменились. Обновите страницу и подтвердите обработку снова."
            )
        # Do not hold a database transaction while the provider processes the file.
        db.commit()
        result = codex_documents.recognize_document(data, filename, locale=body.locale, config=config)
        db.expire_all()
        if not ai_user_allowed(user, ai_config.load()) or user.telegram_id != telegram_id:
            raise HTTPException(403, "Доступ к ИИ изменился. Результат не сохранён.")
        if ai_config.digest(ai_config.load()) != body.config_revision:
            raise HTTPException(409, "Настройки ИИ изменились. Повторите анализ.")
        document, survey = owned_document(db, document_id, user)
        if document.sha256 != fingerprint:
            raise HTTPException(409, "Документ изменился. Повторите анализ.")
        changed = db.execute(
            update(Survey)
            .where(Survey.id == survey_id, Survey.revision == body.revision)
            .values(revision=body.revision)
        )
        if changed.rowcount != 1:
            raise HTTPException(409, "Осмотр изменился во время анализа. Повторите анализ.")
        batch = ImportBatch(
            user_id=user.id,
            kind="ai_document",
            data=proposal_data(document, body.revision, config, result),
        )
        db.add(batch)
        db.flush()
        audit(
            db,
            user,
            "ai.document_proposed",
            document.id,
            {"proposal_id": batch.id, "config_revision": body.config_revision, "cloud_consent": True},
        )
        db.commit()
        return {"id": batch.id, **batch.data, "stale": False}


def proposal_data(document, revision, config, result):
    return {
        "document_id": document.id,
        "sha256": document.sha256,
        "revision": revision,
        "config_revision": ai_config.digest(config),
        "provider": config.provider,
        "model": getattr(config, config.provider).model or "provider_default",
        "created_at": now().isoformat() + "Z",
        "cloud_consent": True,
        "fields": result["fields"],
        "summary": result.get("summary", ""),
        "display_mode": config.display_mode,
    }


@router.post("/{document_id}/proposals/{proposal_id}/review")
def review(document_id: str, proposal_id: str, body: Review, user=Depends(telegram_user), db=Depends(get_db)):
    document, survey = owned_document(db, document_id, user)
    batch = db.get(ImportBatch, proposal_id)
    if (
        not batch
        or batch.kind != "ai_document"
        or batch.user_id != user.id
        or batch.data["document_id"] != document.id
    ):
        raise HTTPException(404, "Предложение не найдено")
    if (
        batch.consumed
        or batch.data["revision"] != body.revision
        or survey.revision != body.revision
        or batch.data["sha256"] != document.sha256
    ):
        raise HTTPException(409, "Предложение уже проверено или осмотр изменился. Повторите анализ.")
    checked_bytes(document)
    rows = {row["field"]: row for row in batch.data["fields"]}
    if body.fields.keys() - rows.keys():
        raise HTTPException(422, "Выберите только поля этого предложения")
    claimed = db.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch.id, ImportBatch.consumed.is_(False))
        .values(consumed=True)
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "Предложение уже проверено")
    result = apply_review(db, document, survey, body, user)
    decisions = []
    for key, row in rows.items():
        selected = key in body.fields
        final = document.extracted["fields"].get(key, {}).get("value")
        decisions.append(
            {
                **row,
                "decision": ("accepted" if final == row["value"] else "corrected")
                if selected
                else "rejected",
                "reviewed_value": final if selected else None,
            }
        )
    evidence = {
        "proposal_id": batch.id,
        "sha256": batch.data["sha256"],
        "provider": batch.data["provider"],
        "model": batch.data["model"],
        "config_revision": batch.data["config_revision"],
        "generated_at": batch.data["created_at"],
        "reviewed_at": now().isoformat() + "Z",
        "reviewed_by": user.id,
        "reviewer_name": user.name,
        "reason": body.reason,
        "fields": decisions,
    }
    document.extracted = {
        **document.extracted,
        "ai_reviews": [*document.extracted.get("ai_reviews", []), evidence],
    }
    audit(db, user, "ai.document_reviewed", document.id, evidence)
    db.commit()
    return {**result, "extracted": document.extracted}
