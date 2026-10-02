"""Local consistent backups with integrity verification and non-destructive restore."""

import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

from surveyor.config import settings
from surveyor.db import Audit, LoginAttempt, Session, TelegramUpdate, now


def checksum(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def create_backup(database_url=None, backup_dir=None):
    from sqlalchemy.engine import make_url

    url = make_url(database_url or settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise ValueError(
            "This local backup command requires SQLite; use the PostgreSQL backup script for PostgreSQL"
        )
    source = Path(url.database).resolve()
    if not source.is_file():
        raise ValueError("Database does not exist")
    root = Path(backup_dir or settings.backup_dir).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = root / now().strftime("%Y%m%dT%H%M%S%f")
    dest.mkdir(mode=0o700)
    try:
        (dest / "uploads").mkdir(mode=0o700)
        with (
            closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as conn,
            closing(sqlite3.connect(dest / "database.sqlite")) as copy,
        ):
            conn.backup(copy)
            documents = copy.execute("SELECT id, path, sha256 FROM documents").fetchall()
        files = {"database.sqlite": checksum(dest / "database.sqlite")}
        from surveyor.file_lock import locked_file

        with locked_file(settings.ai_config_dir / "settings.lock"):
            for source in settings.ai_config_dir.rglob("*.json"):
                if source.is_symlink() or not source.is_file():
                    continue
                relative = Path("ai") / source.relative_to(settings.ai_config_dir)
                target = dest / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(source, target)
                files[relative.as_posix()] = checksum(target)
        document_map = {}
        for doc_id, path, expected in documents:
            path = Path(path)
            name = f"uploads/{doc_id}{path.suffix}"
            if checksum(path) != expected:
                raise ValueError("Document checksum mismatch")
            shutil.copyfile(path, dest / name)
            files[name] = expected
            document_map[doc_id] = name
        (dest / "manifest.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "created_at": now().isoformat(),
                    "database": "sqlite",
                    "files": files,
                    "documents": document_map,
                },
                indent=2,
            )
        )
        for p in dest.rglob("*"):
            if p.is_file():
                p.chmod(0o600)
        verify_backup(dest)
        return dest
    except Exception:
        shutil.rmtree(dest)
        raise


def verify_backup(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("version") != 1:
        raise ValueError("Unsupported backup version")
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or path.is_symlink():
            raise ValueError("Unsafe backup path")
        if checksum(path) != expected:
            raise ValueError("Backup checksum mismatch")
    with closing(sqlite3.connect(f"file:{directory / 'database.sqlite'}?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        for doc_id, expected in conn.execute("SELECT id, sha256 FROM documents"):
            name = manifest["documents"].get(doc_id)
            if not name or manifest["files"].get(name) != expected:
                raise ValueError("Backup is missing a referenced document")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign key check failed")
    return manifest


def restore_backup(directory, destination):
    """Never overwrite a live database. Restore into an empty, new directory only."""
    directory, dest = Path(directory).resolve(), Path(destination).resolve()
    manifest = verify_backup(directory)
    if dest.exists():
        raise ValueError("Restore destination must not exist")
    if dest.is_relative_to(directory):
        raise ValueError("Restore destination must be outside the backup")
    dest.mkdir(parents=True, mode=0o700)
    (dest / "uploads").mkdir(mode=0o700)
    try:
        for name in manifest["files"]:
            (dest / name).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(directory / name, dest / name)
            (dest / name).chmod(0o600)
        with closing(sqlite3.connect(dest / "database.sqlite")) as conn:
            for doc_id, name in manifest["documents"].items():
                conn.execute("UPDATE documents SET path=? WHERE id=?", (str(dest / name), doc_id))
            # Existing session cookies must not authenticate against a restored environment.
            conn.execute("DELETE FROM sessions")
            conn.commit()
        return dest
    except Exception:
        shutil.rmtree(dest)
        raise


def maintain(db):
    db.execute(delete(Session).where(Session.expires_at < now()))
    db.execute(delete(LoginAttempt).where(LoginAttempt.reset_at < now()))
    db.execute(delete(TelegramUpdate).where(TelegramUpdate.created_at < now() - timedelta(days=30)))
    db.add(Audit(action="worker.heartbeat", entity_id="local", data={}))
    db.commit()
    if not settings.backup_enabled or not settings.database_url.startswith("sqlite"):
        return
    recent = db.scalar(
        select(Audit).where(
            Audit.action == "backup.completed", Audit.created_at > now() - timedelta(hours=24)
        )
    )
    if recent:
        return
    try:
        path = create_backup()
        db.add(Audit(action="backup.completed", entity_id=path.name, data={"verified": True}))
        # Only prune valid backups produced by this tool, after a new verified backup exists.
        cutoff = now() - timedelta(days=settings.backup_retention_days)
        for candidate in settings.backup_dir.glob("*/manifest.json"):
            if candidate.parent == path:
                continue
            try:
                metadata = verify_backup(candidate.parent)
                if metadata["created_at"] < cutoff.isoformat():
                    shutil.rmtree(candidate.parent)
            except (ValueError, OSError, KeyError):
                pass
    except (ValueError, OSError, sqlite3.Error):
        db.add(
            Audit(
                action="backup.failed",
                entity_id="local",
                data={"message": "Backup failed integrity/storage check; inspect local storage"},
            )
        )
    db.commit()
