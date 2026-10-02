"""Portable public statistics; build fresh files so deleted private SQLite pages never leak."""

import hashlib
import json
import re
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DBSession

from surveyor.db import Base, Channel, Indicator, now
from surveyor.schemas import IndicatorInput
from surveyor.source_adapters import SIAT_DATASETS

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "database" / "public-data.sqlite"
SIAT = {code: (dataset, metric) for code, dataset, metric, _, _ in SIAT_DATASETS}
NAPP_METRICS = {
    "company_premiums",
    "company_payments",
    "claims_received",
    "claims_paid",
    "claims_refused",
    "claims_unsettled",
    "bundle_premiums",
    "bundle_payments",
    "bundle_liabilities",
    "regional_premiums",
    "regional_payments",
    "inson_premiums_market_share",
    "inson_payments_market_share",
    "inson_subdivision_premiums",
    "inson_subdivision_payments",
    "inson_payment_premium_ratio",
    "inson_region_to_company_ratio",
}
ALLOWED = {"cbu", "napp_market", "napp_reference", *SIAT}
PUBLIC_FIELDS = {
    "metric",
    "region",
    "class_code",
    "object_type",
    "period",
    "value",
    "unit",
    "source_url",
    "observation_date",
    "stale_days",
    "subject",
    "reference_only",
}


def public_data(channel, data):
    """Only known official series; discard approvals, notes, quote adjustments and extra fields."""
    url = urlsplit(str(data["source_url"]))
    if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
        raise ValueError("Snapshot requires an uncredentialed official source URL")
    metric = data["metric"]
    if channel in SIAT:
        dataset, expected = SIAT[channel]
        valid = (
            metric == expected
            and url.hostname == "api.siat.stat.uz"
            and url.path == f"/media/uploads/sdmx/sdmx_data_{dataset}.json"
        )
    elif channel == "cbu":
        valid = (
            bool(re.fullmatch(r"fx_[A-Z]{3}", metric))
            and url.hostname == "cbu.uz"
            and url.path == "/ru/arkhiv-kursov-valyut/json/"
        )
    elif channel in {"napp_market", "napp_reference"}:
        valid = url.hostname == "napp.uz" and bool(
            re.fullmatch(r"/storage/files/shares/opendata/20\d{2}/[1-4]Q/[^/]+\.xlsx", unquote(url.path))
        )
        valid = valid and (
            metric in {"market_premiums", "market_payments", "market_liabilities", "market_loss_ratio"}
            if channel == "napp_market"
            else metric.removeprefix("napp_ref_") in NAPP_METRICS and metric.startswith("napp_ref_")
        )
    else:
        valid = False
    if not valid:
        raise ValueError(f"Not a supported public series: {channel}")
    clean = {k: v for k, v in data.items() if k in PUBLIC_FIELDS}
    if channel == "napp_reference":
        from surveyor.napp_reference import PORTFOLIO_NOTE, REGIONAL_NOTE

        clean["reference_only"] = True
        clean["note"] = (
            REGIONAL_NOTE
            if clean.get("region", "all") != "all" or "region_to_company" in metric
            else PORTFOLIO_NOTE
        )
        if "bundle_" in metric:
            clean["note"] = (
                "Комплексное страхование: единая сумма по набору классов, без распределения между ними."
            )
        if "market_share" in metric:
            clean["note"] = "Доля INSON в общем рынке, включая страхование жизни; период совпадает с отчётом."
    else:
        clean["subject"] = "market"
    return IndicatorInput.model_validate(clean).model_dump(mode="json")


