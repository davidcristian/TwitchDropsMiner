"""Fake folder dialogs: functions a child process runs in place of Tk's dialog, and a `Dialog` a test answers."""
from __future__ import annotations

import time


def chosen_in(title: str, start: str) -> str:
    """Return the folder named after the title inside the start folder."""
    return f"{start}/{title}"


def failing(title: str, start: str) -> str:
    """Raise, as the dialog does when Tk cannot open a window."""
    raise RuntimeError("no display")


def open_for_an_hour(title: str, start: str) -> str:
    """Wait an hour, like a user who leaves the dialog open."""
    time.sleep(3600)
    return ""


class FakeDialog:
    """A dialog that stays open until a test sets its folder."""

    def __init__(self, title: str, start: str) -> None:
        self.title = title
        self.start = start
        self.folder: str | None = None
        self.closed = False

    def answer(self) -> str | None:
        return self.folder

    def close(self) -> None:
        self.closed = True


class FakeDialogs:
    """Opens a `FakeDialog` for each call and keeps them in `opened`."""

    def __init__(self) -> None:
        self.opened: list[FakeDialog] = []

    def __call__(self, title: str, start: str) -> FakeDialog:
        self.opened.append(FakeDialog(title, start))
        return self.opened[-1]
