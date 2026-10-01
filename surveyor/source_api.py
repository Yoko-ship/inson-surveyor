"""Source administration, file fallback, permission review and operational visibility."""

import csv
import hashlib
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import Field
from sqlalchemy import select, update

from surveyor.api import manager, upload_bytes
from surveyor.auth import roles
from surveyor.db import Audit, Channel, ImportBatch, audit, get_db, now
from surveyor.documents import read_table
from surveyor.market import MarketQuoteInput
from surveyor.regions import REGIONS
from surveyor.schemas import IndicatorInput, ReferenceInput, Strict
from surveyor.source_adapters import SourceConfig, checked_url
from surveyor.sources import collect_channel, store_indicator

router = APIRouter(prefix="/api")
admin = roles("admin")


@router.get("/admin/source-coverage")
def coverage(user=Depends(manager), db=Depends(get_db)):
    from surveyor.source_coverage import source_coverage

    return source_coverage(db)


@router.post("/admin/market-quotes", status_code=201)
def market_quote(body: MarketQuoteInput, user=Depends(manager), db=Depends(get_db)):
    channel_for(db, "market_quotes")
    row = store_indicator(db, "market_quotes", body.indicator(), user)
    audit(db, user, "market_quote.created", row.id, {"class_code": body.class_code})
    db.commit()
    return {"id": row.id, "annual_market_rate": row.data["annual_market_rate"]}


@router.get("/regions")
def regions():
    return [{"code": c, "ru": ru, "uz": uz, "en": en} for c, ru, uz, en in REGIONS]


def channel_for(db, code):
    channel = db.get(Channel, code)
    if not channel:
        raise HTTPException(404, "Канал не найден")
    return channel


@router.put("/admin/sources/{code}/config")
def configure(code: str, body: SourceConfig, user=Depends(admin), db=Depends(get_db)):
    row = channel_for(db, code)
    checked_url(body.url, row.data.get("host_channel", code), resolve=False)
    before = row.data
    row.data = {
        **row.data,
        "config": body.model_dump(mode="json"),
        "schema": None,
        "review_status": "connect",
        "reviewed_on": now().date().isoformat(),
        "reviewed_by": user.id,
    }
    row.enabled, row.error = True, None
    audit(db, user, "source.configured", code, {"before": before, "after": row.data})
    db.commit()
    return {"ok": True}


class ChannelState(Strict):
    enabled: bool
    reason: str = Field(min_length=10, max_length=1000)


@router.patch("/admin/sources/{code}")
def toggle(code: str, body: ChannelState, user=Depends(admin), db=Depends(get_db)):
    row = channel_for(db, code)
    if body.enabled and code != "cbu" and not row.data.get("config"):
        raise HTTPException(422, "Сначала настройте разрешённый адрес и формат канала")
    row.enabled = body.enabled
    if body.enabled:
        row.error = None
    audit(db, user, "source.enabled" if body.enabled else "source.disabled", code, {"reason": body.reason})
    db.commit()
    return {"ok": True}


@router.post("/admin/sources/{code}/collect")
def collect(code: str, user=Depends(manager), db=Depends(get_db)):
    channel_for(db, code)
    return collect_channel(db, code, force=True)


@router.get("/admin/sources/import-template")
def import_template(user=Depends(manager)):
    out = io.StringIO()
    csv.writer(out).writerow(list(IndicatorInput.model_fields))
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="indicators.csv"'},
    )


@router.post("/admin/sources/{code}/imports/preview")
async def preview(code: str, file: UploadFile, user=Depends(manager), db=Depends(get_db)):
    channel_for(db, code)
    content = await upload_bytes(file)
    rows, seen = [], set()
    for index, raw in enumerate(read_table(content, file.filename or ""), 2):
        try:
            if "observation_date" in raw:
                raw["observation_date"] = str(raw["observation_date"])[:10]
            item = IndicatorInput.model_validate(raw)
            key = (item.metric, item.region, item.class_code, item.object_type, item.period)
            if key in seen:
                raise ValueError("Повторяющийся показатель в файле")
            seen.add(key)
            rows.append({"row": index, "action": "add", "data": item.model_dump(mode="json")})
        except ValueError:
            rows.append(
                {
                    "row": index,
                    "action": "error",
                    "error": "Проверьте столбцы, дату, числа и уникальность показателя",
                }
            )
    batch = ImportBatch(
        user_id=user.id,
        kind="indicators",
        data={
            "channel": code,
            "rows": rows,
            "filename": file.filename,
            "sha256": hashlib.sha256(content).hexdigest(),
        },
    )
    db.add(batch)
    db.commit()
    return {"id": batch.id, "rows": rows, "can_confirm": all(r["action"] != "error" for r in rows)}


