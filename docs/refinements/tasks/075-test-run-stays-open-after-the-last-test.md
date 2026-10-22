# A test run sometimes stays open after its last test

**Status:** done 2026-10-23
**Area:** tests, repo checks
**Origin:** Found on 2026-10-22 when the test run of the pre-commit hook did not end after its last test
**Verified:** 2026-10-23

Once, `just check` in the pre-commit hook ran every test and then did not end. The `pytest` process stayed open
for more than 10 minutes with almost no CPU time, so `git commit` waited until the process was ended by hand.
The temporary folders of pytest went up to the last test of the suite, `test_websocket.py`'s test of a restart
with fewer topics, so each test had run.

What the process held, read from `/proc`:

- 5 threads: the main thread and one other thread waiting on a lock (`futex_wait_queue`), one thread in
  `select`, and the two GLib threads `gmain` and `pool-spawner`, which start when a test loads GLib through
  PyGObject;
- the child process of `multiprocessing.resource_tracker`;
- on the Xvfb display, one unnamed 1 by 1 window and no Tk window.

A main thread that waits on a lock after the last test matches Python's exit, which waits for each thread that
is not a daemon thread. Which thread it waited for is not known: the process had no `faulthandler`, and the
shell has neither `py-spy` nor `gdb`.

The same tree then passed 25 runs with no wait: 15 runs of the suite with coverage, 8 runs with and without
coverage, and 2 runs in the pre-commit hook.

## What a fix involves

Find the thread. A `pytest_sessionfinish` hook in `tests/conftest.py` can list the threads of
`threading.enumerate()` that are alive and not daemon threads, and fail the run with their names instead of
waiting. `PYTHONFAULTHANDLER=1` with `timeout -s SIGABRT` around a run prints the stack of every thread of a run
that does not end. Then end that thread in the test that starts it. Twitch requests: none.

## How it was closed

`tests/threadcheck.py`, which `tests/conftest.py` loads, ends such a run. Its `pytest_sessionfinish` gives each
thread that is not a daemon thread 5 seconds to end, then prints the name and the stack of each one that still
runs and sets the exit status to 1. Its `pytest_unconfigure` then ends the process with `os._exit`, so the exit
does not wait. `tests/test_threadcheck.py` runs pytest in a child process on a test that leaves a thread waiting:
the run ends at once with status 1 and names the thread and its stack. Without the hook the child process does
not end within the 60 seconds the test gives it.

The thread of the first run was not found. With the check in place, 40 runs of the tray and GUI test files
and 15 runs of the whole suite with coverage, each under `xvfb-run`, reported no thread. Tk leaves one unnamed 1 by 1 window open
after `tk.Tk().destroy()`, which the `display` fixture calls, so every run that opens a window has the window
that the first run showed. The window of an X11 icon has the icon's title as its name.

A failed assertion placed in each tray test before its cleanup showed five tests that then leave a thread
running. The three tests of a change from another thread left that thread waiting on a lock in `_dispatch`. The
test of a click left the X11 icon thread in `select`, because `icon.stop()` does nothing before pystray marks the
icon running. The GUI tray test left pystray's setup thread waiting in `_dispatch`. A thread waiting on a lock
matches one thread of the first run. Its thread in `select` had no icon window, so it was probably not an X11
icon thread, whose window stays while it runs. Whether a test of the first run failed is not known: pre-commit
shows the output of a hook only when the hook ends. Each of these tests now ends its thread in a `finally` block,
with `release_caller`, `stop_icon` or `wait_until_shown` from `tests/xorgicon.py`, and the same eight placed
failures leave no thread.

The same stop in the app is [077](077-x11-tray-icon-stop-right-after-start-keeps-the-app-open.md).

## History

- 2026-10-22: Opened. The wait came once in the pre-commit hook and not in 25 runs after it.
- 2026-10-23: Closed with the thread check in place, which turns the next such wait into a failure that names
  the thread. The thread of the first run was not found. The tray tests that left a thread after a failed
  assertion now end it. Opened [077](077-x11-tray-icon-stop-right-after-start-keeps-the-app-open.md).
