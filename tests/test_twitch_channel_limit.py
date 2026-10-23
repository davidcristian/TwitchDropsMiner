from __future__ import annotations

import asyncio

import twitch.client as twitch_client
from constants import State
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
from twitch import Twitch

SECOND = {"id": "2", "name": "Second", "boxArtURL": "https://example.invalid/2-285x380.jpg"}
THIRD = {"id": "3", "name": "Third", "boxArtURL": "https://example.invalid/3-285x380.jpg"}


def limit_fake(acl: list[int], second: list[int], third: list[int]) -> FakeTwitch:
    """Return a FakeTwitch with a campaign of each of GAME, SECOND and THIRD, wanted in that order.

    The ACL of GAME lists the offline channels acl, and the directories list the live channels second and third.
    """
    allow = {"channels": [{"id": str(i), "name": f"c{i}", "displayName": f"C{i}"} for i in acl], "isEnabled": True}
    campaigns = [
        {**campaign_data([drop_data("d1")]), "allow": allow},
        {**campaign_data([drop_data("d2")], game=SECOND), "id": "c2"},
        {**campaign_data([drop_data("d3")], game=THIRD), "id": "c3"},
    ]
    directories = {
        "second": directory(*((i, 100) for i in second), game=SECOND),
        "third": directory(*((i, 1000) for i in third), game=THIRD),
    }
    fake = FakeTwitch(gql=gql_answers(
        Inventory=inventory(campaigns),
        Campaigns=NO_CAMPAIGNS,
        GetStreamInfo=lambda op: {"data": {"user": stream_user(int(op["variables"]["channel"][1:]), online=False)}},
        GameDirectory=lambda op: directories[op["variables"]["slug"]],
        PlaybackAccessToken=HeldAnswer({}),
    ))
    fake.settings.priority = [GAME["name"], SECOND["name"], THIRD["name"]]
    return fake


def run_to_switch(twitch: Twitch) -> Twitch:
    """Run twitch until it watches a channel, and return it."""

    async def scenario():
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await start_run(twitch)
        return twitch

    return run_with_fast_clock(scenario())


def test_an_offline_acl_channel_of_a_higher_game_keeps_its_slot_ahead_of_a_live_channel_of_a_lower_game(
    live_twitch, monkeypatch
):
    monkeypatch.setattr(twitch_client, "MAX_CHANNELS", 2)

    twitch = run_to_switch(live_twitch(limit_fake(acl=[1], second=[2], third=[3])))

    assert list(twitch.channels) == [2, 1]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]


def test_the_live_channels_of_the_best_game_that_can_be_watched_keep_their_slots_first(live_twitch, monkeypatch):
    monkeypatch.setattr(twitch_client, "MAX_CHANNELS", 2)

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
        monkeypatch.setattr(twitch_client, "MAX_CHANNELS", 2)
        twitch.change_state(State.CHANNELS_CLEANUP)
        # the refresh sends the run's seventh and eighth GQL requests, which wait a second for the limiter
        await asyncio.sleep(2)
        await until(lambda: waits(twitch))
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert list(twitch.channels) == [2, 3]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[3]
    assert fake.gui.channels.get_selection() is twitch.channels[3]
