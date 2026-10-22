"""Fakes of pystray's xorg icon and of an X connection, and helpers that run a real X11 icon, for the tray tests."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from traybackend import CLIENT_MESSAGE, XORG_MODULE, icon_class

# ExposureMask and StructureNotifyMask, which pystray 0.19.5 selects on its xorg icon window
XORG_EVENTS = (1 << 15) | (1 << 17)
ATOMS = {"MANAGER": 1, "_NET_SYSTEM_TRAY_S0": 2, "_NET_WM_CM_S0": 3, "_PYSTRAY__SHOW": 4}


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

    def __init__(self, systray_manager: str | None = None) -> None:
        self._xembed_info = "_XEMBED_INFO"
        self._display = FakeDisplay()
        self._systray_manager = systray_manager
        self._net_system_tray_sx = ATOMS["_NET_SYSTEM_TRAY_S0"]
        self._thread = threading.current_thread()
        self.calls: list[str] = []
        self._message_handlers = {CLIENT_MESSAGE: lambda event: self.calls.append(f"pystray {event.client_type}")}
        self._window = self._create_window()

    def _create_window(self) -> FakeWindow:
        return FakeWindow()

    def _show(self) -> None:
        self.calls.append("dock")

    def _hide(self) -> None:
        self.calls.append("undock")

    def _update_icon(self) -> None:
        self.calls.append("dock and draw")

    def _send_message(self, window: str, client_type: int, *data: int) -> None:
        self._display.messages.append((window, client_type, data))


FakeXorgIcon.__module__ = XORG_MODULE


def client_message(client_type: str, selection: str) -> SimpleNamespace:
    return SimpleNamespace(client_type=ATOMS[client_type], data=(32, [0, ATOMS[selection], 9, 0, 0]))


def next_event(connection, kind: int):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        while connection.pending_events():
            if (event := connection.next_event()).type == kind:
                return event
        time.sleep(0.01)
    pytest.fail(f"no X event of type {kind} within 10 seconds")


def start_icon(name: str):
    import pystray._xorg
    from PIL import Image

    icon = icon_class(pystray._xorg.Icon)(name, Image.new("RGB", (24, 24)), name)
    thread = threading.Thread(target=icon.run)
    thread.start()
    deadline = time.monotonic() + 5
    while not icon.visible and time.monotonic() < deadline:
        time.sleep(0.01)
    return icon, thread
