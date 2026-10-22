"""A pytest plugin that fails a run which leaves a thread running that Python's exit would wait for."""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback

import pytest

# A thread that ends within this many seconds after the last test is not reported, as Python's exit waits for it.
GRACE = 5.0
_EXIT_STATUS = pytest.StashKey[int]()


def running_threads(grace: float) -> list[threading.Thread]:
    """Return the threads other than the main thread that are not daemon threads and still run after `grace`."""
    deadline = time.monotonic() + grace
    threads = [
        thread for thread in threading.enumerate()
        if thread is not threading.main_thread() and not thread.daemon and thread.is_alive()
    ]
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    return [thread for thread in threads if thread.is_alive()]


def thread_report(threads: list[threading.Thread]) -> list[str]:
    """Return the name and the stack of each thread, as lines."""
    frames = sys._current_frames()
    lines: list[str] = []
    for thread in threads:
        lines.append(f"Thread {thread.name!r}, ident {thread.ident}:")
        frame = frames.get(thread.ident)
        stack = traceback.format_stack(frame) if frame is not None else ["  (no stack)\n"]
        lines.extend("".join(stack).rstrip("\n").splitlines())
    return lines


def pytest_sessionfinish(session: pytest.Session) -> None:
    threads = running_threads(GRACE)
    if not threads:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    lines = ["These threads are not daemon threads and still run after the last test:"]
    lines += thread_report(threads)
    if reporter is None:
        print("\n".join(lines), file=sys.stderr)
    else:
        # ends the line of progress dots, which write_sep leaves open under -q
        reporter.write_line("")
        reporter.write_sep("=", "threads left running", red=True)
        for line in lines:
            reporter.write_line(line)
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    session.config.stash[_EXIT_STATUS] = int(session.exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    status = config.stash.get(_EXIT_STATUS, None)
    if status is None:
        return
    sys.stdout.flush()
    sys.stderr.flush()
    # Python's exit waits for each thread that is not a daemon thread, so the run ends here instead.
    os._exit(status)
