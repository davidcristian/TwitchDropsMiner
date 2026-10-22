from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from threadcheck import running_threads

TESTS = Path(__file__).resolve().parent
LEFT_RUNNING = """
import threading


def wait_forever(event):
    event.wait()


def test_leaves_a_thread_running():
    threading.Thread(target=wait_forever, args=(threading.Event(),), name="left running").start()
"""


def run_pytest(folder: Path) -> subprocess.CompletedProcess[str]:
    (folder / "conftest.py").write_text("import threadcheck\n\nthreadcheck.GRACE = 0.1\n", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(TESTS)}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "threadcheck", "-p", "no:cacheprovider", "test_left.py"],
        capture_output=True, text=True, cwd=folder, env=env, timeout=60,
    )


def test_a_run_that_leaves_a_thread_running_ends_and_fails_with_the_name_and_stack_of_the_thread(tmp_path):
    (tmp_path / "test_left.py").write_text(LEFT_RUNNING, encoding="utf-8")

    result = run_pytest(tmp_path)

    assert result.returncode == 1
    assert "1 passed" in result.stdout
    report = result.stdout[result.stdout.index("threads left running"):]
    assert "Thread 'left running'" in report
    assert "in wait_forever" in report and "event.wait()" in report


def test_a_thread_that_still_runs_after_the_grace_is_listed():
    event = threading.Event()
    thread = threading.Thread(target=event.wait)
    thread.start()
    try:
        assert thread in running_threads(0.0)
    finally:
        event.set()
        thread.join(5)


def test_a_thread_that_ends_within_the_grace_is_not_listed():
    event = threading.Event()
    thread = threading.Thread(target=event.wait)
    thread.start()
    setter = threading.Thread(target=lambda: (time.sleep(0.1), event.set()), daemon=True)
    setter.start()
    try:
        assert thread not in running_threads(5.0)
    finally:
        event.set()
        thread.join(5)


def test_a_daemon_thread_and_the_main_thread_are_not_listed():
    event = threading.Event()
    thread = threading.Thread(target=event.wait, daemon=True)
    thread.start()
    try:
        listed = running_threads(0.0)
        assert thread not in listed and threading.main_thread() not in listed
    finally:
        event.set()
        thread.join(5)
