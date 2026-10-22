"""Fakes of pystray's xorg icon and of an X connection, and helpers that run a real X11 icon, for the tray tests."""
from __future__ import annotations

import threading
import time
from functools import partial
from types import SimpleNamespace

import pytest

from traybackend import CLIENT_MESSAGE, XORG_MODULE, icon_class

# ExposureMask and StructureNotifyMask, which pystray 0.19.5 selects on its xorg icon window
XORG_EVENTS = (1 << 15) | (1 << 17)
ATOMS = {"MANAGER": 1, "_NET_SYSTEM_TRAY_S0": 2, "_NET_WM_CM_S0": 3, "_PYSTRAY__SHOW": 4, "_PYSTRAY__UPDATE_ICON": 5}


class FakeWindow:
    def __init__(self) -> None:
        self.mask = XORG_EVENTS
        self.properties: list[tuple[str, str, int, list[int]]] = []

    def get_attributes(self) -> SimpleNamespace:
        return SimpleNamespace(your_event_mask=self.mask)

    def change_attributes(self, *, event_mask: int) -> None:
        self.mask = event_mask

    def change_property(self, name: str, kind: str, size: int, data: list[int]) -> None:
        self.properties.append((name, kind, size, data))


class FakeDisplay:
    opened: list[FakeDisplay] = []

    def __init__(self) -> None:
        self.flushes = 0
        self.messages: list[tuple[str, int, tuple[int, ...]]] = []
        self.synced = 0
        self.closed = False
        self.root = FakeWindow()
        self.root.mask = 0
        FakeDisplay.opened.append(self)

    def flush(self) -> None:
        self.flushes += 1

    def sync(self) -> None:
        self.synced = len(self.messages)

    def close(self) -> None:
        self.closed = True

    def screen(self) -> SimpleNamespace:
        return SimpleNamespace(root=self.root)

    def intern_atom(self, name: str) -> int:
        return ATOMS[name]


class FakeXorgIcon:
    _XEMBED_VERSION = 0
    _XEMBED_MAPPED = 1

    def __init__(self, systray_manager: str | None = None, dispatched: bool = False) -> None:
        self._xembed_info = "_XEMBED_INFO"
        self._display = FakeDisplay()
        self._systray_manager = systray_manager
        self._net_system_tray_sx = ATOMS["_NET_SYSTEM_TRAY_S0"]
        self._thread = threading.current_thread()
        self.calls: list[str] = []
        self.error: Exception | None = None
        self._message_handlers = {CLIENT_MESSAGE: lambda event: self.calls.append(f"pystray {event.client_type}")}
        self._window = self._create_window()
        # pystray's __init__ passes the methods that must run in the icon thread to _rewrite_implementation
        if dispatched:
            self._rewrite_implementation(self._show, self._update_icon)

    def _create_window(self) -> FakeWindow:
        return FakeWindow()

    def _show(self) -> None:
        self.calls.append("dock")

    def _hide(self) -> None:
        self.calls.append("undock")

    def _update_icon(self) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append("dock and draw")

    def _send_message(self, window: str, client_type: int, *data: int) -> None:
        self._display.messages.append((window, client_type, data))


FakeXorgIcon.__module__ = XORG_MODULE


def client_message(client_type: str, selection: str = "_NET_SYSTEM_TRAY_S0") -> SimpleNamespace:
    return SimpleNamespace(client_type=ATOMS[client_type], data=(32, [0, ATOMS[selection], 9, 0, 0]))


def next_event(connection, kind: int):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        while connection.pending_events():
            if (event := connection.next_event()).type == kind:
                return event
        time.sleep(0.01)
    pytest.fail(f"no X event of type {kind} within 10 seconds")


def sent_message() -> list[tuple[str, int, tuple[int, ...]]]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if FakeDisplay.opened and FakeDisplay.opened[0].closed:
            return FakeDisplay.opened[0].messages
        time.sleep(0.01)
    pytest.fail("no message on a new connection within 5 seconds")


def record_uses(uses: list[tuple[str, str]]):
    # Each request goes through send_request, and each flush, sync, wait for a reply and read of events through
    # send_and_recv. A use is the name of its thread and the request class or the keyword of send_and_recv.
    def record(method, *args, **kwargs):
        uses.append((threading.current_thread().name, type(args[0]).__name__ if args else " ".join(kwargs)))
        return method(*args, **kwargs)

    def wrap(icon) -> None:
        connection = icon._display.display
        for name in ("send_request", "send_and_recv"):
            setattr(connection, name, partial(record, getattr(connection, name)))

    return wrap


def start_icon(name: str, prepare=lambda icon: None):
    import pystray._xorg
    from PIL import Image

    icon = icon_class(pystray._xorg.Icon)(name, Image.new("RGB", (24, 24)), name)
    prepare(icon)
    thread = threading.Thread(target=icon.run)
    thread.start()
    deadline = time.monotonic() + 5
    while not icon.visible and time.monotonic() < deadline:
        time.sleep(0.01)
    return icon, thread
