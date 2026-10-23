from __future__ import annotations

import asyncio
import time
import tkinter as tk
from pathlib import Path

from fakedialog import FakeDialogs
from fakes import FakeTwitch
from folderpicker import FolderPicker
import gui as gui_module
from gui import GUIManager


class ScanningTwitch(FakeTwitch):
    """A fake `Twitch` that counts the game scans and the close requests of the window."""

    def __init__(self) -> None:
        super().__init__()
        self.scans = 0
        self.close_requests = 0

    async def detect_games(self) -> None:
        self.scans += 1

    def close(self) -> None:
        self.close_requests += 1


async def until(condition) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.01)


def folder_dialog_run(window, answer: str | None) -> tuple[ScanningTwitch, GUIManager, FakeDialogs, dict]:
    """Press the button that adds a game folder twice, run other tasks, then give the dialog an answer.

    With `answer` None, the window is closed while the dialog is open.
    """
    twitch = ScanningTwitch()
    gui = window(twitch)
    button = gui.settings._game_dir_add_button
    dialogs = FakeDialogs()
    gui.settings._folder_picker = FolderPicker(dialogs)
    seen: dict = {}

    async def scenario() -> None:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        ticker = asyncio.create_task(tick())
        button.invoke()
        button.invoke()
        await until(lambda: ticks >= 20)
        seen["disabled while open"] = button.instate(["disabled"])
        seen["dialogs opened"] = len(dialogs.opened)
        if answer is None:
            gui.close()
        else:
            dialogs.opened[0].folder = answer
        await until(lambda: not button.instate(["disabled"]))
        # the scan task that a new folder starts runs on a later turn of the event loop
        await asyncio.sleep(0.05)
        ticker.cancel()

    asyncio.run(scenario())
    return twitch, gui, dialogs, seen


def test_other_tasks_run_while_the_folder_dialog_is_open_and_the_chosen_folder_is_added(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, "/games/Steam")

    folder = str(Path("/games/Steam"))
    assert seen == {"disabled while open": True, "dialogs opened": 1}
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == [folder]
    assert gui.settings._game_dirs_list.get(0, "end") == (folder,)
    assert twitch.scans == 1


def test_a_cancelled_folder_dialog_adds_no_folder(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, "")

    assert seen == {"disabled while open": True, "dialogs opened": 1}
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == []
    assert gui.settings._game_dirs_list.get(0, "end") == ()
    assert twitch.scans == 0


def test_closing_the_window_closes_an_open_folder_dialog(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, None)

    assert twitch.close_requests == 1
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == []
    assert twitch.scans == 0


def test_the_window_leaves_color_fonts_out_before_tk_starts_when_libxft_is_older_than_2_3_5(window, monkeypatch):
    events: list[str] = []

    class OldXft:
        def xft_version(self) -> int:
            return 20304

        def use_fontconfig_rules(self, rules: bytes) -> bool:
            events.append("rules")
            return True

    class RecordedTk(tk.Tk):
        def __init__(self, *args, **kwargs) -> None:
            events.append("Tk")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gui_module, "LoadedFontLibraries", OldXft)
    monkeypatch.setattr(gui_module, "Tk", RecordedTk)
    window(FakeTwitch())

    assert events == ["rules", "Tk"]


def test_a_cancelled_caller_cancels_the_request_it_waits_for(window):
    gui = window(FakeTwitch())

    async def scenario():
        started = asyncio.Event()

        async def request():
            started.set()
            await asyncio.sleep(3600)

        caller = asyncio.create_task(gui.coro_unless_closed(request()))
        await started.wait()
        caller.cancel()
        await asyncio.gather(caller, return_exceptions=True)
        # a cancelled task ends on a later turn of the event loop
        for _turn in range(3):
            await asyncio.sleep(0)
        others = asyncio.all_tasks() - {asyncio.current_task()}
        return sorted(task.get_coro().__qualname__ for task in others)

    assert asyncio.run(scenario()) == []
