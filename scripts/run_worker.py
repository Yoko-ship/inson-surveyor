"""One background worker per shared local data directory. No credentials in status/logs."""

import fcntl
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor.bootstrap import bootstrap  # noqa: E402
from surveyor.cli import main  # noqa: E402
from surveyor.config import settings  # noqa: E402

path = settings.storage_dir.parent / "worker.lock"
path.parent.mkdir(parents=True, exist_ok=True)
lock = path.open("a+")
try:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Worker is already running for this data directory") from None
lock.seek(0)
lock.truncate()
lock.write(str(os.getpid()))
lock.flush()

bootstrap()
sys.argv = [sys.argv[0], "worker"]
main()
