"""Explicit, allowlisted public-data adapters. No arbitrary URL fetches."""

from datetime import date, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select

from surveyor.db import Audit, Channel, Indicator, now
from surveyor.schemas import IndicatorInput

CBU_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/"
CHANNELS = [
    ("cbu", "cbu.uz", "official_api", "Официальный JSON API", True),
    ("stat", "stat.uz / siat.stat.uz", "manual", "Открытые файлы; схема набора требует проверки", False),
    ("egov", "data.egov.uz", "manual", "Открытые файлы; выберите набор", False),
    ("napp", "napp.uz", "manual", "Отчёты рынка: загрузка нормализованных показателей", False),
    ("lex", "lex.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("avtoelon", "avtoelon.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("seismos", "seismos.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("weather", "hydromet.uz / meteo.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("auction", "e-auksion.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("exchange", "uzex.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("construction", "mc.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("new_cars", "uzavtosanoat.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("customs", "customs.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("licenses", "license.gov.uz", "review_required", "Нужна проверка разрешения и формата", False),
    ("court", "public.sud.uz", "review_required", "Нужна проверка разрешения и формата", False),
    (
        "listings",
        "OLX / uybor.uz / joymee.uz",
        "manual_only",
        "Только файлы и снимки экрана сотрудника",
        False,
    ),
    ("credit", "Кредитное бюро", "contract_required", "Только по договору; ручной отчёт", False),
    ("registries", "Кадастр / транспорт / организации", "contract_required", "Только по договору", False),
]


def store_indicator(db, channel, item, actor=None):
    data = item.model_dump(mode="json") if isinstance(item, IndicatorInput) else item
    rows = db.scalars(
        select(Indicator).where(Indicator.channel_code == channel).order_by(Indicator.fetched_at.desc())
    ).all()
    identity = ("metric", "region", "class_code", "object_type", "period")
    previous = next((r for r in rows if all(r.data.get(k) == data.get(k) for k in identity)), None)
    if previous and {k: v for k, v in previous.data.items() if k != "approved_by"} == data:
        return previous
    row = Indicator(channel_code=channel, data=data)
    db.add(row)
    db.flush()
    db.add(
        Audit(
            user_id=actor.id if actor else None,
            action="indicator.version",
            entity_id=row.id,
            data={"previous_id": previous.id if previous else None},
        )
    )
    return row


def collect_cbu(db, force=False):
    channel = db.get(Channel, "cbu")
    if not channel or not channel.enabled:
        raise ValueError("Канал отключён; проверьте причину в панели источников")
    if channel.last_attempt and (now() - channel.last_attempt).total_seconds() < (1 if force else 86400):
        return {"status": "cached"}
    channel.last_attempt = now()
    db.commit()
    try:
        with httpx.Client(
            timeout=20, follow_redirects=False, headers={"User-Agent": "Surveyor/0.1 (public currency data)"}
        ) as client:
            response = client.get(CBU_URL)
        if response.status_code in {401, 403, 429}:
            channel.enabled = False
            raise ValueError("Источник отказал в доступе; автоматический канал отключён, повторов нет")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError("Формат CBU изменился: ожидается непустой список")
        parsed = []
        for row in payload:
            if not all(k in row for k in ["Ccy", "Rate", "Nominal", "Date"]):
                raise ValueError("Формат CBU изменился: отсутствуют обязательные поля")
            parsed.append(
                IndicatorInput(
                    metric=f"fx_{row['Ccy']}",
                    period=row["Date"],
                    value=Decimal(row["Rate"]) / Decimal(row["Nominal"]),
                    unit="UZS",
                    source_url=CBU_URL,
                    observation_date=datetime.strptime(row["Date"], "%d.%m.%Y").date(),
                    stale_days=7,
                )
            )
        for item in parsed:
            store_indicator(db, "cbu", item)
        channel.error = None
        channel.last_success = now()
        db.commit()
        return {"status": "collected", "count": len(parsed)}
    except (ValueError, KeyError, ArithmeticError) as exc:
        channel.enabled = False
        channel.error = str(exc)[:500]
    except httpx.HTTPError:
        channel.error = "Источник недоступен; используются последние сохранённые данные"
    db.add(Audit(action="source.error", entity_id="cbu", data={"message": channel.error}))
    db.commit()
    return {"status": "error", "message": channel.error}


def latest_indicators(db, region=None, class_code=None):
    rows = db.scalars(select(Indicator).order_by(Indicator.fetched_at.desc())).all()
    seen, result = set(), []
    for row in rows:
        d = row.data
        key = (row.channel_code, d["metric"], d.get("region"), d.get("class_code"), d.get("object_type"))
        if key in seen:
            continue
        seen.add(key)
        if region and d.get("region", "all") not in {"all", region}:
            continue
        if class_code and d.get("class_code", "all") not in {"all", class_code}:
            continue
        age = (date.today() - date.fromisoformat(d["observation_date"])).days
        result.append(
            {
                **d,
                "id": row.id,
                "channel": row.channel_code,
                "fetched_at": row.fetched_at.isoformat(),
                "stale": age > d["stale_days"],
            }
        )
    return result
