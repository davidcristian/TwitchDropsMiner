from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from yarl import URL

import channel as channel_module
from channel import Channel
from fakes import FakeResponse, FakeTwitch, HeldAnswer, settle, stream_user

PLAYLIST = "https://video-weaver.example.invalid/v1/playlist/1.m3u8"
USHER_LIST = f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n{PLAYLIST}\n"
TOKEN = {"data": {"streamPlaybackAccessToken": {"value": "value", "signature": "signature"}}}


@pytest.fixture
def no_online_delay(monkeypatch):
    monkeypatch.setattr(channel_module, "ONLINE_DELAY", timedelta(0))


def shown_channel(twitch: FakeTwitch, *, online: bool) -> Channel:
    channel = Channel(twitch, id=1, login="c1")
    channel.external_update(stream_user(1, online=online), [])
    channel.display(add=True)
    return channel


def usher_or_404(method: str, url: URL) -> FakeResponse:
    if url.host == "usher.ttvnw.net":
        return FakeResponse(200, USHER_LIST)
    return FakeResponse(404)


def test_a_failed_playlist_request_requests_usher_again_and_starts_one_online_check():
    twitch = FakeTwitch(gql=lambda op: TOKEN, http=usher_or_404)
    channel = shown_channel(twitch, online=True)

    async def three_cycles():
        results = [await channel.send_watch()]
        check = channel._pending_stream_up
        results += [await channel.send_watch(), await channel.send_watch()]
        started_once = check is not None and channel._pending_stream_up is check
        channel.cancel_online_check()
        return results, started_once

    assert asyncio.run(three_cycles()) == ([False, False, False], True)
    assert twitch.http_sent == [
        "GET usher.ttvnw.net",
        "GET video-weaver.example.invalid",
        "GET usher.ttvnw.net",
        "GET video-weaver.example.invalid",
        "GET video-weaver.example.invalid",
    ]
    assert twitch.gql_sent == ["PlaybackAccessToken", "PlaybackAccessToken"]


def test_a_stream_down_during_the_playlist_request_starts_no_online_check():
    def stream_down_then_404(method: str, url: URL) -> FakeResponse:
        if url.host == "usher.ttvnw.net":
            return FakeResponse(200, USHER_LIST)
        channel.set_offline()
        return FakeResponse(404)

    twitch = FakeTwitch(gql=lambda op: TOKEN, http=stream_down_then_404)
    channel = shown_channel(twitch, online=True)

    assert asyncio.run(channel.send_watch()) is False
    assert channel.offline is True
    assert twitch.updates == [(True, False)]
    assert twitch.gui.channels.rows == {"1": "OFFLINE"}


def test_remove_during_the_request_of_an_online_check_cancels_the_check(no_online_delay):
    async def scenario():
        held = HeldAnswer({"data": {"user": stream_user(1, online=True)}})
        twitch = FakeTwitch(gql=held)
        channel = shown_channel(twitch, online=False)
        channel.check_online()
        await held.started.wait()
        channel.remove()
        held.release.set()
        await settle()
        return twitch, channel

    twitch, channel = asyncio.run(scenario())

    assert (channel.online, channel.offline) == (False, True)
    assert twitch.updates == []
    assert twitch.gui.channels.rows == {}


def test_set_offline_during_the_request_of_an_online_check_cancels_the_check(no_online_delay):
    async def scenario():
        held = HeldAnswer({"data": {"user": stream_user(1, online=True)}})
        twitch = FakeTwitch(gql=held)
        channel = shown_channel(twitch, online=True)
        channel.check_online()
        await held.started.wait()
        channel.set_offline()
        held.release.set()
        await settle()
        return twitch, channel

    twitch, channel = asyncio.run(scenario())

    assert (channel.online, channel.offline) == (False, True)
    assert twitch.updates == [(True, False)]
    assert twitch.gui.channels.rows == {"1": "OFFLINE"}


def test_an_online_check_ends_before_it_reports_the_new_status(no_online_delay):
    twitch = FakeTwitch(gql=lambda op: {"data": {"user": stream_user(1, online=False)}})
    channel = shown_channel(twitch, online=False)

    async def scenario():
        channel.check_online()
        pending_row = twitch.gui.channels.rows["1"]
        await settle()
        return pending_row

    assert asyncio.run(scenario()) == "PENDING"
    assert twitch.updates == [(False, False)]
    assert twitch.gui.channels.rows == {"1": "OFFLINE"}
    assert channel.offline is True


def test_external_update_with_no_stream_clears_the_stream():
    channel = shown_channel(FakeTwitch(), online=True)

    channel.external_update(stream_user(1, online=False), [])

    assert (channel.online, channel.game, channel.viewers) == (False, None, None)
