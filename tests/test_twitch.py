from __future__ import annotations

import asyncio

from channel import Channel
from constants import JsonType
from fakes import FakeTwitch, stream_user
from twitch import Twitch


def test_the_bulk_check_clears_the_stream_of_an_offline_channel_and_keeps_that_of_a_missing_one():
    users: dict[str, JsonType | None] = {}
    twitch = FakeTwitch(gql=lambda op: {"data": {"user": users[op["variables"]["channel"]]}})
    channels = [Channel(twitch, id=number, login=f"c{number}", acl_based=True) for number in (1, 2, 3)]

    users.update(c1=stream_user(1, online=True), c2=stream_user(2, online=True), c3=stream_user(3, online=False))
    asyncio.run(Twitch.bulk_check_online(twitch, channels))
    first_pass = [channel.online for channel in channels]
    # A server error sets the user to null
    users.update(c1=stream_user(1, online=False), c2=None, c3=stream_user(3, online=True))
    asyncio.run(Twitch.bulk_check_online(twitch, channels))

    assert first_pass == [True, True, False]
    assert [channel.online for channel in channels] == [False, True, True]
    assert twitch.gql_sent == ["GetStreamInfo"] * 6
