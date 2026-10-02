import json
import sqlite3
from contextlib import closing
from datetime import date

import pytest
from sqlalchemy import select

from surveyor.db import Channel, Indicator, User
from surveyor.public_database import checksum, export_snapshot, import_snapshot, verify_snapshot
from surveyor.schemas import IndicatorInput


def public_sample():
    return IndicatorInput(
        metric="registered_thefts",
        value=42,
        period="2025",
        unit="units",
        observation_date=date(2025, 12, 31),
        source_url="https://api.siat.stat.uz/media/uploads/sdmx/sdmx_data_888.json",
    ).model_dump(mode="json")


def test_export_has_public_data_but_no_private_rows_or_deleted_pages(admin, tmp_path):
    destination = tmp_path / "public.sqlite"
    with admin.factory() as db:
        db.add(
            Indicator(
                channel_code="stat_theft",
                data={
                    **public_sample(),
                    "approved_by": "PRIVATE-APPROVER",
                    "note": "PRIVATE-NOTE",
                    "custom": "PRIVATE-EXTRA",
                },
            )
        )
        db.commit()
        manifest = export_snapshot(db, destination)
    assert manifest["observations"] == 1
    with closing(sqlite3.connect(destination)) as db:
        for table in [
            "users",
            "sessions",
            "login_attempts",
            "audit",
            "telegram_updates",
            "surveys",
            "documents",
            "reports",
        ]:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    content = destination.read_bytes()
    assert not any(
        secret in content
        for secret in [b"PRIVATE-APPROVER", b"PRIVATE-NOTE", b"PRIVATE-EXTRA", b"$argon2id$"]
    )
    assert verify_snapshot(destination)["sha256"] == checksum(destination)


def test_import_preserves_local_users_versions_approvals_and_channels(admin, tmp_path):
    destination = tmp_path / "public.sqlite"
    with admin.factory() as db:
        row = Indicator(channel_code="stat_theft", data=public_sample())
        db.add(row)
        db.commit()
        export_snapshot(db, destination)
        row.data = {**public_sample(), "value": "99", "approved_by": "local-actuary"}
        channel = db.get(Channel, "stat_theft")
        channel.enabled = False
        channel.error = "Local source disabled"
        db.commit()
        password = db.scalar(select(User)).password_hash
        result = import_snapshot(db, destination)
        db.commit()
        assert result["imported"] == 0
        assert row.data["value"] == "99"
        assert row.data["approved_by"] == "local-actuary"
        assert db.scalar(select(User)).password_hash == password
        assert not channel.enabled and channel.error == "Local source disabled"


def test_missing_series_import_is_idempotent(admin, tmp_path):
    destination = tmp_path / "public.sqlite"
    with admin.factory() as db:
        row = Indicator(channel_code="stat_theft", data=public_sample())
        db.add(row)
        db.commit()
        export_snapshot(db, destination)
        db.delete(row)
        db.commit()
        assert import_snapshot(db, destination)["imported"] == 1
        db.commit()
        assert import_snapshot(db, destination)["imported"] == 0
        assert db.scalar(select(Indicator)).data["value"] == "42"


def test_corrupt_bundle_is_rejected_before_writes(admin, tmp_path):
    destination = tmp_path / "public.sqlite"
    with admin.factory() as db:
        export_snapshot(db, destination)
        with destination.open("ab") as out:
            out.write(b"tampered")
        with pytest.raises(ValueError, match="checksum"):
            import_snapshot(db, destination)
        assert not db.scalar(select(Indicator))


def test_snapshot_rejects_operational_rows_even_with_updated_checksum(admin, tmp_path):
    destination = tmp_path / "public.sqlite"
    with admin.factory() as db:
        export_snapshot(db, destination)
    with closing(sqlite3.connect(destination)) as conn:
        conn.execute("INSERT INTO telegram_updates VALUES (1, '2026-01-01')")
        conn.commit()
    manifest_path = destination.with_suffix(".json")
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = checksum(destination)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="nonpublic rows"):
        verify_snapshot(destination)


def test_tracked_snapshot_is_checked_and_usable():
    manifest = verify_snapshot()
    assert manifest["observations"] == 12808
    assert manifest["channels"]["napp_reference"] == 653