@router.post("/admin/source-imports/{batch_id}/confirm")
def confirm(batch_id: str, user=Depends(manager), db=Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.user_id != user.id or batch.kind != "indicators":
        raise HTTPException(404, "Импорт не найден")
    if batch.consumed or batch.created_at < now() - timedelta(hours=1):
        raise HTTPException(409, "Импорт уже сохранён или устарел")
    if any(r["action"] == "error" for r in batch.data["rows"]):
        raise HTTPException(422, "Исправьте ошибки файла")
    changed = db.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch_id, ImportBatch.consumed.is_(False))
        .values(consumed=True)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Импорт уже сохранён")
    for row in batch.data["rows"]:
        store_indicator(db, batch.data["channel"], IndicatorInput.model_validate(row["data"]), user)
    audit(db, user, "source.imported", batch_id, {k: v for k, v in batch.data.items() if k != "rows"})
    db.commit()
    return {"ok": True, "count": len(batch.data["rows"])}


@router.get("/admin/operations")
def operations(user=Depends(admin), db=Depends(get_db)):
    from pathlib import Path

    from surveyor.config import settings

    channels = db.scalars(select(Channel)).all()
    errors = db.scalars(
        select(Audit)
        .where(Audit.action.in_(["source.error", "backup.failed", "reference.changed", "worker.failed"]))
        .order_by(Audit.created_at.desc())
        .limit(30)
    ).all()
    backups = sorted(Path(settings.backup_dir).glob("*/manifest.json"), reverse=True)
    return {
        "data_mode": settings.data_mode,
        "ai_enabled": False,
        "channels": [
            {"code": c.code, "enabled": c.enabled, "last_success": c.last_success, "error": c.error}
            for c in channels
        ],
        "alerts": [
            {
                "id": e.id,
                "channel": e.entity_id,
                "message": e.data.get("message") or e.data.get("title"),
                "date": e.created_at,
            }
            for e in errors
        ],
        "backups": [{"name": p.parent.name} for p in backups[:10]],
        "worker": [
            {"action": e.action, "date": e.created_at}
            for e in db.scalars(
                select(Audit)
                .where(Audit.action == "worker.heartbeat")
                .order_by(Audit.created_at.desc())
                .limit(1)
            ).all()
        ],
    }


@router.post("/admin/sources/{code}/references", status_code=201)
def add_reference(code: str, body: ReferenceInput, user=Depends(manager), db=Depends(get_db)):
    from surveyor.references import reference_view, store_reference

    channel_for(db, code)
    row = store_reference(db, code, body.model_dump(mode="json"), user)
    db.commit()
    return reference_view(row)


@router.get("/admin/sources/{code}/references/history")
def reference_history(code: str, user=Depends(manager), db=Depends(get_db)):
    from surveyor.db import PublicReference
    from surveyor.references import reference_view

    channel_for(db, code)
    return [
        reference_view(r)
        for r in db.scalars(
            select(PublicReference)
            .where(PublicReference.channel_code == code)
            .order_by(PublicReference.fetched_at.desc())
            .limit(200)
        ).all()
    ]


@router.post("/admin/source-files/read")
async def read_public_file(file: UploadFile, user=Depends(manager)):
    from surveyor.documents import extract_text

    content = await upload_bytes(file)
    text, pages = extract_text(content, file.filename or "")
    if len(text) > 50000:
        raise HTTPException(422, "Сократите документ до 50 000 символов")
    return {
        "text": text,
        "pages": pages,
        "sha256": hashlib.sha256(content).hexdigest(),
        "manual": not bool(text.strip()),
    }
