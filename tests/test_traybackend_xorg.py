from __future__ import annotations

import sys
import threading

import pytest

from traybackend import BUTTON_PRESS_MASK, hides_by_stopping, icon_class
from xorgicon import XORG_EVENTS, FakeXorgIcon, next_event


def test_the_xorg_icon_window_selects_button_press_and_keeps_the_events_pystray_selects():
    icon = icon_class(FakeXorgIcon)()
    assert isinstance(icon, FakeXorgIcon)
    assert icon._window.mask == XORG_EVENTS | BUTTON_PRESS_MASK


@pytest.mark.parametrize("module", ["pystray._appindicator", "pystray._gtk", "pystray._dummy", "pystray._win32"])
def test_the_icon_class_of_another_backend_is_returned_unchanged(module):
    icon = type("Icon", (), {"__module__": module})
    assert icon_class(icon) is icon


@pytest.mark.parametrize(("systray_manager", "calls"), [("tray", []), (None, ["dock"])])
def test_showing_the_xorg_icon_docks_it_only_when_it_is_undocked(systray_manager, calls):
    icon = icon_class(FakeXorgIcon)(systray_manager)
    icon._show()
    assert icon.calls == calls


@pytest.mark.parametrize(
    ("icon_type", "stops"),
    [
        (icon_class(FakeXorgIcon), True),
        (FakeXorgIcon, True),
        (type("Icon", (), {"__module__": "pystray._appindicator"}), False),
        (type("Icon", (), {"__module__": "pystray._gtk"}), False),
        (type("Icon", (), {"__module__": "pystray._win32"}), False),
    ],
)
def test_only_an_icon_of_the_xorg_backend_hides_by_stopping(icon_type, stops):
    assert hides_by_stopping(icon_type()) is stops


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

