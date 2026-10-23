"""`ConsoleOutput`, the Output box of the Main tab, and `_TKOutputHandler`, which writes the log records to it."""
from __future__ import annotations

import queue
import logging
import threading
import tkinter as tk
from collections import abc
from contextlib import contextmanager
from datetime import datetime
from tkinter import ttk
from typing import TYPE_CHECKING

from translate import _

if TYPE_CHECKING:
    from gui import GUIManager


class _TKOutputHandler(logging.Handler):
    """Writes each log record to the Output box, and queues a record that another thread logs for the Tk thread."""

    def __init__(self, output: GUIManager):
        super().__init__()
        self._output = output
        # _tkinter passes a call from another thread to Tk only while Tk runs mainloop, which the app never calls
        self._tk_thread: int = threading.get_ident()
        self._queued: queue.SimpleQueue[str] = queue.SimpleQueue()

    def emit(self, record: logging.LogRecord) -> None:
        text = self.format(record)
        if threading.get_ident() != self._tk_thread:
            self._queued.put(text)
            return
        # the queued records were logged first, so the Output box keeps the order of the log calls
        self.print_queued()
        self._output.print(text)

    def print_queued(self) -> None:
        """Write the queued records to the Output box. Only the Tk thread calls this."""
        while True:
            try:
                text = self._queued.get_nowait()
            except queue.Empty:
                return
            self._output.print(text)


class ConsoleOutput:
    MAX_LINES = 5000
    LINES = 10
    MIN_LINES = 4

    def __init__(self, manager: GUIManager, master: ttk.Widget):
        frame = ttk.LabelFrame(master, text=_("gui", "output"), padding=(4, 0, 4, 4))
        frame.grid(column=0, row=3, columnspan=3, sticky="nsew", padx=2)
        # tell master frame that the containing row can expand
        master.rowconfigure(3, weight=1)
        frame.rowconfigure(0, weight=1)  # let the frame expand
        frame.columnconfigure(0, weight=1)
        xscroll = ttk.Scrollbar(frame, orient="horizontal")
        yscroll = ttk.Scrollbar(frame, orient="vertical")
        self._text = tk.Text(
            frame,
            width=52,
            height=self.LINES,
            wrap="none",
            state="disabled",
            exportselection=False,
            xscrollcommand=xscroll.set,
            yscrollcommand=yscroll.set,
        )
        xscroll.config(command=self._text.xview)
        yscroll.config(command=self._text.yview)
        self._text.grid(column=0, row=0, sticky="nsew")
        xscroll.grid(column=0, row=1, sticky="ew")
        yscroll.grid(column=1, row=0, sticky="ns")

    def print(self, message: str):
        stamp = datetime.now().strftime("%X")
        if '\n' in message:
            message = message.replace('\n', f"\n{stamp}: ")
        self._text.config(state="normal")
        self._text.insert("end", f"{stamp}: {message}\n")
        # keep the last MAX_LINES lines: "end" is two lines below the last line written
        self._text.delete("1.0", f"end - {self.MAX_LINES + 1} lines")
        self._text.see("end")  # scroll to the newly added line
        self._text.config(state="disabled")

    @contextmanager
    def shortened(self) -> abc.Iterator[None]:
        """Make the Output box request MIN_LINES lines in the block, for the minimum window size."""
        self._text.config(height=self.MIN_LINES)
        try:
            yield
        finally:
            self._text.config(height=self.LINES)

    def configure_theme(self, *, bg: str, fg: str, sel_bg: str, sel_fg: str):
        # Apply colors to the Tk Text widget used for console output
        self._text.config(
            bg=bg,
            fg=fg,
            insertbackground=fg,
            selectbackground=sel_bg,
            selectforeground=sel_fg,
        )
