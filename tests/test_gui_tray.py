from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from fakes import FakeTwitch
import gui as gui_module
from traybackend import XORG_MODULE
from xorgicon import FakeTray


class FakeIcon:
    def __init__(self, visible: bool) -> None:
        self.visible = visible
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


@pytest.mark.parametrize(
    ("module", "shown", "kept", "visible", "stopped"),
    [
        ("pystray._appindicator", True, True, False, False),
        ("pystray._gtk", True, True, False, False),
        ("pystray._win32", True, True, False, False),
        (XORG_MODULE, True, False, True, True),
        (XORG_MODULE, False, False, False, True),
    ],
)
def test_restoring_the_window_stops_an_x11_tray_icon_and_hides_the_icon_of_another_backend(
    window, module, shown, kept, visible, stopped
):
    gui = window(FakeTwitch())
    icon = type("Icon", (FakeIcon,), {"__module__": module})(shown)
    gui.tray.icon = icon

    gui.tray.restore()

    assert (gui.tray.icon is icon, icon.visible, icon.stopped) == (kept, visible, stopped)
    assert gui._root.state() == "normal"


def test_restoring_the_window_removes_the_x11_tray_icon_from_the_tray_and_minimizing_docks_a_new_one(
    window, monkeypatch
):
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray
    import pystray._xorg

    xorg = SimpleNamespace(Icon=pystray._xorg.Icon, Menu=pystray.Menu, MenuItem=pystray.MenuItem)
    monkeypatch.setattr(gui_module, "pystray", xorg)
    gui = window(FakeTwitch())
    tray = FakeTray()
    docked = ("in the tray", "viewable")

    def shown() -> bool:
        return gui.tray.icon.visible and tray.icon is not None and tray.icon_state() == docked

    async def minimize_and_restore() -> list[tuple[int, bool, bool]]:
        rounds = []
        try:
            for _ in range(2):
                gui.tray.minimize()
                tray.run_until(shown)
                assert shown()
                window_id = tray.icon.id
                gui.tray.restore()
                tray.run_until(lambda: tray.icon is None)
                rounds.append((window_id, gui.tray.icon is None, tray.exists(window_id)))
        finally:
            gui.tray.stop()
            tray.close()
        return rounds

    first, second = asyncio.run(minimize_and_restore())

    assert first[0] != second[0]
    assert first[1:] == second[1:] == (True, False)
    assert tray.dock_requests == 2


@pytest.mark.parametrize("action", ["restore", "stop"])
def test_a_restore_or_a_stop_right_after_a_minimize_ends_both_threads_of_the_x11_tray_icon(window, monkeypatch, action):
    # A stop is what GUIManager.close_window does, as after a SIGTERM.
    if sys.platform != "linux":
        pytest.skip("pystray uses its xorg backend on Linux")
    import pystray
    import pystray._xorg

    xorg = SimpleNamespace(Icon=pystray._xorg.Icon, Menu=pystray.Menu, MenuItem=pystray.MenuItem)
    monkeypatch.setattr(gui_module, "pystray", xorg)
    gui = window(FakeTwitch())

    async def minimize_and_stop():
        gui.tray.minimize()
        icon = gui.tray.icon
        getattr(gui.tray, action)()
        # the executor runs the icon thread, and its shutdown waits for that thread to end
        await asyncio.wait_for(asyncio.get_running_loop().shutdown_default_executor(), 10)
        return icon

    # asyncio.run would wait 300 seconds for an icon thread that runs on, and close does not
    loop = asyncio.new_event_loop()
    try:
        icon = loop.run_until_complete(minimize_and_stop())
    finally:
        loop.close()

    icon._setup_thread.join(5)
    assert (gui.tray.icon, icon._setup_thread.is_alive()) == (None, False)
