"""Guided inspections and authenticated, private durable analysis jobs."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, update

from surveyor import ai_config
from surveyor.ai_jobs import public_job
from surveyor.auth import current_user
from surveyor.db import AIJob, Survey, audit, get_db, now
from surveyor.inspection_assistant import basis_hash, documents_for, guidance
from surveyor.pilot_api import telegram_user
from surveyor.schemas import Strict
from surveyor.services import survey_for

router = APIRouter(prefix="/api")


class JobInput(Strict):
    revision: int = Field(ge=1)
    kind: Literal["document", "inspection", "photo"]
    document_ids: list[str] = Field(min_length=1, max_length=20)
    cloud_consent: Literal[True]
    config_revision: str = Field(min_length=64, max_length=64)
    locale: Literal["ru", "uz", "en"] = "ru"


class Answers(Strict):
    revision: int = Field(ge=1)
    answers: dict[str, Annotated[str, Field(max_length=2000)]] = Field(max_length=100)


class Review(Strict):
    revision: int = Field(ge=1)
    accepted: dict[str, Annotated[str, Field(min_length=1, max_length=1500)]] = Field(max_length=30)
    reason: str = Field(min_length=5, max_length=1000)
    review_confirmed: Literal[True]


def revise(db, survey, revision, assistance):
    changed = db.execute(
        update(Survey)
        .where(Survey.id == survey.id, Survey.revision == revision)
        .values(
            assistance=assistance,
            revision=revision + 1,
            status="draft",
            inputs={**survey.inputs, "manual_review_confirmed": False} if survey.inputs else {},
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Осмотр изменился. Обновите страницу.")


@router.get("/surveys/{survey_id}/guidance")
def get_guidance(survey_id: str, user=Depends(current_user), db=Depends(get_db)):
    survey = survey_for(db, survey_id, user)
    data = guidance(db, survey)
    return {
        **data,
        "reviews": [
            {
                **r,
                "stale": r["basis_hash"] != data["basis_hash"]
                or r.get("context_hash") != data["context_hash"],
            }
            for r in (survey.assistance or {}).get("reviews", [])
        ],
    }


@router.put("/surveys/{survey_id}/guidance")
def save_answers(survey_id: str, body: Answers, user=Depends(current_user), db=Depends(get_db)):
    survey = survey_for(db, survey_id, user, write=True)
    labels = {q["id"]: q["text"] for q in guidance(db, survey)["questions"]}
    allowed = set(labels)
    # Model questions are answerable, but never become system instructions.
    for job in db.scalars(
        select(AIJob).where(AIJob.survey_id == survey.id, AIJob.status.in_(["completed", "reviewed"]))
    ):
        labels.update(
            {f"ai_{job.id}_{i}": question for i, question in enumerate(job.result.get("questions", []))}
        )
        allowed.update(labels)
    if body.answers.keys() - allowed:
        raise HTTPException(422, "Неизвестный вопрос осмотра")
    answers = {**(survey.assistance or {}).get("answers", {}), **body.answers}
    revise(
        db,
        survey,
        body.revision,
        {
            **(survey.assistance or {}),
            "answers": answers,
            "question_labels": {
                **(survey.assistance or {}).get("question_labels", {}),
                **{key: labels[key] for key in body.answers},
            },
        },
    )
    audit(db, user, "inspection.answers_reviewed", survey.id, {"answers": body.answers})
    db.commit()
    return {"revision": body.revision + 1}


@router.post("/ai-pilot/surveys/{survey_id}/jobs", status_code=202)
def enqueue(survey_id: str, body: JobInput, user=Depends(telegram_user), db=Depends(get_db)):
    survey = survey_for(db, survey_id, user, write=True)
    config = ai_config.load()
    if not config.enabled or ai_config.digest(config) != body.config_revision:
        raise HTTPException(409, "Настройки ИИ изменились или ИИ приостановлен. Обновите страницу.")
    docs = {d.id: d for d in documents_for(db, survey)}
    if len(set(body.document_ids)) != len(body.document_ids) or set(body.document_ids) - docs.keys():
        raise HTTPException(422, "Выберите документы этого осмотра без повторов")
    if body.kind == "document" and len(body.document_ids) != 1:
        raise HTTPException(422, "Для извлечения полей выберите один документ")
    if body.kind == "photo":
        from pathlib import Path

        if any(
            Path(docs[key].filename).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
            for key in body.document_ids
        ):
            raise HTTPException(422, "Выберите фотографии")
    changed = db.execute(
        update(Survey)
        .where(Survey.id == survey.id, Survey.revision == body.revision)
        .values(revision=body.revision)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Осмотр изменился. Обновите страницу.")
    active = db.scalar(
        select(AIJob).where(AIJob.survey_id == survey.id, AIJob.status.in_(["queued", "running"]))
    )
    request_data = {**body.model_dump(), "telegram_id": user.telegram_id}
    if active:
        if active.user_id == user.id and active.request == request_data:
            return public_job(active)
        raise HTTPException(409, "Анализ этого осмотра уже выполняется")
    job = AIJob(user_id=user.id, survey_id=survey.id, kind=body.kind, request=request_data)
    db.add(job)
    db.flush()
    audit(
        db,
        user,
        "ai.job_queued",
        job.id,
        {
            "survey_id": survey.id,
            "kind": body.kind,
            "cloud_consent": True,
            "config_revision": body.config_revision,
        },
    )
    db.commit()
    return public_job(job)


@router.get("/ai-pilot/surveys/{survey_id}/jobs")
def jobs(survey_id: str, user=Depends(telegram_user), db=Depends(get_db)):
    survey_for(db, survey_id, user, write=True)
    return [
        public_job(j)
        for j in db.scalars(
            select(AIJob)
            .where(AIJob.survey_id == survey_id, AIJob.user_id == user.id)
            .order_by(AIJob.created_at.desc())
            .limit(30)
        )
    ]


def job_for(db, job_id, user):
    job = db.get(AIJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Задание не найдено")
    survey = survey_for(db, job.survey_id, user, write=True)
    return job, survey


@router.get("/ai-pilot/jobs/{job_id}")
def job_status(job_id: str, user=Depends(telegram_user), db=Depends(get_db)):
    job, _ = job_for(db, job_id, user)
    return public_job(job)


@router.post("/ai-pilot/jobs/{job_id}/cancel")
def cancel(job_id: str, user=Depends(telegram_user), db=Depends(get_db)):
    job, _ = job_for(db, job_id, user)
    # Running model calls cannot be recalled. Discard their eventual result.
    changed = db.execute(
        update(AIJob)
        .where(AIJob.id == job.id, AIJob.status.in_(["queued", "running"]))
        .values(status="cancelled", lease_token=None, lease_until=None, updated_at=now())
    )
    if not changed.rowcount:
        raise HTTPException(409, "Задание уже завершено")
    audit(db, user, "ai.job_cancelled", job.id)
    db.commit()
    return {"status": "cancelled"}


@router.post("/ai-pilot/jobs/{job_id}/review")
def review_job(job_id: str, body: Review, user=Depends(telegram_user), db=Depends(get_db)):
    job, survey = job_for(db, job_id, user)
    if job.status != "completed" or job.kind == "document":
        raise HTTPException(409, "Результат недоступен для этой проверки")
    fingerprint = basis_hash(survey, documents_for(db, survey))
    if (
        job.result["basis_hash"] != fingerprint
        or job.result.get("context_hash") != guidance(db, survey)["context_hash"]
    ):
        raise HTTPException(409, "Исходные данные изменились. Повторите анализ.")
    rows = {r["id"]: r for section in ("findings", "explanation") for r in job.result[section]}
    if body.accepted.keys() - rows.keys():
        raise HTTPException(422, "Неизвестное предложение")
    evidence = {
        "job_id": job.id,
        "kind": job.kind,
        "basis_hash": fingerprint,
        "context_hash": job.result["context_hash"],
        "reviewed_by": user.id,
        "reviewer_name": user.name,
        "reviewed_at": now().isoformat() + "Z",
        "reason": body.reason,
        "provider": job.result["provider"],
        "model": job.result.get("model", "provider_default"),
        "context": job.result.get("context", {}),
        "config_revision": job.result["config_revision"],
        "fields": [
            {
                **row,
                "decision": ("accepted" if body.accepted[key] == row["text"] else "corrected")
                if key in body.accepted
                else "rejected",
                "reviewed_text": body.accepted.get(key),
            }
            for key, row in rows.items()
        ],
    }
    claimed = db.execute(
        update(AIJob)
        .where(AIJob.id == job.id, AIJob.status == "completed")
        .values(status="reviewed", updated_at=now())
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "Предложения уже проверены")
    revise(
        db,
        survey,
        body.revision,
        {**(survey.assistance or {}), "reviews": [*(survey.assistance or {}).get("reviews", []), evidence]},
    )
    audit(db, user, "ai.inspection_reviewed", survey.id, evidence)
    db.commit()
    return {"revision": body.revision + 1}
