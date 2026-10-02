"""Process durable jobs independently from browsers and the HTTP server."""

import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor.ai_jobs import process_one  # noqa: E402
from surveyor.config import settings  # noqa: E402
from surveyor.file_lock import locked_file  # noqa: E402


def main():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logging.basicConfig(level=logging.INFO)
    try:
        with locked_file(settings.storage_dir.parent / "ai-worker.lock", blocking=False):
            while not stop.is_set():
                try:
                    status = settings.storage_dir.parent / "ai-worker-status.json"
                    temporary = status.with_suffix(".tmp")
                    temporary.write_text(json.dumps({"last_seen": time.time()}), encoding="utf-8")
                    temporary.replace(status)
                    worked = process_one()
                except Exception as exc:
                    logging.error("AI worker cycle failed (%s)", type(exc).__name__)
                    worked = False
                stop.wait(0.2 if worked else 2)
    except BlockingIOError:
        raise SystemExit("AI worker already running for this data directory") from None


if __name__ == "__main__":
    main()
