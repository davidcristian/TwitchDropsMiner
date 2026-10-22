# A test run sometimes stays open after its last test

**Status:** open
**Area:** tests, repo checks
**Origin:** Found on 2026-10-22 when the test run of the pre-commit hook did not end after its last test
**Verified:** 2026-10-22

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

## History

- 2026-10-22: Opened. The wait came once in the pre-commit hook and not in 25 runs after it.
