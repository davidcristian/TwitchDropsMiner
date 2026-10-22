from __future__ import annotations

import asyncio
from typing import Any

import pytest

from constants import JsonType, State
from exceptions import ReloadRequest
from fakes import (
    GAME,
    NO_CAMPAIGNS,
    FakeChannelList,
    FakeTwitch,
    HeldAnswer,
    campaign_data,
    directory,
    drop_data,
    gql_answers,
    inventory,
)
from livetwitch import run_with_fast_clock
from ratelimit import RateLimiter
from test_twitch_run import run_fake, start_run, until, waits
from translate import _


@pytest.mark.parametrize("requested, sent_after", [
    (State.INVENTORY_FETCH, ["Inventory", "Campaigns", "GameDirectory"]),
    (State.GAMES_UPDATE, ["GameDirectory"]),
])
def test_a_state_requested_during_the_channel_fetch_runs_after_it(live_twitch, requested, sent_after):
    async def scenario():
        def request_during_the_request(op: JsonType) -> JsonType:
            twitch.change_state(requested)
            return directory((1, 1000))

        fake = run_fake(directory((1, 1000)), request_during_the_request, directory((1, 1000)))
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await start_run(twitch)
        # the stream refresh of the maintenance task
        twitch.change_state(State.CHANNELS_CLEANUP)
        await asyncio.sleep(2)
        await until(lambda: waits(twitch))
        return fake

    fake = run_with_fast_clock(scenario())

    assert fake.gql_sent == ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken", "GameDirectory", *sent_after]


@pytest.mark.parametrize("requested", [[State.RESTART], [State.RESTART, State.INVENTORY_FETCH]])
def test_a_restart_requested_during_the_inventory_fetch_ends_the_run_after_it(live_twitch, requested):
    async def scenario():
        def campaigns(op: JsonType) -> JsonType:
            for state in requested:
                twitch.change_state(state)
            return NO_CAMPAIGNS

        fake = FakeTwitch(gql=gql_answers(Inventory=inventory([]), Campaigns=campaigns))
        twitch = live_twitch(fake)
        with pytest.raises(ReloadRequest):
            await asyncio.wait_for(twitch._run(), 30)
        return fake

    fake = run_with_fast_clock(scenario())

    assert fake.gql_sent == ["Inventory", "Campaigns"]
    assert fake.printed == []


def test_a_reload_requested_during_the_inventory_fetch_is_merged_into_it(live_twitch):
    async def scenario():
        def campaigns(op: JsonType) -> JsonType:
            # the Reload button, pressed once
            if fake.gql_sent.count("Campaigns") == 1:
                twitch.change_state(State.INVENTORY_FETCH)
            return NO_CAMPAIGNS

        fake = FakeTwitch(gql=gql_answers(Inventory=inventory([]), Campaigns=campaigns))
        twitch = live_twitch(fake)
        run = asyncio.create_task(twitch._run())
        await asyncio.sleep(30)
        return fake, run.done(), waits(twitch)

    fake, ended, waiting = run_with_fast_clock(scenario())

    assert (ended, waiting) == (False, True)
    assert fake.gql_sent == ["Inventory", "Campaigns"]


def test_a_channel_switch_requested_during_the_inventory_fetch_lets_the_reload_go_on_to_the_channel_fetch(
    live_twitch,
):
    async def scenario():
        def campaigns(op: JsonType) -> JsonType:
            twitch.change_state(State.CHANNEL_SWITCH)
            return NO_CAMPAIGNS

        fake = FakeTwitch(gql=gql_answers(
            Inventory=inventory([campaign_data([drop_data("d1")])]),
            Campaigns=campaigns,
            GameDirectory=directory((1, 1000)),
            PlaybackAccessToken=HeldAnswer({}),
        ))
        fake.settings.priority = [GAME["name"]]
        twitch = live_twitch(fake)
        await start_run(twitch)
        return fake, twitch

    fake, twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[1]
    assert fake.gql_sent == ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken"]


class SelectingChannelList(FakeChannelList):
    """The channel list with a selected row. As in Tk, deleting the row or clearing the list ends the selection."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: dict[str, Any] = {}
        self.selected: str | None = None

    def display(self, channel: Any, *, add: bool = False) -> None:
        super().display(channel, add=add)
        if add:
            self.shown[channel.iid] = channel

    def remove(self, channel: Any) -> None:
        super().remove(channel)
        if self.selected == channel.iid:
            self.selected = None

    def clear(self) -> None:
        super().clear()
        self.selected = None

    def get_selection(self) -> Any:
        return self.shown[self.selected] if self.selected in self.rows else None

    def set_selection(self, channel: Any) -> None:
        self.selected = channel.iid


def test_a_channel_selected_and_switched_to_during_a_reload_is_watched_after_it(live_twitch):
    async def scenario():
        def campaigns(op: JsonType) -> JsonType:
            if fake.gql_sent.count("Campaigns") == 2:
                # the user selects C2 and presses Switch while the reload runs
                fake.gui.channels.set_selection(twitch.channels[2])
                twitch.change_state(State.CHANNEL_SWITCH)
            return NO_CAMPAIGNS

        fake = FakeTwitch(gql=gql_answers(
            Inventory=inventory([campaign_data([drop_data("d1")])]),
            Campaigns=campaigns,
            GameDirectory=directory((1, 1000), (2, 10)),
            PlaybackAccessToken=HeldAnswer({}),
        ))
        fake.settings.priority = [GAME["name"]]
        fake.gui.channels = SelectingChannelList()
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await start_run(twitch)
        twitch.change_state(State.INVENTORY_FETCH)
        await asyncio.sleep(2)
        await until(lambda: waits(twitch))
        return fake, twitch

    fake, twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]
    assert fake.gui.channels.get_selection() is twitch.channels[2]
    assert fake.printed == [_("status", "watching").format(channel=name) for name in ("C1", "C2")]
    assert fake.gql_sent == [
        "Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken", "Inventory", "Campaigns", "GameDirectory"
    ]
