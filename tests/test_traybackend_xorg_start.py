from __future__ import annotations

import sys
import threading

import pytest

from traybackend import CLIENT_MESSAGE, STRUCTURE_NOTIFY_MASK, icon_class
from xorgicon import (
    ATOMS, FakeDisplay, FakeXorgIcon, client_message, next_event, record_uses, sent_message, start_icon,
)


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


def test_a_change_in_the_icon_thread_runs_at_once_and_opens_no_connection():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    FakeDisplay.opened.clear()
    icon._update_icon()
    assert (icon.calls, FakeDisplay.opened) == (["dock and draw"], [])


def test_a_change_from_another_thread_sends_its_message_on_a_new_connection_and_waits_for_the_icon_thread():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    FakeDisplay.opened.clear()
    caller = threading.Thread(target=icon._update_icon)
    caller.start()
    assert sent_message() == [(icon._window, ATOMS["_PYSTRAY__UPDATE_ICON"], ())]
    icon._message_handlers[CLIENT_MESSAGE](client_message("_NET_WM_CM_S0"))
    caller.join(0.2)
    assert caller.is_alive()
    assert (icon.calls, icon._display.flushes, icon._display.messages) == ([], 0, [])
    icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
    caller.join(5)
    assert not caller.is_alive()
    assert icon.calls == ["dock and draw"]


def test_an_error_of_a_change_in_the_icon_thread_is_raised_in_the_thread_that_made_it():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    icon.error = ValueError("no tray")
    errors: list[Exception] = []

    def update() -> None:
        try:
            icon._update_icon()
        except ValueError as error:
            errors.append(error)

    FakeDisplay.opened.clear()
    caller = threading.Thread(target=update)
    caller.start()
    sent_message()
    icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
    caller.join(5)
    assert errors == [icon.error]


def test_a_change_before_pystray_sets_the_icon_thread_waits_for_the_icon_thread():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    # pystray's _run marks the icon ready, which lets the setup thread go on, before it sets _thread
    del icon._thread
    errors: list[AttributeError] = []

    def update() -> None:
        try:
            icon._update_icon()
        except AttributeError as error:
            errors.append(error)

    FakeDisplay.opened.clear()
    caller = threading.Thread(target=update)
    caller.start()
    caller.join(0.5)
    assert errors == []
    assert sent_message() == [(icon._window, ATOMS["_PYSTRAY__UPDATE_ICON"], ())]
    icon._thread = threading.current_thread()
    icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
    caller.join(5)
    assert icon.calls == ["dock and draw"]


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


def test_only_the_icon_thread_uses_the_connection_of_the_xorg_icon_from_its_start_to_its_stop(display):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    from PIL import Image
    from Xlib import X, display as xdisplay

    connection = xdisplay.Display()
    tray = connection.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    tray.set_selection_owner(
        connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"), X.CurrentTime
    )
    connection.flush()
    uses: list[tuple[str, str]] = []
    icon, thread = start_icon("connection_test", record_uses(uses))
    try:
        assert icon.visible
        icon.visible = False
        icon.visible = True
        icon.icon = Image.new("RGB", (24, 24), "red")
        icon.title = "Changed"
    finally:
        icon.stop()
        thread.join(5)
        tray.destroy()
        connection.close()
    assert not thread.is_alive()
    assert [use for use in uses if use[0] != thread.name] == []
    # the image is drawn and the window destroyed on this connection, so the record sees its requests
    assert {(thread.name, "GetGeometry"), (thread.name, "DestroyWindow")} <= set(uses)
