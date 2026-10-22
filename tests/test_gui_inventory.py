from __future__ import annotations

import asyncio

import pytest

from constants import PriorityMode
from fakes import GAME, FakeResponse, FakeTwitch, campaign_data, drop_data
from inventory import DropsCampaign


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
