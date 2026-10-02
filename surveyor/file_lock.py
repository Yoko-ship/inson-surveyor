"""Process locks for shared local files on Windows, macOS and Linux."""

import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _acquire(stream, blocking):
    if os.name != "nt":
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(stream.fileno(), flags)
        return
    # Windows locks bytes from the current position, including beyond EOF.
    # Retry ourselves: LK_LOCK gives up after ten seconds, unlike flock.
    while True:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise
            if not blocking:
                raise BlockingIOError(errno.EAGAIN, "File is already locked", stream.name) from None
            time.sleep(0.05)


@contextmanager
def locked_file(path, *, blocking=True):
    """Open without truncating; hold an exclusive lock until the context exits.

    Keep the lock file in place after release so every process locks the same
    file. Nonblocking acquisition raises BlockingIOError if another owner exists.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+", encoding="utf-8") as stream:
        _acquire(stream, blocking)
        try:
            path.chmod(0o600)
            stream.seek(0)
            yield stream
        finally:
            stream.flush()
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
