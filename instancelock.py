"""The lock on `lock.file` that lets only one copy of the app run from a folder."""
from __future__ import annotations

import io
import sys
from contextlib import suppress
from pathlib import Path
from typing import NamedTuple


class Lock(NamedTuple):
    """The result of `lock_file`: the locked file, or the error that opening or writing it raised.

    Both are None when another process holds the lock. The lock lasts while `file` stays open.
    """

    file: io.TextIOWrapper | None
    error: OSError | None


def lock_file(path: Path) -> Lock:
    """Open the file at path, write one character and lock it without waiting."""
    file: io.TextIOWrapper | None = None
    try:
        file = path.open("w", encoding="utf8")
        file.write("ツ")
        file.flush()
    except OSError as exc:
        if file is not None:
            with suppress(OSError):
                file.close()
        return Lock(None, exc)
    if _try_lock(file, path):
        return Lock(file, None)
    file.close()
    return Lock(None, None)


def _try_lock(file: io.TextIOWrapper, path: Path) -> bool:
    """Lock the open file, and return False when another process holds the lock."""
    if sys.platform == "win32":
        import msvcrt
        try:
            # msvcrt.locking locks a range of bytes, so the range must not be empty
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, max(path.stat().st_size, 1))
        except OSError:
            return False
        return True
    if sys.platform in ("linux", "darwin"):
        import fcntl
        try:
            fcntl.lockf(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True
    return True
