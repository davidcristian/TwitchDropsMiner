from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import twitch.channels as twitch_channels
from constants import ONLINE_DELAY, JsonType, State
from fakes import GAME
from livetwitch import run_with_fast_clock
from test_twitch_channel_limit import SECOND, THIRD, limit_fake, output, watch_first
from test_twitch_run import until, waits
from test_twitch_states import SelectingChannelList
from translate import _
from twitch import Twitch


async def change_game(twitch: Twitch, live: dict[int, JsonType], channel_id: int, game: JsonType) -> None:
    """Change the game of the channel's stream with a broadcast settings update, and wait until the run waits again."""
    # the first watch request is the run's sixth GQL request, which waits a second for the limiter
    await asyncio.sleep(2)
    message = {"old_game": live[channel_id]["name"], "game": game["name"]}
    live[channel_id] = game
    await twitch.process_stream_update(channel_id, message)
    # the update fetches the stream after ONLINE_DELAY
    await asyncio.sleep(ONLINE_DELAY.total_seconds() + 1)
    await until(lambda: waits(twitch))


@pytest.mark.parametrize("before, after, watched", [
    (GAME, THIRD, [1, 2]),
    (GAME, GAME, [1]),
    (SECOND, GAME, [1]),
], ids=["a lower game", "the same game", "a higher game"])
def test_a_change_of_the_watched_game_switches_to_a_tracked_channel_of_a_higher_game_only_when_its_priority_drops(
    live_twitch, before, after, watched
):
    live = {1: before}
    fake = limit_fake(acl=[1], second=[2], third=[], live=live)
    shown: list[str] = []
    fake.gui.status = SimpleNamespace(update=shown.append)

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        shown.clear()
        await change_game(twitch, live, 1, after)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[watched[-1]]
    assert fake.printed == output(*(("watching", f"C{i}") for i in watched))
    assert (_("gui", "status", "switching") in shown) is (len(watched) > 1)
    # the update fetches the stream of C1, and the switch sends no request
    assert fake.gql_sent[5:] == ["PlaybackAccessToken", "GetStreamInfo"]


@pytest.mark.parametrize("selected, watched, sent_after", [
    (None, [1, 2], ["GameDirectory", "GameDirectory"]),
    (1, [1], []),
], ids=["nothing selected", "the watched channel selected"])
def test_a_watched_channel_that_changes_to_a_lower_game_refreshes_at_once_unless_the_user_selected_it(
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
        await change_game(twitch, live, 1, THIRD)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[watched[-1]]
    assert fake.printed == output(*(("watching", f"C{i}") for i in watched))
    assert fake.gql_sent[6:] == ["PlaybackAccessToken", "GetStreamInfo", *sent_after]


def test_an_early_refresh_after_a_change_to_a_lower_game_that_finds_no_better_channel_sends_no_other(
    live_twitch, monkeypatch
):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 2)
    live = {1: GAME}
    second = [2]
    fake = limit_fake(acl=[1, 4], second=second, third=[], live=live)

    async def scenario():
        twitch = await watch_first(live_twitch(fake))
        # C2, which the limit left off the list, ends its stream too
        second.clear()
        await change_game(twitch, live, 1, THIRD)
        return twitch

    twitch = run_with_fast_clock(scenario())

    assert twitch._state is State.CHANNEL_SWITCH and waits(twitch)
    # the refresh stops watching C1, and the switch at its end watches it again
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[1]
    assert fake.printed == output(("watching", "C1"), ("watching", "C1"))
    assert fake.gql_sent[6:] == ["PlaybackAccessToken", "GetStreamInfo", "GameDirectory", "GameDirectory"]
