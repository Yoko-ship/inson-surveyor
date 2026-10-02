"""Run the browser app and worker with the current Python environment on any OS."""

import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    subprocess.run([sys.executable, str(ROOT / "scripts" / "setup_local.py")], check=True)

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    port = int(os.getenv("PORT", "8010"))
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Port {port} is unavailable; check PORT and PUBLIC_URL in .env") from None

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    from surveyor.bootstrap import bootstrap
    from surveyor.config import settings

    # Finish first-time seeding before starting either process.
    bootstrap()
    if settings.data_mode == "synthetic":
        from surveyor.db import SessionLocal
        from surveyor.public_database import import_snapshot

        with SessionLocal() as db:
            result = import_snapshot(db)
            db.commit()
        print(f"Public database: {result['imported']} observations imported; local records preserved.")
    log_path = settings.storage_dir.parent / "worker.log"
    with log_path.open("a", encoding="utf-8") as log:
        worker = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_worker.py")],
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        ai_worker = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "run_ai_worker.py")],
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            print(f"Open {settings.public_url} (Ctrl+C to stop). Worker log: {log_path}", flush=True)
            uvicorn.run("surveyor.main:app", host="127.0.0.1", port=port)
        finally:
            if ai_worker.poll() is None:
                ai_worker.terminate()
                try:
                    ai_worker.wait(timeout=100)
                except subprocess.TimeoutExpired:
                    ai_worker.kill()
                    ai_worker.wait()
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()


if __name__ == "__main__":
    main()
