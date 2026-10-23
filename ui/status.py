"""`StatusBar` and `WebsocketStatus`, the panels of the Main tab that show what the app and its websockets do."""
from __future__ import annotations

from math import log10, ceil
from tkinter import ttk, StringVar
from typing import TypedDict, TYPE_CHECKING

from translate import _
from constants import MAX_WEBSOCKETS, WS_TOPICS_LIMIT

if TYPE_CHECKING:
    from gui import GUIManager


DIGITS = ceil(log10(WS_TOPICS_LIMIT))


class StatusBar:
    def __init__(self, manager: GUIManager, master: ttk.Widget):
        frame = ttk.LabelFrame(master, text=_("gui", "status", "name"), padding=(4, 0, 4, 4))
        frame.grid(column=0, row=0, columnspan=3, sticky="nsew", padx=2)
        self._label = ttk.Label(frame)
        self._label.grid(column=0, row=0, sticky="nsew")

    def update(self, text: str):
        self._label.config(text=text)

    def clear(self):
        self._label.config(text='')


class _WSEntry(TypedDict):
    status: str
    topics: int


class WebsocketStatus:
    def __init__(self, manager: GUIManager, master: ttk.Widget):
        frame = ttk.LabelFrame(master, text=_("gui", "websocket", "name"), padding=(4, 0, 4, 4))
        frame.grid(column=0, row=1, sticky="nsew", padx=2)
        self._status_var = StringVar(frame)
        self._topics_var = StringVar(frame)
        ttk.Label(
            frame,
            text='\n'.join(
                _("gui", "websocket", "websocket").format(id=i)
                for i in range(1, MAX_WEBSOCKETS + 1)
            ),
            style="MS.TLabel",
        ).grid(column=0, row=0)
        ttk.Label(
            frame,
            textvariable=self._status_var,
            width=16,
            justify="left",
            style="MS.TLabel",
        ).grid(column=1, row=0)
        ttk.Label(
            frame,
            textvariable=self._topics_var,
            width=(DIGITS * 2 + 1),
            justify="right",
            style="MS.TLabel",
        ).grid(column=2, row=0)
        self._items: dict[int, _WSEntry | None] = {i: None for i in range(MAX_WEBSOCKETS)}
        self._update()

    def update(self, idx: int, status: str | None = None, topics: int | None = None):
        if status is None and topics is None:
            raise TypeError("You need to provide at least one of: status, topics")
        entry = self._items.get(idx)
        if entry is None:
            entry = self._items[idx] = _WSEntry(
                status=_("gui", "websocket", "disconnected"), topics=0
            )
        if status is not None:
            entry["status"] = status
        if topics is not None:
            entry["topics"] = topics
        self._update()

    def remove(self, idx: int):
        if idx in self._items:
            del self._items[idx]
            self._update()

    def _update(self):
        status_lines: list[str] = []
        topic_lines: list[str] = []
        for idx in range(MAX_WEBSOCKETS):
            if (item := self._items.get(idx)) is None:
                status_lines.append('')
                topic_lines.append('')
            else:
                status_lines.append(item["status"])
                topic_lines.append(f"{item['topics']:>{DIGITS}}/{WS_TOPICS_LIMIT}")
        self._status_var.set('\n'.join(status_lines))
        self._topics_var.set('\n'.join(topic_lines))
