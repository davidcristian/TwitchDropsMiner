"""Shows the folder dialog in a child process, so the event loop keeps running while the dialog is open."""
from __future__ import annotations

import asyncio
import multiprocessing
from collections import abc
from multiprocessing.connection import Connection
from tkinter import Tk, filedialog
from typing import Protocol

from colorfonts import LoadedFontLibraries, skip_color_fonts

POLL_SECONDS = 0.1

Ask = abc.Callable[[str, str], str]


class Dialog(Protocol):
    """An open folder dialog, as `FolderPicker` uses it."""

    def answer(self) -> str | None:
        """Return the folder chosen, "" when the dialog closed without one, or None while it is open."""
        ...

    def close(self) -> None:
        """End the dialog, also while it is open."""
        ...


def ask_on_top(title: str, start: str) -> str:
    """Show Tk's folder dialog above the other windows and return the folder chosen, or "" on Cancel."""
    skip_color_fonts(LoadedFontLibraries())
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        # tkinter leaves out an option set to None, so Tk opens its default folder
        return filedialog.askdirectory(parent=root, title=title, initialdir=start or None, mustexist=True) or ""
    finally:
        root.destroy()


def send_answer(conn: Connection, ask: Ask, title: str, start: str) -> None:
    """Send the folder that `ask` returns through `conn`, then close it. The child process runs this."""
    with conn:
        conn.send(ask(title, start))


class ChildDialog:
    """A folder dialog that `ask` shows in a child process started with the spawn method."""

    def __init__(self, title: str, start: str, ask: Ask = ask_on_top) -> None:
        context = multiprocessing.get_context("spawn")
        self._conn, sender = context.Pipe(duplex=False)
        # multiprocessing ends a daemon child when the app exits, instead of waiting for the dialog to close
        self._process = context.Process(target=send_answer, args=(sender, ask, title, start), daemon=True)
        self._process.start()
        # the child has its own copy, so the pipe reports its end when the child ends
        sender.close()

    def answer(self) -> str | None:
        """Return the folder the child sent, "" when the child ended without one, or None while it runs."""
        try:
            if not self._conn.poll():
                return None
            return self._conn.recv()
        except (EOFError, BrokenPipeError):
            return ""

    def close(self) -> None:
        """End the child process and wait for it."""
        self._conn.close()
        self._process.kill()
        self._process.join()


class FolderPicker:
    """Opens one folder dialog per call, in the folder that the last dialog returned."""

    def __init__(self, open_dialog: abc.Callable[[str, str], Dialog] = ChildDialog) -> None:
        self._open_dialog = open_dialog
        self._start = ""

    async def choose(self, title: str) -> str:
        """Open a dialog with this title and return the folder chosen, or "" when it closes without one."""
        dialog = self._open_dialog(title, self._start)
        try:
            while (folder := dialog.answer()) is None:
                await asyncio.sleep(POLL_SECONDS)
        finally:
            dialog.close()
        if folder:
            self._start = folder
        return folder
