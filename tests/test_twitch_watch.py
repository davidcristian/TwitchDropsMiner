from __future__ import annotations

import asyncio

import pytest
from yarl import URL

import twitch.client as twitch_client
from channel import Channel
from fakes import TOKEN, USHER_LIST, FakeResponse, FakeTwitch, gql_answers, stream_user
from livetwitch import run_with_fast_clock


def watch_request_times(live_twitch, monkeypatch, restart_at: float | None) -> list[float]:
    """Run the watch loop on one channel and return the seconds from its start to each of its first two requests.

    restart_watching is called restart_at seconds after the start, or before it when restart_at is None.
    """
    sent: list[float] = []

    def playlists(method: str, url: URL) -> FakeResponse:
        if url.host == "usher.ttvnw.net":
            return FakeResponse(200, USHER_LIST)
        sent.append(asyncio.get_running_loop().time())
        return FakeResponse(200, "")

    fake = FakeTwitch(gql=gql_answers(PlaybackAccessToken=TOKEN), http=playlists)
    # a running countdown, so the cycles send no CurrentDrop query
    fake.gui.progress.minute_almost_done = lambda: False

    async def scenario():
        loop = asyncio.get_running_loop()
        # the loop measures its cycle with time(), which must follow the clock that skips the waits
        monkeypatch.setattr(twitch_client, "time", loop.time)
        twitch = live_twitch(fake)
        channel = Channel(twitch, id=1, login="c1")
        channel.external_update(stream_user(1, online=True), [])
        twitch.watching_channel.set(channel)
        if restart_at is None:
            twitch.restart_watching()
        start = loop.time()
        watch_loop = asyncio.create_task(twitch._watch_loop())
        if restart_at is not None:
            await asyncio.sleep(restart_at)
            twitch.restart_watching()
        await asyncio.sleep(30)
        assert not watch_loop.done()
        return [round(time - start, 1) for time in sent[:2]]

    return run_with_fast_clock(scenario())


@pytest.mark.parametrize("restart_at, next_at", [(5, 15), (14, 15), (17, 17)])
def test_a_watch_restart_during_a_cycle_ends_the_wait_after_its_current_drop_check(
    live_twitch, monkeypatch, restart_at, next_at
):
    assert watch_request_times(live_twitch, monkeypatch, restart_at) == [0, next_at]


def test_a_watch_restart_before_a_watch_request_leaves_the_cycle_of_that_request_its_full_length(
    live_twitch, monkeypatch
):
    assert watch_request_times(live_twitch, monkeypatch, None) == [0, 20]
