"""Fakes of pystray's xorg icon, an X connection and a tray, and helpers that run a real X11 icon, for tray tests."""
from __future__ import annotations

import threading
import time
from functools import partial
from types import SimpleNamespace

import pytest

from traybackend import CLIENT_MESSAGE, XORG_MODULE, icon_class

# ExposureMask and StructureNotifyMask, which pystray 0.19.5 selects on its xorg icon window
XORG_EVENTS = (1 << 15) | (1 << 17)
ATOMS = {
    "MANAGER": 1, "_NET_SYSTEM_TRAY_S0": 2, "_NET_WM_CM_S0": 3, "_PYSTRAY__SHOW": 4, "_PYSTRAY__UPDATE_ICON": 5,
    "_PYSTRAY__STOP": 6,
}


class FakeWindow:
    def __init__(self) -> None:
        self.mask = XORG_EVENTS

    def get_attributes(self) -> SimpleNamespace:
        return SimpleNamespace(your_event_mask=self.mask)

    def change_attributes(self, *, event_mask: int) -> None:
        self.mask = event_mask


class FakeDisplay:
    opened: list[FakeDisplay] = []
    # the number of the next connections that the X server refuses
    refusals = 0

    def __init__(self) -> None:
        if FakeDisplay.refusals:
            FakeDisplay.refusals -= 1
            raise ConnectionRefusedError("the X server refused the connection")
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
    def __init__(self, systray_manager: str | None = None, dispatched: bool = False) -> None:
        self._display = FakeDisplay()
        self._systray_manager = systray_manager
        self._net_system_tray_sx = ATOMS["_NET_SYSTEM_TRAY_S0"]
        self._thread = threading.current_thread()
        self._running = False
        self.calls: list[str] = []
        self.error: Exception | None = None
        self._message_handlers = {CLIENT_MESSAGE: lambda event: self.calls.append(f"pystray {event.client_type}")}
        self._window = self._create_window()
        # pystray's __init__ passes the methods that must run in the icon thread to _rewrite_implementation
        if dispatched:
            self._rewrite_implementation(self._show, self._update_icon, self._stop)

    def _create_window(self) -> FakeWindow:
        return FakeWindow()

    def _show(self) -> None:
        self.calls.append("dock")

    def _update_icon(self) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append("dock and draw")

    def _send_message(self, window: str, client_type: int, *data: int) -> None:
        self._display.messages.append((window, client_type, data))

    # pystray's _run marks the icon ready, which lets the setup thread go on, and then runs the main loop
    def _mark_ready(self) -> None:
        self._running = True

    def _mainloop(self) -> None:
        self.calls.append("main loop")

    def stop(self) -> None:
        if self._running:
            self._stop()
            self._running = False

    def _stop(self) -> None:
        self.calls.append("stop")


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


def release_caller(icon: FakeXorgIcon, caller: threading.Thread) -> None:
    """Answer the change that a caller thread waits for, as the icon thread would, and wait for the caller to end."""
    if caller.is_alive():
        icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
    caller.join(5)


def wait_until_shown(icon) -> None:
    """Wait up to 5 seconds for pystray's setup thread to show a real icon."""
    deadline = time.monotonic() + 5
    while not icon.visible and time.monotonic() < deadline:
        time.sleep(0.01)


def start_icon(name: str, prepare=lambda icon: None):
    import pystray._xorg
    from PIL import Image

    icon = icon_class(pystray._xorg.Icon)(name, Image.new("RGB", (24, 24)), name)
    prepare(icon)
    thread = threading.Thread(target=icon.run)
    thread.start()
    wait_until_shown(icon)
    return icon, thread


def stop_icon(icon, thread: threading.Thread) -> None:
    """Stop a real icon that a thread runs, and wait for the thread to end."""
    icon.stop()
    thread.join(5)


class FakeTray:
    # Embeds the icon of a dock request in a window of its own inside the tray. It ignores the XEmbed mapped flag,
    # as tint2 17.0.1 does. As stalonetray 0.8.1 does, it maps a docked icon window that its client unmaps, maps an
    # icon window that its client moves out of the tray on the root window, and removes a destroyed icon window.
    def __init__(self) -> None:
        from Xlib import X, display as xdisplay

        self.connection = xdisplay.Display()
        # stalonetray ignores the errors of its requests on an icon window that its client has destroyed
        self.connection.set_error_handler(lambda error, request: None)
        self.root = self.connection.screen().root
        self.tray = self.root.create_window(0, 0, 48, 48, 0, X.CopyFromParent)
        self.holder = self.tray.create_window(0, 0, 48, 48, 0, X.CopyFromParent)
        self.opcode = self.connection.intern_atom("_NET_SYSTEM_TRAY_OPCODE")
        self.tray.set_selection_owner(
            self.connection.intern_atom(f"_NET_SYSTEM_TRAY_S{self.connection.get_default_screen()}"), X.CurrentTime
        )
        self.tray.map()
        self.connection.flush()
        self.icon = None
        self.dock_requests = 0

    def handle(self, event) -> None:
        from Xlib import X

        if event.type == X.ClientMessage and event.client_type == self.opcode and event.data[1][1] == 0:
            self.dock_requests += 1
            if self.icon is None:
                self.icon = self.connection.create_resource_object("window", event.data[1][2])
                self.icon.change_attributes(event_mask=X.StructureNotifyMask)
                self.icon.reparent(self.holder, 0, 0)
                self.icon.map()
                self.holder.map()
        elif self.icon is None or event.window.id != self.icon.id:
            return
        elif event.type == X.DestroyNotify:
            self.icon = None
            self.holder.unmap()
        elif event.type == X.UnmapNotify:
            self.icon.map()
        elif event.type == X.ReparentNotify and event.parent.id != self.holder.id:
            self.icon.change_attributes(event_mask=X.NoEventMask)
            self.icon.unmap()
            self.icon.reparent(self.root, 0, 0)
            self.icon.map()
        self.connection.flush()

    def run_until(self, condition) -> None:
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            while self.connection.pending_events():
                self.handle(self.connection.next_event())
            time.sleep(0.01)

    def icon_state(self) -> tuple[str, str]:
        from Xlib import X

        parent = self.icon.query_tree().parent.id
        holder = {self.holder.id: "in the tray", self.root.id: "on the root window"}.get(parent, hex(parent))
        states = {X.IsUnmapped: "unmapped", X.IsUnviewable: "unviewable", X.IsViewable: "viewable"}
        return holder, states[self.icon.get_attributes().map_state]

    def exists(self, window_id: int) -> bool:
        from Xlib.error import BadWindow

        try:
            self.connection.create_resource_object("window", window_id).get_attributes()
        except BadWindow:
            return False
        return True

    def close(self) -> None:
        self.tray.destroy()
        self.connection.close()
