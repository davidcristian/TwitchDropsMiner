from __future__ import annotations

import sys
import threading
import time

import pytest

from traybackend import CLIENT_MESSAGE, icon_class
from xorgicon import FakeDisplay, FakeXorgIcon, client_message, release_caller, sent_message, wait_until_shown


def sent_messages(count: int) -> None:
    deadline = time.monotonic() + 5
    while sum(connection.closed for connection in FakeDisplay.opened) < count:
        assert time.monotonic() < deadline, f"fewer than {count} messages on new connections within 5 seconds"
        time.sleep(0.01)


def test_a_stop_before_pystray_marks_the_icon_ready_runs_pystrays_stop_in_place_of_the_main_loop():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    icon.stop()
    assert icon.calls == []
    icon._mark_ready()
    icon._mainloop()
    assert icon.calls == ["stop"]


def test_a_stop_after_pystray_marks_the_icon_ready_is_the_stop_of_pystray():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    icon._mark_ready()
    icon.stop()
    icon._mainloop()
    assert (icon.calls, icon._running) == (["stop", "main loop"], False)


def test_the_end_of_the_main_loop_ends_a_change_that_waits_for_the_icon_thread():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    FakeDisplay.opened.clear()
    caller = threading.Thread(target=icon._update_icon)
    caller.start()
    try:
        sent_message()
        icon._mainloop()
        caller.join(5)
        assert not caller.is_alive()
        assert icon.calls == ["main loop"]
    finally:
        release_caller(icon, caller)


def test_a_change_after_the_main_loop_has_ended_returns_at_once_and_sends_no_message():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    icon._mainloop()
    FakeDisplay.opened.clear()
    caller = threading.Thread(target=icon._update_icon)
    caller.start()
    try:
        caller.join(5)
        assert not caller.is_alive()
        assert (icon.calls, FakeDisplay.opened) == (["main loop"], [])
    finally:
        release_caller(icon, caller)


def test_each_waiting_change_gets_the_answer_of_its_own_method():
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    icon.error = ValueError("no tray")
    errors: list[Exception] = []

    def update() -> None:
        try:
            icon._update_icon()
        except ValueError as error:
            errors.append(error)

    FakeDisplay.opened.clear()
    shower = threading.Thread(target=icon._show)
    shower.start()
    updater = threading.Thread(target=update)
    try:
        sent_messages(1)
        updater.start()
        sent_messages(2)
        icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
        updater.join(5)
        shower.join(0.2)
        assert (updater.is_alive(), errors, shower.is_alive()) == (False, [icon.error], True)
        icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__SHOW"))
        shower.join(5)
        assert not shower.is_alive()
    finally:
        release_caller(icon, updater)
        if shower.is_alive():
            icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__SHOW"))
            shower.join(5)


def test_a_change_whose_message_cannot_be_sent_raises_and_the_next_change_gets_its_answer(monkeypatch):
    icon = icon_class(FakeXorgIcon)(dispatched=True)
    monkeypatch.setattr(FakeDisplay, "refusals", 1)
    errors: list[OSError] = []

    def update() -> None:
        try:
            icon._update_icon()
        except ConnectionRefusedError as error:
            errors.append(error)

    refused = threading.Thread(target=update)
    refused.start()
    refused.join(5)
    assert len(errors) == 1
    FakeDisplay.opened.clear()
    caller = threading.Thread(target=icon._update_icon)
    caller.start()
    try:
        sent_message()
        icon._message_handlers[CLIENT_MESSAGE](client_message("_PYSTRAY__UPDATE_ICON"))
        caller.join(5)
        assert not caller.is_alive()
    finally:
        release_caller(icon, caller)


@pytest.mark.parametrize("moment", ["before the run", "as the run starts", "before the show", "after the show"])
def test_a_stop_of_the_xorg_icon_at_any_moment_of_its_start_ends_both_threads_of_pystray(display, moment):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray._xorg
    from PIL import Image
    from Xlib import X, display as xdisplay

    connection = xdisplay.Display()
    tray = connection.screen().root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    tray.set_selection_owner(
        connection.intern_atom(f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"), X.CurrentTime
    )
    connection.flush()
    icon = icon_class(pystray._xorg.Icon)("stop_test", Image.new("RGB", (24, 24)), "Stop test")
    ready, go = threading.Event(), threading.Event()

    def held_setup(icon) -> None:
        # pystray's own setup, held between the mark of the icon ready and the show
        ready.set()
        go.wait()
        icon.visible = True

    thread = threading.Thread(target=icon.run, kwargs={"setup": held_setup if moment == "before the show" else None})
    try:
        if moment == "before the run":
            icon.stop()
        thread.start()
        if moment == "before the show":
            assert ready.wait(5)
            # the setup thread shows the icon only after the icon thread has ended
            threading.Thread(target=lambda: (thread.join(5), go.set()), daemon=True).start()
        elif moment == "after the show":
            wait_until_shown(icon)
            assert icon.visible
        if moment != "before the run":
            icon.stop()
        thread.join(5)
        icon._setup_thread.join(5)
        assert (thread.is_alive(), icon._setup_thread.is_alive()) == (False, False)
    finally:
        go.set()
        tray.destroy()
        connection.close()
