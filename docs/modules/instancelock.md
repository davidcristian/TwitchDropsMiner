# `instancelock.py`

**Purpose.** `lock_file` takes the lock on `lock.file` that stops a second copy of the app from running from the
same folder. `main.py` calls it once at startup with `LOCK_PATH` ([main.md](main.md#startup-order)). It reports a
file it cannot open as a result instead of raising, so `main.py` can show a message for it. The module imports no
other module of the app, so `tests/test_instancelock.py` runs it on real files in a temporary folder.

## Public contract

`lock_file(path)` opens `path` for writing, writes one character and locks the file without waiting. It returns
a `Lock` named tuple of `file` and `error`:

| Result | When |
| --- | --- |
| `file` is the open file, `error` is None | The lock was taken. It lasts while `file` stays open. |
| Both are None | Another process holds the lock. `lock_file` closes its own file first. |
| `file` is None, `error` is the `OSError` | Opening or writing the file raised it, for example `PermissionError` for a folder the user cannot write to, or `ENOSPC` on a full disk. |

The lock is taken with `msvcrt.locking` and `LK_NBLCK` on Windows, which locks the bytes of the file, and with
`fcntl.lockf` and `LOCK_EX | LOCK_NB` on Linux and macOS. On any other platform `lock_file` returns the file
without a lock. Every `OSError` from the lock call counts as a lock that another process holds. A held lock
raises `EACCES` or `EAGAIN` on Linux and macOS and `EACCES` on Windows. The check does not narrow to these codes:
no run on Windows confirmed them, and a code left out would turn the silent exit of a second copy into an error
dialog.

## Invariants

- The operating system releases the lock when the process ends, also after a crash, so `lock.file` never needs
  to be deleted. `tests/test_instancelock.py` asserts this on Linux.
- The lock is per folder: two copies started from different folders both run.
- `lock_file` returns an `OSError` from opening or writing the file and never raises it. An exception of another
  class passes up to the caller.

**Dependencies.** None: the standard library only.
