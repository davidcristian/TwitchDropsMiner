from __future__ import annotations

import sys
import threading
import time

import pytest

from traybackend import BUTTON_PRESS_MASK, icon_class
from xorgicon import XORG_EVENTS, FakeXorgIcon, next_event


def test_the_xorg_icon_window_selects_button_press_and_keeps_the_events_pystray_selects():
    icon = icon_class(FakeXorgIcon)()
    assert isinstance(icon, FakeXorgIcon)
    assert icon._window.mask == XORG_EVENTS | BUTTON_PRESS_MASK


@pytest.mark.parametrize("module", ["pystray._appindicator", "pystray._gtk", "pystray._dummy", "pystray._win32"])
def test_the_icon_class_of_another_backend_is_returned_unchanged(module):
    icon = type("Icon", (), {"__module__": module})
    assert icon_class(icon) is icon


def test_hiding_the_docked_xorg_icon_clears_its_xembed_mapped_flag_and_keeps_it_docked():
    icon = icon_class(FakeXorgIcon)("tray")
    icon._hide()
    assert icon._window.properties == [("_XEMBED_INFO", "_XEMBED_INFO", 32, [0, 0])]
    assert (icon._display.flushes, icon.calls, icon._systray_manager) == (1, [], "tray")


@pytest.mark.parametrize(("systray_manager", "calls"), [("tray", []), (None, ["dock"])])
def test_showing_the_xorg_icon_sets_its_xembed_mapped_flag_and_docks_it_only_when_undocked(systray_manager, calls):
    icon = icon_class(FakeXorgIcon)(systray_manager)
    icon._show()
    assert icon._window.properties == [("_XEMBED_INFO", "_XEMBED_INFO", 32, [0, 1])]
    assert (icon._display.flushes, icon.calls) == (1, calls)


def test_a_left_click_on_the_docked_xorg_icon_runs_the_default_menu_item_and_a_right_click_nothing(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray._xorg
    from PIL import Image
    from Xlib import X, display as xdisplay
    from Xlib.protocol import event

    # The test owns the system tray selection, as a tray does, so pystray sends it the dock request of the icon.
    connection = xdisplay.Display()
    root = connection.screen().root
    tray = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    tray.set_selection_owner(
        connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"), X.CurrentTime
    )
    connection.flush()
    clicks: list[str] = []
    shown = threading.Event()

    def show() -> None:
        clicks.append("show")
        shown.set()

    menu = pystray.Menu(pystray.MenuItem("Show", show, default=True))
    icon = icon_class(pystray._xorg.Icon)("click_test", Image.new("RGB", (24, 24)), "Click test", menu)
    thread = threading.Thread(target=icon.run)
    thread.start()
    try:
        window = connection.create_resource_object("window", next_event(connection, X.ClientMessage).data[1][2])
        for button in (3, 1):
            press = event.ButtonPress(
                time=X.CurrentTime, root=root, window=window, child=X.NONE, root_x=0, root_y=0, event_x=0,
                event_y=0, state=0, same_screen=1, detail=button,
            )
            window.send_event(press, event_mask=X.ButtonPressMask)
        connection.flush()
        assert shown.wait(5)
        assert clicks == ["show"]
    finally:
        icon.stop()
        thread.join(5)
        tray.destroy()
        connection.close()


class FakeStalonetray:
    # Embeds an icon as stalonetray 0.8.1 does: in a window of its own inside the tray, which it unmaps while the
    # icon's XEmbed mapped flag is clear. It maps a docked icon window that its client unmaps, and maps an icon
    # window that its client moves out of the tray on the root window.
    def __init__(self) -> None:
        from Xlib import X, display as xdisplay

        self.connection = xdisplay.Display()
        self.root = self.connection.screen().root
        self.tray = self.root.create_window(0, 0, 48, 48, 0, X.CopyFromParent)
        self.holder = self.tray.create_window(0, 0, 48, 48, 0, X.CopyFromParent)
        self.xembed_info = self.connection.intern_atom("_XEMBED_INFO")
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
                self.icon.change_attributes(event_mask=X.StructureNotifyMask | X.PropertyChangeMask)
                self.icon.reparent(self.holder, 0, 0)
                self.icon.map()
                self.holder.map()
        elif self.icon is None or event.window.id != self.icon.id:
            return
        elif event.type == X.UnmapNotify:
            self.icon.map()
        elif event.type == X.ReparentNotify and event.parent.id != self.holder.id:
            self.icon.change_attributes(event_mask=X.NoEventMask)
            self.icon.unmap()
            self.icon.reparent(self.root, 0, 0)
            self.icon.map()
        elif event.type == X.PropertyNotify and event.atom == self.xembed_info:
            flags = self.icon.get_full_property(self.xembed_info, self.xembed_info).value[1]
            (self.holder.map if flags & 1 else self.holder.unmap)()
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


def test_the_xorg_icon_hides_and_shows_in_a_tray_that_maps_windows_as_stalonetray_does(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray._xorg
    from PIL import Image

    tray = FakeStalonetray()
    icon = icon_class(pystray._xorg.Icon)("hide_test", Image.new("RGB", (24, 24)), "Hide test")
    thread = threading.Thread(target=icon.run)
    thread.start()
    try:
        shown = ("in the tray", "viewable")
        tray.run_until(lambda: icon.visible and tray.icon is not None and tray.icon_state() == shown)
        assert tray.icon_state() == shown
        icon.visible = False
        tray.run_until(lambda: tray.icon_state() == ("in the tray", "unviewable"))
        assert tray.icon_state() == ("in the tray", "unviewable")
        icon.visible = True
        tray.run_until(lambda: tray.icon_state() == shown)
        assert tray.icon_state() == shown
        assert tray.dock_requests == 1
    finally:
        icon.stop()
        thread.join(5)
        tray.tray.destroy()
        tray.connection.close()
