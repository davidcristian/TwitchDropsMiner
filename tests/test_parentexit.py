from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from parentexit import LinuxProcess, end_with_runtime

ROOT = Path(__file__).resolve().parent.parent
APPIMAGE = "/home/user/Twitch Drops Miner/Twitch.Drops.Miner-x86_64.AppImage"


class FakeProcess:
    def __init__(self, parents: list[int], executables: dict[int, str], prctl_error: OSError | None = None) -> None:
        self.parents = parents
        self.executables = executables
        self.prctl_error = prctl_error
        self.requested: list[int] = []
        self.signals: list[int] = []

    def parent_id(self) -> int:
        return self.parents.pop(0) if len(self.parents) > 1 else self.parents[0]

    def executable(self, pid: int) -> str:
        if pid not in self.executables:
            raise FileNotFoundError(2, "No such file or directory")
        return self.executables[pid]

    def signal_on_parent_exit(self, signum: int) -> None:
        if self.prctl_error is not None:
            raise self.prctl_error
        self.requested.append(signum)

    def signal_self(self, signum: int) -> None:
        self.signals.append(signum)


def test_a_child_of_the_runtime_gets_sigterm_when_the_runtime_ends():
    calls = FakeProcess([20], {20: APPIMAGE})
    assert end_with_runtime("linux", {"APPIMAGE": APPIMAGE}, calls) is True
    assert calls.requested == [signal.SIGTERM]
    assert calls.signals == []


def test_a_runtime_that_ended_before_the_request_sends_sigterm_at_once():
    calls = FakeProcess([20, 1], {20: APPIMAGE, 1: "/sbin/init"})
    assert end_with_runtime("linux", {"APPIMAGE": APPIMAGE}, calls) is True
    assert calls.requested == [signal.SIGTERM]
    assert calls.signals == [signal.SIGTERM]


def test_a_start_through_fuse_whose_parent_is_a_shell_requests_nothing():
    calls = FakeProcess([19], {19: "/usr/bin/bash"})
    assert end_with_runtime("linux", {"APPIMAGE": APPIMAGE}, calls) is False
    assert calls.requested == []
    assert calls.signals == []


@pytest.mark.parametrize("environ", [{}, {"APPIMAGE": ""}])
def test_a_run_outside_an_appimage_requests_nothing(environ):
    calls = FakeProcess([20], {20: APPIMAGE})
    assert end_with_runtime("linux", environ, calls) is False
    assert calls.requested == []


@pytest.mark.parametrize("platform", ["win32", "darwin", "freebsd14"])
def test_other_platforms_request_nothing(platform):
    calls = FakeProcess([20], {20: APPIMAGE})
    assert end_with_runtime(platform, {"APPIMAGE": APPIMAGE}, calls) is False
    assert calls.requested == []


def test_a_parent_whose_file_cannot_be_read_requests_nothing():
    calls = FakeProcess([20], {})
    assert end_with_runtime("linux", {"APPIMAGE": APPIMAGE}, calls) is False
    assert calls.requested == []
    assert calls.signals == []


def test_a_failed_request_sends_no_signal():
    calls = FakeProcess([20, 1], {20: APPIMAGE}, prctl_error=OSError(22, "Invalid argument"))
    assert end_with_runtime("linux", {"APPIMAGE": APPIMAGE}, calls) is False
    assert calls.signals == []


@pytest.mark.skipif(sys.platform != "linux", reason="reads /proc")
def test_the_executable_of_a_process_is_the_file_it_runs():
    assert LinuxProcess().executable(os.getpid()) == os.path.realpath(sys.executable)
    with pytest.raises(FileNotFoundError):
        LinuxProcess().executable(2**22 + 1)


# The child calls end_with_runtime with its parent's file as APPIMAGE, prints the result and its PID, and writes
# the file named in argv[2] when SIGTERM arrives
CHILD = """
import os, signal, sys, time
sys.path.insert(0, sys.argv[1])
from parentexit import LinuxProcess, end_with_runtime
signal.signal(signal.SIGTERM, lambda *args: (open(sys.argv[2], "w").close(), os._exit(0)))
environ = {"APPIMAGE": os.readlink(f"/proc/{os.getppid()}/exe")}
print(end_with_runtime(sys.platform, environ, LinuxProcess()), os.getpid(), flush=True)
time.sleep(60)
"""
# A stand in for the runtime: it starts the child, which prints to the same output, and waits
RUNTIME = """
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2], sys.argv[3]])
time.sleep(60)
"""


@pytest.mark.skipif(sys.platform != "linux", reason="prctl is Linux only")
def test_the_kernel_sends_sigterm_to_the_child_when_the_runtime_is_killed(tmp_path):
    ended = tmp_path / "ended"
    runtime = subprocess.Popen(
        [sys.executable, "-c", RUNTIME, CHILD, str(ROOT), str(ended)], stdout=subprocess.PIPE, text=True
    )
    assert runtime.stdout is not None
    result, child = runtime.stdout.readline().split()
    try:
        assert result == "True"
        runtime.kill()
        runtime.wait()
        deadline = time.monotonic() + 10
        while not ended.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ended.exists()
    finally:
        runtime.kill()
        runtime.stdout.close()
        try:
            os.kill(int(child), signal.SIGKILL)
        except ProcessLookupError:
            pass
