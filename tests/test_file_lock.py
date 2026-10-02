import os
import subprocess
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import pytest

from surveyor.file_lock import locked_file

ROOT = Path(__file__).resolve().parents[1]
TRY_LOCK = """
import sys
from surveyor.file_lock import locked_file
try:
    with locked_file(sys.argv[1], blocking=False) as stream:
        print(stream.read())
except BlockingIOError:
    sys.exit(23)
"""


def try_lock(path):
    return subprocess.run(
        [sys.executable, "-c", TRY_LOCK, str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_lock_excludes_other_process_and_preserves_contents(tmp_path):
    path = tmp_path / "shared.lock"
    with locked_file(path) as stream:
        assert try_lock(path).returncode == 23  # Empty files are protected too.
        stream.write("previous timestamp")
        stream.flush()
        assert try_lock(path).returncode == 23
    result = try_lock(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "previous timestamp"


def test_lock_released_after_exception_and_truncation(tmp_path):
    path = tmp_path / "shared.lock"
    path.write_text("old long timestamp", encoding="utf-8")
    with pytest.raises(ValueError, match="failed work"):
        with locked_file(path) as stream:
            stream.truncate()
            stream.write("new")
            raise ValueError("failed work")
    result = try_lock(path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "new"


def test_blocking_waiter_reads_latest_contents(tmp_path):
    path = tmp_path / "shared.lock"
    ready = tmp_path / "waiting"
    code = """
import sys
from pathlib import Path
from surveyor.file_lock import locked_file
Path(sys.argv[2]).touch()
with locked_file(sys.argv[1]) as stream:
    print(stream.read(), flush=True)
"""
    with ExitStack() as processes:
        waiter = None
        try:
            with locked_file(path) as stream:
                waiter = processes.enter_context(
                    subprocess.Popen(
                        [sys.executable, "-c", code, str(path), str(ready)],
                        cwd=ROOT,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )
                deadline = time.monotonic() + 10
                while not ready.exists() and waiter.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                assert ready.exists(), "Child failed to start"
                with pytest.raises(subprocess.TimeoutExpired):
                    waiter.communicate(timeout=0.2)
                stream.write("written before unlock")
            output, error = waiter.communicate(timeout=10)
            assert waiter.returncode == 0, error
            assert "written before unlock" in output
        finally:
            if waiter is not None and waiter.poll() is None:
                waiter.kill()
                waiter.wait()


def test_worker_refuses_second_owner(tmp_path):
    storage = tmp_path / "uploads"
    with locked_file(tmp_path / "worker.lock") as stream:
        stream.write("existing worker")
        stream.flush()
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run_worker.py")],
            cwd=ROOT,
            env={**os.environ, "STORAGE_DIR": str(storage)},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0
        assert "Worker is already running" in result.stderr
        stream.seek(0)
        assert stream.read() == "existing worker"