def checksum(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def identity(channel, data):
    return (
        channel,
        data["metric"],
        data.get("region", "all"),
        data.get("class_code", "all"),
        data.get("object_type", "all"),
        data["period"],
        data.get("subject", "market"),
    )


def export_snapshot(db, destination=SNAPSHOT):
    destination = Path(destination).resolve()
    source_url = db.get_bind().url
    if (
        source_url.get_backend_name() == "sqlite"
        and source_url.database
        and Path(source_url.database).resolve() == destination
    ):
        raise ValueError("Cannot export over the working database")
    destination.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        path = Path(scratch) / "public.sqlite"
        engine = create_engine(f"sqlite:///{path}")
        try:
            Base.metadata.create_all(engine)
            with DBSession(engine) as target:
                channels = set()
                for row in db.scalars(
                    select(Indicator)
                    .where(Indicator.channel_code.in_(ALLOWED))
                    .order_by(Indicator.fetched_at, Indicator.id)
                ):
                    data = public_data(row.channel_code, row.data)
                    if row.channel_code not in channels:
                        target.add(
                            Channel(
                                code=row.channel_code,
                                enabled=False,
                                data={
                                    "domain": urlsplit(data["source_url"]).hostname,
                                    "access": "official_file",
                                    "note": "Public statistics snapshot",
                                },
                            )
                        )
                        target.flush()
                        channels.add(row.channel_code)
                    serialized = json.dumps(
                        [row.channel_code, data, row.fetched_at.isoformat()], sort_keys=True
                    )
                    exported_id = hashlib.sha256(serialized.encode()).hexdigest()[:36]
                    if target.get(Indicator, exported_id):
                        continue
                    target.add(
                        Indicator(
                            id=exported_id,
                            channel_code=row.channel_code,
                            data=data,
                            fetched_at=row.fetched_at,
                        )
                    )
                    counts[row.channel_code] += 1
                target.commit()
        finally:
            engine.dispose()
        manifest = {
            "format": 1,
            "created_at": now().isoformat(),
            "sha256": checksum(path),
            "observations": sum(counts.values()),
            "channels": dict(sorted(counts.items())),
            "contents": "Public statistical observations only. No accounts, credentials, sessions, inspections, documents, reports, audit logs or approval identities.",
        }
        path.replace(destination)
        destination.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    return verify_snapshot(destination)


def read_snapshot(path=SNAPSHOT):
    path = Path(path).resolve()
    manifest = json.loads(path.with_suffix(".json").read_text())
    if manifest.get("format") != 1 or checksum(path) != manifest.get("sha256"):
        raise ValueError("Snapshot checksum or format mismatch")
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if (
            db.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or db.execute("PRAGMA foreign_key_check").fetchall()
        ):
            raise ValueError("Snapshot integrity check failed")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != set(Base.metadata.tables):
            raise ValueError("Unexpected snapshot schema")
        for table in Base.metadata.sorted_tables:
            if (
                table.name not in {"channels", "indicators"}
                and db.execute(f'SELECT COUNT(*) FROM "{table.name}"').fetchone()[0]
            ):
                raise ValueError(f"Snapshot contains nonpublic rows: {table.name}")
        for code, data, enabled, attempt, success, error in db.execute(
            "SELECT code,data,enabled,last_attempt,last_success,error FROM channels"
        ):
            if code not in ALLOWED or enabled or any(x is not None for x in (attempt, success, error)):
                raise ValueError("Snapshot contains operational channel state")
            if set(json.loads(data)) != {"domain", "access", "note"}:
                raise ValueError("Snapshot contains nonpublic channel configuration")
        result = []
        counts = Counter()
        for channel, raw, fetched in db.execute(
            "SELECT channel_code,data,fetched_at FROM indicators ORDER BY fetched_at,id"
        ):
            data = json.loads(raw)
            clean = public_data(channel, data)
            if clean != data:
                raise ValueError("Snapshot contains nonpublic indicator fields")
            result.append((channel, clean, datetime.fromisoformat(fetched)))
            counts[channel] += 1
        if dict(counts) != manifest["channels"] or len(result) != manifest["observations"]:
            raise ValueError("Snapshot counts do not match manifest")
    return manifest, result


def verify_snapshot(path=SNAPSHOT):
    manifest, _ = read_snapshot(path)
    return manifest


def import_snapshot(db, path=SNAPSHOT):
    """Insert missing series/periods only; existing local versions and approvals always win."""
    manifest, rows = read_snapshot(path)
    seen = {identity(r.channel_code, r.data) for r in db.scalars(select(Indicator))}
    channels = set(db.scalars(select(Channel.code)))
    imported = 0
    # For identical identities in the bundle, retain the newest publication version.
    for channel, data, fetched in reversed(rows):
        key = identity(channel, data)
        if key in seen:
            continue
        if channel not in channels:
            db.add(
                Channel(
                    code=channel,
                    enabled=False,
                    data={
                        "domain": urlsplit(data["source_url"]).hostname,
                        "access": "official_file",
                        "note": "Public statistics snapshot",
                    },
                )
            )
            db.flush()
            channels.add(channel)
        db.add(Indicator(channel_code=channel, data=data, fetched_at=fetched))
        seen.add(key)
        imported += 1
    db.flush()
    return {"imported": imported, "skipped": len(rows) - imported, "sha256": manifest["sha256"]}
