from __future__ import annotations

import asyncio

import pytest

from channel import Channel
from constants import JsonType
from fakes import GAME, FakeTwitch, directory, gql_answers, stream_user
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
    # each online check waits 120 seconds, so an hour has at most 30
    assert 0 < fake.gql_sent.count("GetStreamInfo") <= 30
    assert set(fake.gql_sent) == {"GetStreamInfo"}


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
