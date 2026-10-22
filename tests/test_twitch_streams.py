from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import pytest

from channel import Channel
from constants import JsonType
from exceptions import GQLException
from fakes import GAME, FakeTwitch, directory, gql_answers, settle, stream_user
from livetwitch import run_with_fast_clock
from ratelimit import RateLimiter
from utils import Game

NO_DROPS = {"data": {"channel": {"id": "1", "viewerDropCampaigns": []}}}
DIRECTORY_EDGE = ("game", "streams", "edges", 0, "node")


def with_server_error(response: JsonType, *path: str | int) -> JsonType:
    """Return the response with a server error at path, which `Twitch.gql_request` sets to null."""
    return {**response, "errors": [{"message": "server error", "path": list(path)}]}


def online_info(*path: str | int) -> JsonType:
    """Return a `GetStreamInfo` response for the live channel 1, with a server error at path in its user."""
    return with_server_error({"data": {"user": stream_user(1, online=True)}}, "user", *path)


@pytest.mark.parametrize("path, online, sent", [
    (("id",), False, ["GetStreamInfo"]),
    (("stream", "id"), False, ["GetStreamInfo"]),
    (("broadcastSettings",), True, ["GetStreamInfo", "AvailableDrops"]),
    (("broadcastSettings", "game", "id"), True, ["GetStreamInfo", "AvailableDrops"]),
    (("broadcastSettings", "game", "name"), True, ["GetStreamInfo", "AvailableDrops"]),
])
def test_the_bulk_check_reads_a_null_stream_field_as_offline_or_as_a_stream_without_a_game(
    live_twitch, path, online, sent
):
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=online_info(*path), AvailableDrops=NO_DROPS))
    fake.settings.available_drops_check = True
    twitch = live_twitch(fake)
    channel = Channel(twitch, id=1, login="c1", acl_based=True)

    asyncio.run(twitch.bulk_check_online([channel]))

    assert (channel.online, channel.game) == (online, None)
    assert fake.gql_sent == sent


@pytest.mark.parametrize("path, online", [
    (("stream", "id"), False),
    (("broadcastSettings",), True),
    (("broadcastSettings", "game", "id"), True),
])
def test_an_online_check_reads_a_null_stream_field_as_offline_or_as_a_stream_without_a_game(live_twitch, path, online):
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=online_info(*path)))
    channel = Channel(live_twitch(fake), id=1, login="c1")

    assert asyncio.run(channel.update_stream()) is online
    assert (channel.online, channel.game) == (online, None)
    assert fake.gql_sent == ["GetStreamInfo"]


def test_a_live_channel_read_as_offline_is_checked_at_most_once_per_online_delay(live_twitch):
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=online_info("stream", "id")))

    async def an_hour_of_viewcount_events():
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        channel = twitch.channels[1] = Channel(twitch, id=1, login="c1")
        # a live channel's viewcount events start an online check while the app reads it as offline
        for _ in range(360):
            await twitch.process_stream_state(1, {"type": "viewcount", "viewers": 5})
            await asyncio.sleep(10)
        return channel.online

    assert run_with_fast_clock(an_hour_of_viewcount_events()) is False
    # each query of an online check follows a wait of 120 seconds, so an hour has at most 30
    assert 0 < fake.gql_sent.count("GetStreamInfo") <= 30
    assert set(fake.gql_sent) == {"GetStreamInfo"}


def stream_up(live_twitch, stream_info: Callable[[], JsonType]) -> tuple[FakeTwitch, Channel, list[int]]:
    """Send a stream-up event for the offline ACL channel 1, and wait until its online check ends.

    stream_info returns each GetStreamInfo response. Return the seconds from the event to each request too.
    """
    times: list[float] = []

    def timed(op: JsonType) -> JsonType:
        times.append(asyncio.get_running_loop().time())
        return stream_info()

    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=timed))

    async def scenario():
        twitch = live_twitch(fake)
        channel = twitch.channels[1] = Channel(twitch, id=1, login="c1", acl_based=True)
        channel.display(add=True)
        start = asyncio.get_running_loop().time()
        await twitch.process_stream_state(1, {"type": "stream-up"})
        await settle()
        return channel, [round(time - start) for time in times]

    return (fake, *run_with_fast_clock(scenario()))


def test_a_stream_up_check_tries_again_while_twitch_has_no_stream_data(live_twitch):
    answers = [{"data": {"user": stream_user(1, online=online)}} for online in (False, False, True)]

    fake, channel, seconds = stream_up(live_twitch, lambda: answers.pop(0))

    assert channel.online is True
    assert seconds == [120, 240, 360]
    assert fake.gui.channels.rows == {"1": "ONLINE"}


def test_a_stream_up_check_ends_after_three_tries_and_logs_it(live_twitch, caplog):
    caplog.set_level(logging.INFO, logger="TwitchDrops")

    fake, channel, seconds = stream_up(live_twitch, lambda: {"data": {"user": stream_user(1, online=False)}})

    assert channel.offline is True
    assert seconds == [120, 240, 360]
    assert fake.gui.channels.rows == {"1": "OFFLINE"}
    assert "C1 has no stream after 3 checks" in caplog.text


def test_a_failed_stream_up_check_is_logged_and_shows_the_channel_offline(live_twitch, caplog):
    def failed() -> JsonType:
        raise GQLException("GetStreamInfo failed")

    fake, channel, seconds = stream_up(live_twitch, failed)

    assert channel.offline is True
    assert seconds == [120]
    assert fake.gui.channels.rows == {"1": "OFFLINE"}
    assert "The online check of c1 failed" in caplog.text


def test_a_stream_up_check_that_ends_because_the_window_closes_logs_nothing(live_twitch, caplog):
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo={"data": {"user": stream_user(1, online=True)}}))

    async def scenario():
        twitch = live_twitch(fake)
        channel = twitch.channels[1] = Channel(twitch, id=1, login="c1", acl_based=True)
        await twitch.process_stream_state(1, {"type": "stream-up"})
        # the user closes the window while the check waits
        fake.gui.close_requested = True
        await settle()
        return channel

    channel = run_with_fast_clock(scenario())

    assert channel.offline is True
    assert fake.gql_sent == []
    assert caplog.text == ""


@pytest.mark.parametrize("path", [("id",), ("broadcaster", "id"), ("broadcaster", "login")])
def test_the_directory_leaves_out_a_stream_whose_field_a_server_error_set_to_null(live_twitch, path):
    response = with_server_error(directory((1, 10), (2, 5)), *DIRECTORY_EDGE, *path)
    fake = FakeTwitch(gql=gql_answers(GameDirectory=response))

    channels = asyncio.run(live_twitch(fake).get_live_streams(Game(GAME)))

    assert [channel.id for channel in channels] == [2]


@pytest.mark.parametrize("field", ["id", "name"])
def test_the_directory_reads_a_stream_whose_game_field_a_server_error_set_to_null_as_without_a_game(
    live_twitch, field
):
    response = with_server_error(directory((1, 10)), *DIRECTORY_EDGE, "game", field)
    fake = FakeTwitch(gql=gql_answers(GameDirectory=response))

    channels = asyncio.run(live_twitch(fake).get_live_streams(Game(GAME)))

    assert [(channel.id, channel.online, channel.game) for channel in channels] == [(1, True, None)]
