from __future__ import annotations

import asyncio
import tkinter as tk
from tkinter import ttk

import pytest

from constants import PriorityMode
from fakes import GAME, FakeResponse, FakeTwitch, campaign_data, drop_data
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
    inventory._area.update_region()
    tops = []
    for sequence in sequences:
        inventory._area.canvas.event_generate(sequence)
        tops.append(inventory._area.canvas.yview()[0])
    return tops


def shown(window, *, priority=(), exclude=(), detected=(), mode=PriorityMode.PRIORITY_ONLY, excluded_filter=False):
    """Return whether the Inventory tab shows an active campaign of `GAME` after a refresh."""
    fake = FakeTwitch(http=lambda method, url: FakeResponse(404))
    fake.settings.priority = list(priority)
    fake.settings.exclude = set(exclude)
    fake.settings.detected_games = list(detected)
    fake.settings.priority_mode = mode
    inventory = window(fake).inv
    campaign = DropsCampaign(fake, campaign_data([drop_data("d1")]), {})
    asyncio.run(inventory.add_campaign(campaign))
    inventory._filters["excluded"].set(int(excluded_filter))
    inventory.refresh()
    return inventory._campaigns[campaign]["frame"].winfo_manager() == "grid"


@pytest.mark.parametrize(
    ("lists", "expected"),
    [
        ({}, False),
        ({"detected": [GAME["name"]]}, True),
        ({"priority": [GAME["name"]]}, True),
        ({"priority": ["Gam?"]}, True),
        ({"detected": ["Other Game"]}, False),
        ({"detected": [GAME["name"]], "exclude": [GAME["name"]]}, False),
        ({"priority": [GAME["name"]], "exclude": [GAME["name"]]}, False),
        ({"mode": PriorityMode.ENDING_SOONEST}, True),
        ({"mode": PriorityMode.LOW_AVBL_FIRST}, True),
        ({"mode": PriorityMode.ENDING_SOONEST, "exclude": ["G*"]}, False),
        ({"mode": PriorityMode.ENDING_SOONEST, "priority": [GAME["name"]], "exclude": [GAME["name"]]}, False),
    ],
)
def test_without_the_excluded_filter_the_inventory_tab_shows_a_campaign_whose_game_the_lists_let_the_miner_mine(
    window, lists, expected
):
    assert shown(window, **lists) is expected


@pytest.mark.parametrize(
    "lists",
    [{}, {"exclude": [GAME["name"]]}, {"priority": [GAME["name"]], "exclude": [GAME["name"]]}],
)
def test_the_excluded_filter_shows_a_campaign_whatever_the_lists_hold(window, lists):
    assert shown(window, excluded_filter=True, **lists) is True


@pytest.mark.skipif(tk.TkVersion >= 9, reason="Tk 9 sends a wheel turn on X11 as <MouseWheel>")
def test_the_wheel_buttons_of_x11_scroll_the_inventory_tab_under_the_pointer(window):
    gui = window(FakeTwitch())

    tops = inventory_tops(gui, ["<Enter>", "<Button-5>", "<Button-5>", "<Button-4>", "<Leave>", "<Button-5>"])

    start, down, down_twice, up, left, after_leaving = tops
    assert start == 0 < down < down_twice
    assert up < down_twice
    assert after_leaving == left == up


@pytest.mark.skipif(tk.TkVersion < 9, reason="Tk 8.6 on X11 sends a wheel turn as a press of button 4 or 5")
def test_the_back_and_forward_buttons_do_not_scroll_the_inventory_tab(window):
    gui = window(FakeTwitch())

    # Tk 9 on X11 reports the back and forward buttons as 4 and 5
    assert inventory_tops(gui, ["<Enter>", "<Button-4>", "<Button-5>"]) == [0.0, 0.0, 0.0]
