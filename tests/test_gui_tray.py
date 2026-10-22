from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from fakes import FakeTwitch
import gui as gui_module
from traybackend import XORG_MODULE
from xorgicon import FakeTray, wait_until_shown


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
        (XORG_MODULE, False, True, False, False),
    ],
)
def test_restoring_the_window_stops_a_shown_x11_tray_icon_and_hides_the_icon_of_another_backend(
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
            # a stop before pystray's setup thread shows the icon leaves that thread waiting forever
            if gui.tray.icon is not None:
                wait_until_shown(gui.tray.icon)
            gui.tray.stop()
            tray.close()
        return rounds

    first, second = asyncio.run(minimize_and_restore())

    assert first[0] != second[0]
    assert first[1:] == second[1:] == (True, False)
    assert tray.dock_requests == 2
