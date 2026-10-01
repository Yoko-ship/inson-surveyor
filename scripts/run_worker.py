"""One background worker per shared local data directory. No credentials in status/logs."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from surveyor.bootstrap import bootstrap  # noqa: E402
from surveyor.cli import main  # noqa: E402
from surveyor.config import settings  # noqa: E402
from surveyor.file_lock import locked_file  # noqa: E402

if __name__ == "__main__":
    try:
        with locked_file(settings.storage_dir.parent / "worker.lock", blocking=False) as lock:
            lock.truncate()
            lock.write(str(os.getpid()))
            lock.flush()
            bootstrap()
            sys.argv = [sys.argv[0], "worker"]
            main()
    except BlockingIOError:
        raise SystemExit("Worker is already running for this data directory") from None
