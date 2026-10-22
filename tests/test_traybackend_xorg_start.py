from __future__ import annotations

import sys
import threading

import pytest

from traybackend import CLIENT_MESSAGE, STRUCTURE_NOTIFY_MASK, icon_class
from xorgicon import ATOMS, FakeDisplay, FakeXorgIcon, client_message, next_event, start_icon


def test_the_xorg_icon_receives_the_structure_events_of_the_root_window():
    icon = icon_class(FakeXorgIcon)()
    assert icon._display.root.mask == STRUCTURE_NOTIFY_MASK


@pytest.mark.parametrize(
    ("systray_manager", "selection", "calls"),
    [(None, "_NET_SYSTEM_TRAY_S0", ["dock and draw"]), ("tray", "_NET_SYSTEM_TRAY_S0", []), (None, "_NET_WM_CM_S0", [])],
)
def test_a_tray_that_starts_after_the_xorg_icon_docks_it_only_when_it_is_undocked(systray_manager, selection, calls):
    icon = icon_class(FakeXorgIcon)(systray_manager)
    icon._message_handlers[CLIENT_MESSAGE](client_message("MANAGER", selection))
    assert icon.calls == calls


def test_another_client_message_to_the_xorg_icon_goes_to_the_handler_of_pystray():
    icon = icon_class(FakeXorgIcon)()
    icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__SHOW", "_NET_SYSTEM_TRAY_S0"))
    assert icon.calls == [f"pystray {ATOMS['_PYSTRAY__SHOW']}"]


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


def test_the_xorg_icon_docks_in_a_tray_that_starts_after_it(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    from Xlib import X, display as xdisplay
    from Xlib.protocol import event

    connection = xdisplay.Display()
    root = connection.screen().root
    selection = connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}")
    assert connection.get_selection_owner(selection) == X.NONE
    icon, thread = start_icon("late_tray_test")
    tray = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    try:
        assert icon.visible
        # A tray takes the selection and then announces itself to the clients of the root window.
        tray.set_selection_owner(selection, X.CurrentTime)
        manager = event.ClientMessage(
            window=root, client_type=connection.intern_atom("MANAGER"), data=(32, [X.CurrentTime, selection, tray.id, 0, 0])
        )
        root.send_event(manager, event_mask=X.StructureNotifyMask)
        connection.flush()
        request = next_event(connection, X.ClientMessage)
        assert (request.window, request.data[1][1], request.data[1][2]) == (tray, 0, icon._window.id)
    finally:
        icon.stop()
        thread.join(5)
        tray.destroy()
        connection.close()


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
