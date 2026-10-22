from __future__ import annotations

import asyncio
from collections import abc
from typing import Any

import pytest

from constants import JsonType
from exceptions import GQLException
from fakes import GAME, NO_CAMPAIGNS, FakeTwitch, HeldAnswer, campaign_data, directory, drop_data, gql_answers, inventory
from livetwitch import log_in, run_with_fast_clock
from ratelimit import RateLimiter
from translate import _

# an error message that gql_request does not retry, so the watch loop's token request raises GQLException
TOKEN_ERROR = {"errors": [{"message": "failed integrity check"}]}
CONNECTING = _("gui", "websocket", "connecting")


def watch_fake(*tokens: JsonType | abc.Callable[[JsonType], Any], sent_at: list[float]) -> FakeTwitch:
    """Return a FakeTwitch with one campaign of GAME, which lists C1 live and answers each token request with the next
    of tokens. sent_at receives the loop time of each Inventory request."""
    answers = list(tokens)

    def token(op: JsonType) -> Any:
        answer = answers.pop(0)
        return answer(op) if callable(answer) else answer

    def user_inventory(op: JsonType) -> JsonType:
        sent_at.append(asyncio.get_running_loop().time())
        return inventory([campaign_data([drop_data("d1")])])

    fake = FakeTwitch(gql=gql_answers(
        Inventory=user_inventory, Campaigns=NO_CAMPAIGNS, GameDirectory=directory((1, 1000)), PlaybackAccessToken=token
    ))
    fake.settings.priority = [GAME["name"]]
    return fake


def failing_watch_loop(sent_at: list[float], failed_at: list[float]) -> FakeTwitch:
    def token_error(op: JsonType) -> JsonType:
        failed_at.append(asyncio.get_running_loop().time())
        return TOKEN_ERROR

    # the second run's token request gets no answer, so its watch loop waits
    return watch_fake(token_error, HeldAnswer({}), sent_at=sent_at)


def failing_websocket(sent_at: list[float], failed_at: list[float]) -> FakeTwitch:
    fake = watch_fake(HeldAnswer({}), sent_at=sent_at)

    def update(index: int, *, status: str | None = None, topics: int | None = None) -> None:
        # the first connection's status update raises, which ends its task
        if status == CONNECTING and not failed_at:
            failed_at.append(asyncio.get_running_loop().time())
            raise RuntimeError("status update failed")

    fake.gui.websockets.update = update
    return fake


@pytest.mark.parametrize("build, first_run", [
    (failing_watch_loop, ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken"]),
    (failing_websocket, ["Inventory", "Campaigns"]),
])
def test_an_error_in_a_critical_task_restarts_the_run_after_the_restart_delay(live_twitch, build, first_run):
    sent_at: list[float] = []
    failed_at: list[float] = []
    fake = build(sent_at, failed_at)
    fake.settings.restart_delay = 1

    async def scenario():
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        run = asyncio.create_task(twitch.run())
        # the restart waits one minute plus up to a minute of jitter
        await asyncio.sleep(30)
        printed = list(fake.printed)
        # the shutdown before the wait logged out, and the next run logs in again
        log_in(twitch, fake)
        await asyncio.sleep(120)
        twitch.close()
        await run
        return printed

    printed = run_with_fast_clock(scenario())

    assert _("status", "fatal_error") in printed
    assert len(sent_at) == 2
    # the delay of one minute plus up to a minute of jitter starts once the run has ended on the error, which takes
    # it up to 3 seconds here
    assert len(failed_at) == 1
    assert 60 <= sent_at[1] - failed_at[0] <= 123
    assert fake.gql_sent == [*first_run, "Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken"]


def test_an_error_in_the_watch_loop_ends_the_run_with_that_error_when_the_restart_is_off(live_twitch):
    fake = failing_watch_loop([], [])
    fake.settings.restart_delay = 0

    async def scenario():
        await asyncio.wait_for(live_twitch(fake).run(), 30)

    with pytest.raises(GQLException):
        run_with_fast_clock(scenario())
    assert fake.gql_sent == ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken"]
