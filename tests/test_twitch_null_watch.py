from __future__ import annotations

import asyncio
import logging

import pytest
from yarl import URL

from channel import Channel
from constants import State
from fakes import (
    NO_CAMPAIGNS,
    USHER_LIST,
    FakeResponse,
    FakeTwitch,
    campaign_data,
    drop_data,
    gql_answers,
    inventory,
    stream_user,
)
from inventory import DropsCampaign
from livetwitch import run_with_fast_clock
from nullpaths import null_paths, path_id, with_null
from ratelimit import RateLimiter

TOKEN = {"data": {"streamPlaybackAccessToken": {
    "value": "value",
    "signature": "signature",
    "authorization": {"isForbidden": False, "forbiddenReasonCode": "NONE"},
}}}
SESSION = ("data", "currentUser", "dropCurrentSession")
CURRENT_DROP = {"data": {"currentUser": {"id": "1", "dropCurrentSession": {
    "channel": {"id": "1", "name": "c1"},
    "game": {"id": "1", "name": "Game"},
    "currentMinutesWatched": 20,
    "requiredMinutesWatched": 120,
    "dropID": "d1",
}}}}
CLAIM = {"data": {"claimDropRewards": {"status": "ELIGIBLE_FOR_ALL", "isUserAccountConnected": True}}}
CLAIM_EVENT = {"type": "drop-claim", "data": {"drop_id": "d1", "drop_instance_id": "1#c1#d1"}}
# The null paths that change what each reader does. A null at any other path of its response changes nothing.
TOKEN_READS = {
    ("data",),
    ("data", "streamPlaybackAccessToken"),
    ("data", "streamPlaybackAccessToken", "value"),
    ("data", "streamPlaybackAccessToken", "signature"),
}
WATCH_LOOP_READS = {SESSION[:1], SESSION[:2], SESSION, (*SESSION, "dropID"), (*SESSION, "currentMinutesWatched")}
CLAIM_WAIT_READS = WATCH_LOOP_READS - {(*SESSION, "currentMinutesWatched")}
CLAIM_READS = {("data",), ("data", "claimDropRewards"), ("data", "claimDropRewards", "status")}


def playlists(method: str, url: URL) -> FakeResponse:
    return FakeResponse(200, USHER_LIST if url.host == "usher.ttvnw.net" else "")


def online_channel(twitch) -> Channel:
    channel = Channel(twitch, id=1, login="c1")
    channel.external_update(stream_user(1, online=True), [])
    return channel


def warned(caplog: pytest.LogCaptureFixture) -> bool:
    return any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.parametrize("path", null_paths(TOKEN), ids=path_id)
def test_a_null_in_the_playback_token_fails_the_watch_cycle_and_starts_an_online_check(live_twitch, caplog, path):
    fake = FakeTwitch(gql=gql_answers(PlaybackAccessToken=with_null(TOKEN, path)), http=playlists)
    channel = online_channel(live_twitch(fake))

    async def one_cycle():
        watched = await channel.send_watch()
        checking = channel._pending_stream_up is not None
        channel.cancel_online_check()
        return watched, checking

    outcome = asyncio.run(one_cycle())

    read = path in TOKEN_READS
    assert (*outcome, warned(caplog)) == ((False, True, True) if read else (True, False, False))
    assert fake.gql_sent == ["PlaybackAccessToken"]
    assert ("GET usher.ttvnw.net" in fake.http_sent) is not read


def campaign_answers(**answers):
    return gql_answers(Inventory=inventory([campaign_data([drop_data("d1")])]), Campaigns=NO_CAMPAIGNS, **answers)


@pytest.mark.parametrize("path", null_paths(CURRENT_DROP), ids=path_id)
def test_a_null_in_the_current_drop_gives_the_watch_loop_an_estimated_minute(live_twitch, path):
    current = with_null(CURRENT_DROP, path)
    fake = FakeTwitch(gql=campaign_answers(PlaybackAccessToken=TOKEN, CurrentDrop=current), http=playlists)

    async def scenario():
        twitch = live_twitch(fake)
        await twitch.fetch_inventory()
        twitch.wanted_games = [twitch.inventory[0].game]
        twitch.watching_channel.set(online_channel(twitch))
        watch_loop = asyncio.create_task(twitch._watch_loop())
        # the loop asks for the current drop 15 seconds after its watch request, and this clock skips the wait
        await asyncio.sleep(30)
        return twitch.inventory[0].timed_drops["d1"].current_minutes, watch_loop.done()

    minutes, ended = run_with_fast_clock(scenario())

    # without a drop ID and minutes, the loop adds a minute itself
    assert (minutes, ended) == (1 if path in WATCH_LOOP_READS else 20, False)
    assert fake.gql_sent == ["Inventory", "Campaigns", "PlaybackAccessToken", "CurrentDrop"]


@pytest.mark.parametrize("path", null_paths(CURRENT_DROP), ids=path_id)
def test_a_null_in_the_current_drop_after_a_claim_stops_the_wait_for_the_next_drop(live_twitch, path):
    current = with_null(CURRENT_DROP, path)
    fake = FakeTwitch(gql=campaign_answers(ClaimDrop=CLAIM, CurrentDrop=current))

    async def scenario():
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await twitch.fetch_inventory()
        twitch.watching_channel.set(online_channel(twitch))
        await twitch.process_drops(1, CLAIM_EVENT)
        return twitch._state

    state = run_with_fast_clock(scenario())

    # the claimed drop stays the current one, so the wait asks 8 times unless the drop ID cannot be read
    assert (state, fake.gql_sent.count("CurrentDrop")) == (State.INVENTORY_FETCH, 1 if path in CLAIM_WAIT_READS else 8)


@pytest.mark.parametrize("path", null_paths(CLAIM), ids=path_id)
def test_a_null_in_the_claim_response_fails_the_claim(live_twitch, caplog, path):
    fake = FakeTwitch(gql=gql_answers(ClaimDrop=with_null(CLAIM, path)))
    twitch = live_twitch(fake)
    drop = DropsCampaign(twitch, campaign_data([drop_data("d1", watched=120, claim_id="1#c1#d1")]), {}).timed_drops["d1"]

    claimed = asyncio.run(drop.claim())

    read = path in CLAIM_READS
    assert (claimed, drop.is_claimed) == (not read, not read)
    assert ("Drop claim has potentially failed" in caplog.text) is read
    assert fake.gql_sent == ["ClaimDrop"]



@pytest.mark.parametrize("response, reads", [
    (TOKEN, TOKEN_READS),
    (CURRENT_DROP, WATCH_LOOP_READS),
    (CURRENT_DROP, CLAIM_WAIT_READS),
    (CLAIM, CLAIM_READS),
])
def test_each_set_of_reads_names_only_paths_of_its_response(response, reads):
    assert reads <= set(null_paths(response))
