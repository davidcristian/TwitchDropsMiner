from __future__ import annotations

import asyncio

import pytest

import twitch.channels as twitch_channels
from constants import ONLINE_DELAY, JsonType, State
from fakes import (
    GAME,
    NO_CAMPAIGNS,
    FakeTwitch,
    HeldAnswer,
    campaign_data,
    directory,
    drop_data,
    gql_answers,
    inventory,
    stream_user,
)
from livetwitch import run_with_fast_clock
from ratelimit import RateLimiter
from test_twitch_run import start_run, until, waits
from test_twitch_states import SelectingChannelList
from translate import _
from twitch import Twitch

SECOND = {"id": "2", "name": "Second", "boxArtURL": "https://example.invalid/2-285x380.jpg"}
THIRD = {"id": "3", "name": "Third", "boxArtURL": "https://example.invalid/3-285x380.jpg"}


def limit_fake(
    acl: list[int], second: list[int], third: list[int], live: dict[int, JsonType] | None = None
) -> FakeTwitch:
    """Return a FakeTwitch with a campaign of each of GAME, SECOND and THIRD, wanted in that order.

    The ACL of GAME lists acl, live while live maps a channel to its game; the directories list second and third.
    """
    live = {} if live is None else live
    allow = {"channels": [{"id": str(i), "name": f"c{i}", "displayName": f"C{i}"} for i in acl], "isEnabled": True}
    campaigns = [
        {**campaign_data([drop_data("d1")]), "allow": allow},
        {**campaign_data([drop_data("d2")], game=SECOND), "id": "c2"},
        {**campaign_data([drop_data("d3")], game=THIRD), "id": "c3"},
    ]

    def game_directory(op: JsonType) -> JsonType:
        if op["variables"]["slug"] == "second":
            return directory(*((i, 100) for i in second), game=SECOND)
        return directory(*((i, 1000) for i in third), game=THIRD)

    def stream_info(op: JsonType) -> JsonType:
        channel_id = int(op["variables"]["channel"][1:])
        user = stream_user(channel_id, online=channel_id in live)
        user["broadcastSettings"]["game"] = live.get(channel_id, GAME)
        return {"data": {"user": user}}

    fake = FakeTwitch(gql=gql_answers(
        Inventory=inventory(campaigns),
        Campaigns=NO_CAMPAIGNS,
        GetStreamInfo=stream_info,
        GameDirectory=game_directory,
        PlaybackAccessToken=HeldAnswer({}),
    ))
    fake.settings.priority = [GAME["name"], SECOND["name"], THIRD["name"]]
    return fake


async def watch_first(twitch: Twitch) -> Twitch:
    """Start the run of twitch, wait until it watches a channel, and return twitch."""
    # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
    twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
    await start_run(twitch)
    return twitch


def run_to_switch(twitch: Twitch) -> Twitch:
    """Run twitch until it watches a channel, and return it."""
    return run_with_fast_clock(watch_first(twitch))


async def end_stream(twitch: Twitch, live: dict[int, JsonType], channel_id: int) -> None:
    """End the stream of the channel with its stream-down event, and wait until the run waits again."""
    # the first watch request is the run's sixth GQL request, which waits a second for the limiter
    await asyncio.sleep(2)
    del live[channel_id]
    await twitch.process_stream_state(channel_id, {"type": "stream-down"})
    await until(lambda: waits(twitch))


def test_an_offline_acl_channel_of_a_higher_game_keeps_its_slot_ahead_of_a_live_channel_of_a_lower_game(
    live_twitch, monkeypatch
):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)

    twitch = run_to_switch(live_twitch(limit_fake(acl=[1], second=[2], third=[3])))

    assert list(twitch.channels) == [2, 1]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]


def test_the_live_channels_of_the_best_game_that_can_be_watched_keep_their_slots_first(live_twitch, monkeypatch):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)

    twitch = run_to_switch(live_twitch(limit_fake(acl=[1, 4], second=[2], third=[])))

    assert len(twitch.channels) == 2
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]


