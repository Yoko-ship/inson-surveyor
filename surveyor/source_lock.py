"""Per-host serialization across the local app and worker (shared storage volume)."""

import hashlib
import time
from contextlib import contextmanager

from surveyor.config import settings
from surveyor.file_lock import locked_file


@contextmanager
def host_lock(host):
    directory = settings.storage_dir.parent / "source-locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (hashlib.sha256(host.encode()).hexdigest() + ".lock")
    with locked_file(path) as stream:
        previous = stream.read()
        if previous:
            elapsed = time.time() - float(previous)
            if elapsed < 1:
                time.sleep(min(1, 1 - elapsed))
        try:
            yield
        finally:
            stream.seek(0)
            stream.truncate()
            stream.write(str(time.time()))
            stream.flush()
