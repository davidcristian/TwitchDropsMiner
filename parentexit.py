"""Ends the app with the AppImage runtime that started it as a child process, which passes no signal on to it."""
from __future__ import annotations

import ctypes
import os
import signal
from collections import abc
from typing import Protocol


# from <linux/prctl.h>
PR_SET_PDEATHSIG = 1


class ProcessCalls(Protocol):
    def parent_id(self) -> int:
        """Return the ID of the parent process."""

    def executable(self, pid: int) -> str:
        """Return the path of the file that the process runs, or raise OSError."""

    def signal_on_parent_exit(self, signum: int) -> None:
        """Ask the kernel to send signum to this process when its parent ends, or raise OSError."""

    def signal_self(self, signum: int) -> None:
        """Send signum to this process."""


class LinuxProcess:
    """The calls of `ProcessCalls` on Linux."""

    def parent_id(self) -> int:
        return os.getppid()

    def executable(self, pid: int) -> str:
        return os.readlink(f"/proc/{pid}/exe")

    def signal_on_parent_exit(self, signum: int) -> None:
        libc = ctypes.CDLL(None, use_errno=True)
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl.restype = ctypes.c_int
        if libc.prctl(PR_SET_PDEATHSIG, signum, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))

    def signal_self(self, signum: int) -> None:
        os.kill(os.getpid(), signum)


def end_with_runtime(platform: str, environ: abc.Mapping[str, str], calls: ProcessCalls) -> bool:
    """On Linux, have the kernel send SIGTERM to the app when the AppImage runtime that is its parent ends.

    environ is the app's environment, where the runtime sets APPIMAGE. Returns whether the parent is that runtime.
    """
    appimage = environ.get("APPIMAGE")
    if platform != "linux" or not appimage:
        return False
    parent = calls.parent_id()
    try:
        # Through FUSE, the runtime runs the app in its own process, so the parent is the program that started it.
        if calls.executable(parent) != appimage:
            return False
        calls.signal_on_parent_exit(signal.SIGTERM)
    except OSError:
        return False
    if calls.parent_id() != parent:
        # the runtime ended before the request, so the kernel will send nothing
        calls.signal_self(signal.SIGTERM)
    return True
