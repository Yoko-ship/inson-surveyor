"""Factor policy versioning and private, aggregate experience import."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy import select, update

from surveyor.auth import current_user, roles
from surveyor.db import ClassTemplate, ImportBatch, audit, get_db, now
from surveyor.factor_pricing import (
    METHOD,
    calibration_stale,
    catalogue,
    entries,
    experience_hash,
    latest_experience,
    propose,
    validate_class,
)
from surveyor.schemas import FactorPolicy, Money, Strict

router = APIRouter(prefix="/api")
manager = roles("admin", "actuary")


def template_for(db, template_id, latest=False):
    row = db.get(ClassTemplate, template_id)
    if not row:
        raise HTTPException(404, "Шаблон не найден")
    if latest:
        current = db.scalar(
            select(ClassTemplate)
            .where(ClassTemplate.class_code == row.class_code)
            .order_by(ClassTemplate.created_at.desc(), ClassTemplate.id.desc())
        )
        if current.id != row.id:
            raise HTTPException(409, "Шаблон изменился; откройте последнюю версию")
    return row


@router.get("/factor-catalogue")
def factor_catalogue(user=Depends(current_user)):
    source = catalogue()
    return {key: source[key] for key in ("id", "sha256", "entries")}


class PolicyVersion(Strict):
    policy: FactorPolicy


@router.post("/admin/templates/{template_id}/factors", status_code=201)
def save_policy(template_id: str, body: PolicyVersion, user=Depends(manager), db=Depends(get_db)):
    old = template_for(db, template_id, latest=True)
    validate_class(old.class_code, body.policy.insurance_class)
    # A manual change resets both approval and statistical provenance.
    data = {k: v for k, v in old.data.items() if k != "factor_calibration"}
    data["factor_policy"] = body.policy.model_dump(mode="json")
    row = ClassTemplate(class_code=old.class_code, data=data)
    db.add(row)
    db.flush()
    audit(db, user, "factor_policy.version_created", row.id, {"previous_id": old.id})
    db.commit()
    return {"id": row.id}


class ExperienceRow(Strict):
    factor_id: str = Field(pattern=r"^(factor_[0-9]{3}|note_[0-9]{1,2}_[0-9]{1,2})$")
    choice: Literal["raises", "lowers", "neutral"]
    year: int = Field(ge=1990, le=2100)
    exposure: Annotated[Decimal, Field(gt=0, le=Decimal("1e12"), decimal_places=4)]
    claims: int = Field(ge=0, le=1000000000)
    payments: Money


@router.get("/admin/factor-experience/template")
def import_template(user=Depends(manager)):
    return Response(
        "factor_id,choice,year,exposure,claims,payments\n",
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="factor-experience.csv"'},
    )


@router.post("/admin/templates/{template_id}/factor-experience/preview")
async def preview(template_id: str, file: UploadFile, user=Depends(manager), db=Depends(get_db)):
    from surveyor.api import upload_bytes
    from surveyor.documents import read_table

    template = template_for(db, template_id, latest=True)
    policy = template.data.get("factor_policy")
    if not policy:
        raise HTTPException(422, "Сначала сохраните факторный шаблон")
    available = {r["id"] for r in entries(policy["insurance_class"])}
    data = await upload_bytes(file)
    raw = read_table(data, file.filename or "")
    if not raw or len(raw) > 2000:
        raise HTTPException(422, "Нужны 1–2000 строк статистики")
    results, seen = [], set()
    for index, item in enumerate(raw, 2):
        try:
            row = ExperienceRow.model_validate(item)
            key = (row.factor_id, row.choice, row.year)
            if row.factor_id not in available or row.year >= date.today().year:
                raise ValueError("Фактор другого класса или незавершённый год")
            if key in seen:
                raise ValueError("Повтор фактора, сегмента и года")
            seen.add(key)
            results.append({"row": index, "data": row.model_dump(mode="json")})
        except (ValueError, ValidationError) as exc:
            results.append({"row": index, "error": str(exc)[:500]})
    batch = ImportBatch(
        user_id=user.id,
        kind="factor_experience",
        data={
            "class_code": template.class_code,
            "insurance_class": policy["insurance_class"],
            "template_id": template.id,
            "rows": results,
        },
    )
    db.add(batch)
    db.commit()
    return {"id": batch.id, "rows": results, "can_confirm": all("data" in r for r in results)}


@router.post("/admin/factor-experience/{batch_id}/confirm")
def confirm(batch_id: str, user=Depends(manager), db=Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.kind != "factor_experience" or batch.user_id != user.id:
        raise HTTPException(404, "Импорт не найден")
    if batch.consumed or batch.created_at < now() - timedelta(hours=1):
        raise HTTPException(409, "Импорт уже сохранён или устарел")
    template_for(db, batch.data["template_id"], latest=True)
    if not all("data" in r for r in batch.data["rows"]):
        raise HTTPException(422, "Исправьте ошибки перед подтверждением")
    rows = sorted(
        [r["data"] for r in batch.data["rows"]], key=lambda r: (r["factor_id"], r["choice"], r["year"])
    )
    data = {**batch.data, "rows": rows, "sha256": experience_hash(rows)}
    claim = db.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch.id, ImportBatch.consumed.is_(False))
        .values(consumed=True, data=data, created_at=now())
    )
    if claim.rowcount != 1:
        raise HTTPException(409, "Импорт уже сохранён")
    audit(db, user, "factor_experience.confirmed", batch.id, {"sha256": data["sha256"], "count": len(rows)})
    db.commit()
    return {"ok": True, "sha256": data["sha256"]}


@router.get("/admin/templates/{template_id}/factor-experience")
def experience(template_id: str, user=Depends(manager), db=Depends(get_db)):
    template = template_for(db, template_id)
    batch = latest_experience(db, template.class_code)
    return {
        "batch": {"id": batch.id, **batch.data} if batch else None,
        "stale": calibration_stale(db, template.data),
        "calibration": template.data.get("factor_calibration"),
    }


class CalibrationRequest(Strict):
    batch_id: str = Field(max_length=36)
    minimum_exposure: Annotated[Decimal, Field(gt=0, le=Decimal("1e12"))]
    max_change: Annotated[Decimal, Field(gt=0, le=Decimal("0.9"))]
    rationale: str = Field(min_length=10, max_length=3000)
    method_confirmed: Literal[True]


@router.post("/admin/templates/{template_id}/factor-calibration", status_code=201)
def recalibrate(
    template_id: str, body: CalibrationRequest, user=Depends(roles("actuary")), db=Depends(get_db)
):
    template = template_for(db, template_id, latest=True)
    policy = template.data.get("factor_policy")
    batch = latest_experience(db, template.class_code)
    if (
        not policy
        or not batch
        or batch.id != body.batch_id
        or batch.data["insurance_class"] != policy["insurance_class"]
    ):
        raise HTTPException(409, "Выберите актуальную статистику для этого класса")
    proposed, estimates = propose(policy, batch.data["rows"], body.minimum_exposure, body.max_change)
    proposed["rationale"] = body.rationale
    # Re-validate bounds/directions after decimal rounding.
    proposed = FactorPolicy.model_validate(proposed).model_dump(mode="json")
    calibration = {
        "method": METHOD,
        "data_id": batch.id,
        "data_sha256": batch.data["sha256"],
        "minimum_exposure": str(body.minimum_exposure),
        "max_change": str(body.max_change),
        "rationale": body.rationale,
        "estimates": estimates,
        "rows": batch.data["rows"],
        "proposed_by": user.id,
        "proposed_at": now().isoformat(),
    }
    row = ClassTemplate(
        class_code=template.class_code,
        data={**template.data, "factor_policy": proposed, "factor_calibration": calibration},
    )
    db.add(row)
    db.flush()
    audit(db, user, "factor_calibration.proposed", row.id, {"previous_id": template.id, "batch_id": batch.id})
    db.commit()
    return {"id": row.id, "policy": proposed, "calibration": calibration}
