from __future__ import annotations

import asyncio
import tkinter as tk
from tkinter import ttk

import pytest

from channel import Channel
from fakes import GAME, FakeTwitch, campaign_data, drop_data
from gui import GUIManager
from inventory import DropsCampaign


def inventory_tops(gui: GUIManager, sequences: list[str]) -> list[float]:
    """Return the top of the Inventory tab's view, as a fraction of its height, after each event over the tab."""
    if gui._root.tk.call("tk", "windowingsystem") != "x11":
        pytest.skip("only Tk on X11 binds the mouse buttons 4 and 5")
    inventory = gui.inv
    # a frame taller than the tab, so that the tab can scroll
    ttk.Frame(inventory._main_frame, height=5000).grid()
    gui.tabs._nb.select(1)
    gui._root.update()
    inventory._canvas_update()
    tops = []
    for sequence in sequences:
        inventory._canvas.event_generate(sequence)
        tops.append(inventory._canvas.yview()[0])
    return tops


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
def test_the_minimum_window_size_is_the_size_of_the_current_theme(window, dark):
    fake = FakeTwitch()
    fake.settings.dark_mode = dark
    gui = window(fake)
    root = gui._root

    def minimum_and_requested() -> tuple[tuple[int, int], tuple[int, int]]:
        root.update_idletasks()
        return root.minsize(), (root.winfo_reqwidth(), root.winfo_reqheight())

    at_start = minimum_and_requested()
    gui.apply_theme(not dark)
    after_the_change = minimum_and_requested()

    assert at_start[0] == at_start[1]
    assert after_the_change[0] == after_the_change[1]


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
