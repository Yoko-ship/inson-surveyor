"""Human review of scanned and rule-extracted documents, preserving the original reading."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import update

from surveyor.auth import current_user
from surveyor.db import Document, Survey, audit, get_db
from surveyor.document_values import derive_document_term, document_number
from surveyor.schemas import Strict
from surveyor.services import survey_for

router = APIRouter(prefix="/api")
NUMERIC = {"insured_sum", "object_value", "declared_rate", "declared_premium", "term_days"}
TEXT = {
    "object_description",
    "insured_organization",
    "insurer_organization",
    "contract_start",
    "contract_end",
}


class DocumentReview(Strict):
    revision: int = Field(ge=1)
    kind: Literal["photo", "contract", "branch_request", "report", "document"]
    fields: dict[str, str | None] = Field(max_length=15)
    reason: str = Field(min_length=5, max_length=1000)


@router.put("/documents/{document_id}/review")
def review_document(document_id: str, body: DocumentReview, user=Depends(current_user), db=Depends(get_db)):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(404, "Документ не найден")
    survey = survey_for(db, document.survey_id, user, write=True)
    fields = dict(document.extracted.get("fields", {}))
    for field, value in body.fields.items():
        if field not in NUMERIC | TEXT:
            raise HTTPException(422, "Неизвестное поле документа")
        if value is not None:
            value = value.strip()
            if len(value) > 2000:
                raise HTTPException(422, "Значение слишком длинное")
            if not value:
                value = None
        if value is not None and field in NUMERIC:
            try:
                if not re.fullmatch(r"[0-9][0-9 ,.\u00a0\u202f]*", value):
                    raise ValueError()
                parsed = document_number(value, field)
                if parsed is None:
                    raise ValueError()
                amount = Decimal(parsed)
                if not amount.is_finite() or not 0 <= amount <= Decimal("1e18"):
                    raise ValueError()
                if field == "declared_rate" and amount > 100:
                    raise ValueError()
                if field == "term_days" and (amount != int(amount) or not 1 <= amount <= 36500):
                    raise ValueError()
                value = str(amount)
            except (InvalidOperation, ValueError):
                raise HTTPException(422, "Проверьте числовое значение") from None
        if value and field.startswith("contract_"):
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, "Дата должна быть YYYY-MM-DD") from None
        if (
            value
            and field.endswith("organization")
            and not re.search(r"\b(?:ООО|АО|ОАО|ЗАО|МЧЖ|АЖ|MChJ|AJ|LLC|JSC)\b", value, re.I)
        ):
            raise HTTPException(
                422, "Укажите организацию с организационно-правовой формой; физлица не извлекаются"
            )
        original = fields.get(field, {})
        fields[field] = {
            **original,
            "original": original.get("original", original.get("value")),
            "value": value,
            "status": "manual" if value is not None else "blank",
            "source": document.filename,
            "reviewed_by": user.id,
            "review_reason": body.reason,
        }
        if field == "term_days":
            fields[field].pop("derived_from", None)
    derive_document_term(fields, document.filename)
    changed = db.execute(
        update(Survey)
        .where(Survey.id == survey.id, Survey.revision == body.revision)
        .values(
            revision=body.revision + 1,
            status="draft",
            inputs={**survey.inputs, "manual_review_confirmed": False} if survey.inputs else {},
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Осмотр изменён в другой вкладке. Обновите страницу")
    before = document.extracted
    document.extracted = {
        **before,
        "original_kind": before.get("original_kind", before["kind"]),
        "kind": body.kind,
        "fields": fields,
        "reviewed_by": user.id,
    }
    audit(
        db,
        user,
        "document.reviewed",
        document.id,
        {"before": before, "after": document.extracted, "reason": body.reason},
    )
    db.commit()
    return {"revision": body.revision + 1, "extracted": document.extracted}