def test_a_selected_channel_that_can_be_watched_keeps_its_slot(live_twitch, monkeypatch):
    fake = limit_fake(acl=[1], second=[2], third=[3])
    fake.gui.channels = SelectingChannelList()

    async def scenario():
        twitch = live_twitch(fake)
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await start_run(twitch)
        # the user selects C3 and presses Switch, then the limit leaves room for two of the three channels
        fake.gui.channels.set_selection(twitch.channels[3])
        twitch.change_state(State.CHANNEL_SWITCH)
        await until(lambda: waits(twitch))
        monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)
        twitch.change_state(State.CHANNELS_CLEANUP)
        # the refresh sends the run's seventh and eighth GQL requests, which wait a second for the limiter
        await asyncio.sleep(2)
        await until(lambda: waits(twitch))
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert list(twitch.channels) == [2, 3]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[3]
    assert fake.gui.channels.get_selection() is twitch.channels[3]


def output(*lines: tuple[str, str]) -> list[str]:
    """Return the Output box lines of these status keys, each given with the name of its channel."""
    return [_("status", key).format(channel=name) for key, name in lines]


def test_a_stream_end_that_leaves_nothing_to_watch_refreshes_at_once_when_the_limit_left_out_a_live_channel(
    live_twitch, monkeypatch
):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)
    live = {1: GAME}
    fake = limit_fake(acl=[1, 4], second=[2], third=[], live=live)

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        await end_stream(twitch, live, 1)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]
    assert fake.printed == output(("watching", "C1"), ("goes_offline", "C1"), ("watching", "C2"))
    assert fake.gql_sent[6:] == ["PlaybackAccessToken", "GameDirectory", "GameDirectory"]


@pytest.mark.parametrize("selected, watched, sent_after", [
    (None, 2, ["GameDirectory", "GameDirectory"]),
    (4, 4, []),
], ids=["nothing selected", "the lower channel selected"])
def test_a_stream_end_that_leaves_a_channel_of_a_lower_game_refreshes_at_once_unless_the_user_selected_it(
    live_twitch, monkeypatch, selected, watched, sent_after
):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)
    live = {1: GAME}
    fake = limit_fake(acl=[1, 4], second=[2], third=[], live=live)
    fake.gui.channels = SelectingChannelList()

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        if selected is not None:
            fake.gui.channels.set_selection(twitch.channels[selected])
        # the offline ACL channel C4 kept its slot, and starts a stream of the lowest game
        live[4] = THIRD
        await twitch.process_stream_state(4, {"type": "stream-up"})
        await asyncio.sleep(ONLINE_DELAY.total_seconds() + 1)
        await end_stream(twitch, live, 1)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[watched]
    assert fake.printed == output(("watching", "C1"), ("goes_offline", "C1"), ("watching", f"C{watched}"))
    assert fake.gql_sent[6:] == ["PlaybackAccessToken", "GetStreamInfo", *sent_after]


@pytest.mark.parametrize("limit, second, refresh_interval", [
    (199, [], 5),
    (2, [2], 0),
], ids=["nothing cut", "the refresh set to Never"])
def test_a_stream_end_that_leaves_nothing_to_watch_sends_no_early_refresh(
    live_twitch, monkeypatch, limit, second, refresh_interval
):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", limit)
    live = {1: GAME}
    fake = limit_fake(acl=[1, 4], second=second, third=[], live=live)
    fake.settings.refresh_interval = refresh_interval

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        await end_stream(twitch, live, 1)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch._state is State.IDLE
    assert fake.printed == output(("watching", "C1"), ("goes_offline", "C1"), ("no_channel", ""))
    assert fake.gql_sent[6:] == ["PlaybackAccessToken"]


def test_an_early_refresh_that_finds_nothing_to_watch_sends_no_other(live_twitch, monkeypatch):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)
    live = {1: GAME}
    second = [2]
    fake = limit_fake(acl=[1, 4, 5], second=second, third=[], live=live)

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        # C2, which the limit left off the list, ends its stream too
        second.clear()
        await end_stream(twitch, live, 1)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch._state is State.IDLE
    assert fake.printed == output(("watching", "C1"), ("goes_offline", "C1"), ("no_channel", ""))
    # the refresh checks the ACL channel that the limit left off the list, and the two directories
    assert fake.gql_sent[7:] == ["PlaybackAccessToken", "GetStreamInfo", "GameDirectory", "GameDirectory"]
