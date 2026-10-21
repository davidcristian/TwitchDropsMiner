from __future__ import annotations

import asyncio
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pytest

from channel import Channel
from fakedialog import FakeDialogs
from fakes import GAME, FakeTwitch, campaign_data, drop_data
from folderpicker import FolderPicker
from gui import GUIManager
from inventory import DropsCampaign


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


def inventory_tops(gui: GUIManager, sequences: list[str]) -> list[float]:
    """Return the top of the Inventory tab's view, as a fraction of its height, after each event over the tab."""
    if gui._root.tk.call("tk", "windowingsystem") != "x11":
        pytest.skip("only Tk on X11 binds the mouse buttons 4 and 5")
    inventory = gui.inv
    # a frame taller than the tab, so that the tab can scroll
    ttk.Frame(inventory._main_frame, height=5000).grid()
    gui.tabs._nb.select(1)
    gui._root.update()
    inventory._area.update_region()
    tops = []
    for sequence in sequences:
        inventory._area.canvas.event_generate(sequence)
        tops.append(inventory._area.canvas.yview()[0])
    return tops


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


def test_a_channel_added_again_is_the_object_that_the_selection_returns(window):
    fake = FakeTwitch()
    channels = window(fake).channels
    old, new = Channel(fake, id=1, login="c1"), Channel(fake, id=1, login="c1")
    channels.display(old, add=True)
    channels.display(new, add=True)
    channels.set_selection(new)

    assert channels.get_selection() is new


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


def test_the_output_box_keeps_the_last_5000_lines(window):
    gui = window(FakeTwitch())
    for number in range(5003):
        gui.print(f"line {number}")

    lines = gui.output._text.get("1.0", "end-1c").splitlines()
    assert len(lines) == 5000
    assert [line.rpartition(": ")[2] for line in (lines[0], lines[-1])] == ["line 3", "line 5002"]


def test_the_tray_title_keeps_the_line_break_after_a_shortened_game_name(window):
    fake = FakeTwitch()
    campaign = DropsCampaign(fake, campaign_data([drop_data("d1")], game={**GAME, "name": "N" * 100}), {})

    title = window(fake).tray.get_title(campaign.timed_drops["d1"])

    # a tray title has at most 127 characters, so the game name is cut to fit
    assert title.split("\n") == ["Twitch Drops Miner", "N" * 84 + "...", "Reward d1 0.0% (0/1)"]


@pytest.mark.parametrize("dark", [False, True])
def test_the_minimum_window_size_is_the_size_of_the_current_theme_without_the_settings_tab(window, dark):
    fake = FakeTwitch()
    fake.settings.dark_mode = dark
    gui = window(fake)
    root, notebook = gui._root, gui.tabs._nb

    def minimum_and_requested_without_settings() -> tuple[tuple[int, int], tuple[int, int]]:
        pane, text = notebook.tabs()[2], notebook.tab(2, "text")
        notebook.forget(2)
        root.update_idletasks()
        requested = (root.winfo_reqwidth(), root.winfo_reqheight())
        notebook.insert(2, pane, text=text, sticky="nsew")
        return root.minsize(), requested

    at_start = minimum_and_requested_without_settings()
    gui.apply_theme(not dark)
    after_the_change = minimum_and_requested_without_settings()

    assert at_start[0] == at_start[1]
    assert after_the_change[0] == after_the_change[1]


def test_the_whole_main_tab_shows_at_the_minimum_window_size_after_a_long_channel_name(window):
    fake = FakeTwitch()
    gui = window(fake)
    root, main = gui._root, gui.tabs._nb.nametowidget(gui.tabs._nb.tabs()[0])
    root.update()
    width = main.winfo_reqwidth()

    async def scenario() -> None:
        gui.start()
        gui.channels.display(Channel(fake, id=1, login="c" * 30), add=True)
        # the poll task lays out the window and checks the minimum size in one step
        await until(lambda: main.winfo_reqwidth() > width)
        gui.stop()

    asyncio.run(scenario())
    root.geometry("{}x{}".format(*root.minsize()))
    root.update()

    assert main.winfo_width() >= main.winfo_reqwidth()


def test_setting_the_theme_again_does_not_resize_a_window_that_follows_its_requested_size(window):
    gui = window(FakeTwitch())
    root = gui._root
    root.geometry("")
    root.update()
    resizes = []
    root.bind("<Configure>", lambda event: event.widget is root and resizes.append((event.width, event.height)))
    gui.apply_theme(False)
    root.update()

    assert resizes == []


def test_the_window_opens_at_its_requested_size_cut_to_the_largest_size_tk_allows(window):
    root = window(FakeTwitch())._root
    root.update()
    largest = root.maxsize()

    assert (root.winfo_width(), root.winfo_height()) == (
        min(root.winfo_reqwidth(), largest[0]),
        min(root.winfo_reqheight(), largest[1]),
    )


def test_the_settings_tab_in_a_small_window_scrolls_to_the_end_of_its_content(window):
    gui = window(FakeTwitch())
    root, area = gui._root, gui.settings._area
    root.minsize(1, 1)
    root.geometry("700x400")
    gui.tabs._nb.select(2)
    root.update()
    canvas, content = area.canvas, (area.inner.winfo_reqwidth(), area.inner.winfo_reqheight())
    canvas.xview_moveto(1)
    canvas.yview_moveto(1)
    root.update()
    button = gui.settings._game_dir_add_button
    corner = (button.winfo_rootx() + button.winfo_width(), button.winfo_rooty() + button.winfo_height())

    assert canvas.cget("scrollregion") == f"0 0 {content[0]} {content[1]}"
    assert (canvas.canvasx(canvas.winfo_width()), canvas.canvasy(canvas.winfo_height())) == content
    assert canvas.winfo_rootx() < corner[0] <= canvas.winfo_rootx() + canvas.winfo_width()
    assert canvas.winfo_rooty() < corner[1] <= canvas.winfo_rooty() + canvas.winfo_height()


@pytest.mark.skipif(tk.TkVersion >= 9, reason="Tk 9 sends a wheel turn on X11 as <MouseWheel>")
def test_the_wheel_buttons_of_x11_scroll_the_inventory_tab_under_the_pointer(window):
    gui = window(FakeTwitch())

    tops = inventory_tops(gui, ["<Enter>", "<Button-5>", "<Button-5>", "<Button-4>", "<Leave>", "<Button-5>"])

    start, down, down_twice, up, left, after_leaving = tops
    assert start == 0 < down < down_twice
    assert up < down_twice
    assert after_leaving == left == up


@pytest.mark.skipif(tk.TkVersion < 9, reason="Tk 8.6 on X11 sends a wheel turn as a press of button 4 or 5")
@pytest.mark.xfail(strict=True, reason="docs/refinements/tasks/052-tk-9-back-button-scrolls-inventory.md")
def test_the_back_button_does_not_scroll_the_inventory_tab(window):
    gui = window(FakeTwitch())

    assert inventory_tops(gui, ["<Enter>", "<Button-4>"]) == [0.0, 0.0]
