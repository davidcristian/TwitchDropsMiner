from __future__ import annotations

import sys
import threading

import pytest

from traybackend import icon_class
from xorgicon import FakeDisplay, FakeXorgIcon, start_icon


def test_a_message_from_the_xorg_icon_thread_goes_through_the_connection_of_the_icon():
    icon = icon_class(FakeXorgIcon)()
    FakeDisplay.opened.clear()
    icon._send_message("tray", 5, 0, 7)
    assert (icon._display.messages, FakeDisplay.opened) == ([("tray", 5, (0, 7))], [])


def test_a_message_from_another_thread_goes_through_a_new_connection_that_it_syncs_and_closes():
    icon = icon_class(FakeXorgIcon)()
    FakeDisplay.opened.clear()
    sender = threading.Thread(target=icon._send_message, args=("icon", 4))
    sender.start()
    sender.join(5)
    assert icon._display.messages == []
    connections = [(connection.messages, connection.synced, connection.closed) for connection in FakeDisplay.opened]
    assert connections == [([("icon", 4, ())], 1, True)]


def test_a_title_change_from_another_thread_sends_no_request_on_the_connection_of_the_xorg_icon(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    from Xlib import X, display as xdisplay

    connection = xdisplay.Display()
    tray = connection.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    tray.set_selection_owner(
        connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"), X.CurrentTime
    )
    connection.flush()
    icon, thread = start_icon("thread_test")
    try:
        assert icon.visible
        # a change that the icon thread makes after it has handled every earlier event of its window
        icon.title = "Settled"
        serial = icon._display.display.request_serial
        icon.title = "Changed"
        # only the request of the icon thread that sets the window name
        assert (icon._display.display.request_serial - serial) % 65536 == 1
        window = connection.create_resource_object("window", icon._window.id)
        assert window.get_wm_name() == "Changed"
    finally:
        icon.stop()
        thread.join(5)
        tray.destroy()
        connection.close()
