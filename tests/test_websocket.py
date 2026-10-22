from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import aiohttp

from constants import JsonType, WebsocketTopic
from fakes import FakeTwitch
from livetwitch import SERVER_CLOSE, FakePubSub, run_with_fast_clock
from twitch import Twitch

DROP_EVENTS = "user-drop-events.1"
DROP_CLAIM = {"type": "drop-claim", "data": {"drop_instance_id": "7#c1#d1"}}


def event(topic: str, message: str) -> str:
    return json.dumps({"type": "MESSAGE", "data": {"topic": topic, "message": message}})


def pubsub_server(*connections: FakePubSub, opened: list[float]) -> Callable[[], FakePubSub]:
    """Return a PubSub answer that opens these connections in order and refuses each later connect.

    opened receives the loop time of each connect that succeeds.
    """
    waiting = list(connections)

    def connect() -> FakePubSub:
        if not waiting:
            raise aiohttp.ClientConnectionError("connection refused")
        opened.append(asyncio.get_running_loop().time())
        return waiting.pop(0)

    return connect


def channel_topics(count: int) -> list[WebsocketTopic]:
    """Return the StreamState topics of the channels 1 to count, whose events do nothing."""

    async def process(channel_id: int, message: JsonType) -> None:
        pass

    return [WebsocketTopic("Channel", "StreamState", channel_id, process) for channel_id in range(1, count + 1)]


async def run_pubsub(twitch: Twitch, seconds: float, received: list[JsonType] | None = None) -> None:
    """Start PubSub with the drop event topic of user 1, run it for seconds of loop time, then stop it."""

    async def process(user_id: int, message: JsonType) -> None:
        if received is not None:
            received.append(message)

    await twitch.get_auth()
    twitch.websocket.add_topics([WebsocketTopic("User", "Drops", 1, process)])
    twitch.websocket.start()
    await asyncio.sleep(seconds)
    await twitch.websocket.stop()


def test_connections_that_close_at_once_are_spaced_by_the_backoff(live_twitch):
    opened: list[float] = []
    # the limit ends a run in which each connect follows the last one with no wait
    server = pubsub_server(*(FakePubSub(SERVER_CLOSE) for _ in range(50)), opened=opened)

    async def scenario():
        start = asyncio.get_running_loop().time()
        await run_pubsub(live_twitch(FakeTwitch(), pubsub=server), 600)
        return [time - start for time in opened]

    times = run_with_fast_clock(scenario())

    gaps = [later - earlier for earlier, later in zip(times, times[1:])]
    # ExponentialBackoff doubles the wait from 1 second up to 180 seconds and varies each wait by 10%
    short = [(step, round(gap, 1)) for step, gap in enumerate(gaps) if gap < 0.9 * min(2**step, 180)]
    assert short == []
    assert 10 <= len(times) <= 11


def test_a_connection_after_one_closed_before_its_pong_sends_a_ping_at_once(live_twitch):
    first, second = FakePubSub(SERVER_CLOSE), FakePubSub()
    server = pubsub_server(first, second, opened=[])

    run_with_fast_clock(run_pubsub(live_twitch(FakeTwitch(), pubsub=server), 30))

    assert [message["type"] for message in first.sent] == ["PING", "LISTEN"]
    assert [message["type"] for message in second.sent] == ["PING", "LISTEN"]


def test_a_malformed_message_is_skipped_and_the_rest_of_its_batch_is_handled(live_twitch):
    opened: list[float] = []
    received: list[JsonType] = []
    connection = FakePubSub(
        "not JSON",
        json.dumps({"nonce": "no type"}),
        event(DROP_EVENTS, "not JSON"),
        event(DROP_EVENTS, json.dumps(DROP_CLAIM)),
    )
    server = pubsub_server(connection, opened=opened)

    run_with_fast_clock(run_pubsub(live_twitch(FakeTwitch(), pubsub=server), 30, received))

    assert received == [DROP_CLAIM]
    assert len(opened) == 1


def test_a_received_message_is_logged_with_its_secrets_hidden(live_twitch, caplog):
    caplog.set_level(logging.DEBUG, logger="TwitchDrops.websocket")
    response = json.dumps({"type": "RESPONSE", "nonce": "n", "data": {"auth_token": "secret-token"}})
    server = pubsub_server(FakePubSub(response), opened=[])

    run_with_fast_clock(run_pubsub(live_twitch(FakeTwitch(), pubsub=server), 30))

    logged = [record.getMessage() for record in caplog.records]
    assert [message for message in logged if "RESPONSE" in message] == [
        "Websocket[0] received: {'type': 'RESPONSE', 'nonce': 'n', 'data': {'auth_token': '<hidden>'}}"
    ]
    assert "secret-token" not in caplog.text


def test_a_restart_with_fewer_topics_connects_only_the_websockets_that_hold_them(live_twitch):
    opened: list[float] = []
    server = pubsub_server(*(FakePubSub() for _ in range(8)), opened=opened)

    async def scenario() -> list[int]:
        twitch = live_twitch(FakeTwitch(), pubsub=server)
        pool = twitch.websocket
        await twitch.get_auth()
        pool.start()
        pool.add_topics(channel_topics(120))
        await asyncio.sleep(30)
        # Twitch.shutdown stops the pool this way before a restart, and the next run starts it and subscribes again
        await pool.stop(clear_topics=True)
        pool.start()
        pool.add_topics(channel_topics(10))
        await asyncio.sleep(30)
        topics = [len(websocket.topics) for websocket in pool.websockets]
        await pool.stop()
        return topics

    topics = run_with_fast_clock(scenario())

    # 3 connections hold the 120 topics of the first run, and 1 the 10 topics of the next
    assert (topics, len(opened)) == ([10], 4)
