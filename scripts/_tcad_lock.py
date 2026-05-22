"""Minimal advisory file lock for .protocol/status.json writes.

Used by tcad_conduct.py, tcad_worktree.py, tcad_scan.py, tcad_log.py to
serialize status.json updates across concurrent terminals.

Pure stdlib. POSIX-only (uses fcntl). Acceptable for v0 — TCAD-H is local.
On Windows, falls back to a best-effort lockfile dance (no kernel guarantee).
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# fcntl is POSIX-only; degrade gracefully on Windows.
try:
    import fcntl  # type: ignore
    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover
    _HAVE_FCNTL = False


@contextmanager
def status_lock(lock_path: Path, timeout: float = 5.0, poll_interval: float = 0.05):
    """Acquire an exclusive advisory lock on lock_path, release on exit.

    Usage:
        with status_lock(Path('.protocol/status.lock')):
            ... read-modify-write status.json ...
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        if _HAVE_FCNTL:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"Could not acquire lock {lock_path} within {timeout}s"
                        )
                    time.sleep(poll_interval)
        else:
            # Windows fallback: poll for exclusive create. Not race-proof but
            # acceptable for local single-user dev.
            while lock_path.exists() and lock_path.stat().st_size > 0:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock {lock_path} within {timeout}s"
                    )
                time.sleep(poll_interval)
            os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        if fd is not None:
            try:
                if _HAVE_FCNTL:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except OSError:
                pass
        # Best-effort cleanup; another process may still hold the file.
        try:
            if not _HAVE_FCNTL and lock_path.exists():
                lock_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    # Self-test
    lock = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/_tcad_test.lock")
    with status_lock(lock):
        print(f"acquired {lock} for 1s")
        time.sleep(1)
    print("released")
