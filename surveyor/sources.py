"""Explicit, allowlisted public-data adapters. No arbitrary URL fetches."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

import httpx
from openpyxl.utils.exceptions import InvalidFileException
from sqlalchemy import or_, select, update

from surveyor.db import Audit, Channel, Indicator, now
from surveyor.regions import region_code
from surveyor.schemas import IndicatorInput
from surveyor.source_lock import host_lock

CBU_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/"
CHANNELS = [
    (
        "market_quotes",
        "Рыночные страховые котировки",
        "manual_only",
        "Проверенные сопоставимые котировки с типом ставки, сроком, источником и датой",
        False,
    ),
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
    identity = ("metric", "region", "class_code", "object_type", "period")
    previous = db.scalar(
        select(Indicator)
        .where(
            Indicator.channel_code == channel,
            *(Indicator.data[k].as_string() == data.get(k) for k in identity),
        )
        .order_by(Indicator.fetched_at.desc())
        .limit(1)
    )
    if (
        previous
        and {k: v for k, v in previous.data.items() if k not in {"approved_by", "approved_at"}} == data
    ):
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


def claim_collection(db, channel, force=False):
    # A temporary failure is retried by the next hourly cycle, not treated as a successful daily cache.
    seconds = (
        60
        if force
        else 3600
        if channel.error
        else channel.data.get("config", {}).get("interval_hours", 24) * 3600
    )
    attempt = now()
    claim = db.execute(
        update(Channel)
        .where(
            Channel.code == channel.code,
            Channel.enabled.is_(True),
            or_(Channel.last_attempt.is_(None), Channel.last_attempt <= attempt - timedelta(seconds=seconds)),
        )
        .values(last_attempt=attempt)
    )
    db.commit()
    return claim.rowcount == 1


def collect_cbu(db, force=False):
    channel = db.get(Channel, "cbu")
    if not channel or not channel.enabled:
        return {"status": "disabled", "channel": "cbu"}
    if not claim_collection(db, channel, force):
        return {"status": "cached"}
    try:
        with (
            host_lock("cbu.uz"),
            httpx.Client(
                timeout=20,
                follow_redirects=False,
                headers={"User-Agent": "Surveyor/0.1 (public currency data)"},
            ) as client,
        ):
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
            if not isinstance(row, dict) or not all(k in row for k in ["Ccy", "Rate", "Nominal", "Date"]):
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
    except (ValueError, KeyError, TypeError, ArithmeticError):
        db.rollback()
        channel.enabled = False
        channel.error = "Доступ отклонён или формат CBU изменился; канал отключён до проверки"
    except httpx.HTTPError:
        db.rollback()
        channel.error = "Источник недоступен; используются последние сохранённые данные"
    except OSError:
        db.rollback()
        channel.error = (
            "Не удалось получить доступ к локальному хранилищу или сети; повтор в следующем часовом цикле"
        )
    db.add(Audit(action="source.error", entity_id="cbu", data={"message": channel.error}))
    db.commit()
    return {"status": "error", "message": channel.error}


def latest_indicators(db, region=None, class_code=None):
    rows = db.scalars(select(Indicator).order_by(Indicator.fetched_at.desc())).all()
    # New uploads of older periods must never displace newer observations.
    rows.sort(key=lambda r: (r.data["observation_date"], r.fetched_at, r.id), reverse=True)
    seen, result = set(), []
    for row in rows:
        d = row.data
        key = (row.channel_code, d["metric"], d.get("region"), d.get("class_code"), d.get("object_type"))
        if key in seen:
            continue
        seen.add(key)
        if region and region_code(d.get("region", "all")) not in {"all", region_code(region)}:
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


def collect_channel(db, code, force=False):
    """A failed permission/schema check opens the circuit; only an administrator can reset it."""
    import hashlib

    from surveyor.source_adapters import AccessRefused, FormatChanged, fetch_public, parse_public

    if code == "cbu":
        return collect_cbu(db, force=force)
    channel = db.get(Channel, code)
    if not channel or not channel.enabled or not channel.data.get("config"):
        return {"status": "disabled", "channel": code}
    config = channel.data["config"]
    if not claim_collection(db, channel, force):
        return {"status": "cached", "channel": code}
    try:
        content = fetch_public(config, channel.data.get("host_channel", code))
        if config["format"] == "document":
            from surveyor.references import public_text, store_reference

            row = store_reference(
                db,
                code,
                {**config.get("reference", {}), "source_url": config["url"], "text": public_text(content)},
            )
            channel.last_success, channel.error = now(), None
            db.commit()
            return {"status": "collected", "channel": code, "reference_id": row.id, "count": 1}
        if config["format"] == "napp":
            from surveyor.napp import latest_download, parse_napp

            dataset_url = latest_download(content)
            workbook = fetch_public({**config, "url": dataset_url}, "napp")
            items, schema = parse_napp(workbook, dataset_url)
            channel.data = {**channel.data, "last_dataset_url": dataset_url}
        else:
            items, schema = parse_public(content, config)
        if not items:
            raise FormatChanged("Источник не содержит завершённых периодов")
        previous_schema = channel.data.get("schema")
        if previous_schema and previous_schema != schema:
            # SIAT appends a new annual period; classifier columns must stay identical.
            def stable(keys):
                return [k for k in keys if not re.fullmatch(r"20\d{2}(?:-Q[1-4]|-M(?:0[1-9]|1[0-2]))?", k)]

            if config["format"] != "siat" or stable(previous_schema) != stable(schema):
                raise FormatChanged("Столбцы источника изменились; проверьте схему и настройте канал заново")
        for item in items:
            store_indicator(db, code, item)
        channel.data = {
            **channel.data,
            "schema": schema,
            "last_file_sha256": hashlib.sha256(content).hexdigest(),
        }
        channel.last_success, channel.error = now(), None
        db.add(Audit(action="source.collected", entity_id=code, data={"count": len(items)}))
        db.commit()
        return {"status": "collected", "channel": code, "count": len(items)}
    except httpx.HTTPError:
        message = "Источник временно недоступен; сохранённые данные доступны с исходной датой"
    except (
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        ArithmeticError,
        BadZipFile,
        ParseError,
        InvalidFileException,
    ) as exc:
        channel.enabled = False
        # Never echo external payloads/Pydantic inputs into logs or the admin screen.
        message = (
            str(exc)
            if isinstance(exc, (AccessRefused, FormatChanged))
            else "Формат данных изменился; канал отключён до проверки"
        )
    except OSError:
        message = "Не удалось разрешить публичный адрес источника"
    channel.error = message
    db.add(Audit(action="source.error", entity_id=code, data={"message": message}))
    db.commit()
    return {"status": "error", "channel": code, "message": message}


def collect_all(db):
    codes = db.scalars(select(Channel.code).where(Channel.enabled.is_(True))).all()
    results = []
    for code in codes:
        try:
            results.append(collect_channel(db, code))
        except Exception as exc:
            # Keep one broken adapter from stopping other sources and scheduled backups.
            db.rollback()
            channel = db.get(Channel, code)
            message = "Ошибка сборщика; остальные каналы продолжают работу"
            channel.error = message
            db.add(
                Audit(
                    action="source.error",
                    entity_id=code,
                    data={"message": message, "error_type": type(exc).__name__},
                )
            )
            db.commit()
            results.append({"status": "error", "channel": code, "message": message})
    return results
