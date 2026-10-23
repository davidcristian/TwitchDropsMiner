from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import twitch.client as twitch_client
from constants import RESTART_JITTER, JsonType, State
from fakes import NO_CAMPAIGNS, FakeTwitch, gql_answers, inventory
from livetwitch import log_in, run_with_fast_clock
from ratelimit import RateLimiter
from translate import _

# an error message that gql_request does not retry, so the Inventory request raises GQLException and ends the run
FAILED = {"errors": [{"message": "failed integrity check"}]}
EMPTY = inventory([])
LONGER = _("status", "restart_longer").split("{")[0]
# the random jitter of each restart at its smallest and at its largest
JITTER = pytest.mark.parametrize("pick", [min, max])


def restart_waits(live_twitch, monkeypatch, pick, *answers: JsonType) -> tuple[list[int], list[str]]:
    """Return the whole minutes from each failed Inventory request to the next, less the jitter, and the printed lines.

    Requests get answers in turn, and the one after the last closes the app. A Reload press comes an hour after EMPTY.
    """
    monkeypatch.setattr(twitch_client, "random", SimpleNamespace(uniform=pick))
    jitter = pick(0, RESTART_JITTER.total_seconds())
    pending = list(answers)
    sent_at: list[float] = []

    async def scenario() -> None:
        loop = asyncio.get_running_loop()

        def user_inventory(op: JsonType) -> JsonType:
            sent_at.append(loop.time())
            if not pending:
                twitch.close()
                return EMPTY
            answer = pending.pop(0)
            if answer is EMPTY:
                # _maintenance_task reads the system clock, which this event loop does not move, so a Reload press
                # stands in for the hourly reload
                loop.call_later(3600, twitch.change_state, State.INVENTORY_FETCH)
            return answer

        fake = FakeTwitch(gql=gql_answers(Inventory=user_inventory, Campaigns=NO_CAMPAIGNS))
        fake.settings.restart_delay = 1
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=loop.time)
        shutdown = twitch.shutdown

        async def shutdown_and_log_in() -> None:
            await shutdown()
            # the shutdown logs out, and the next run logs in again
            log_in(twitch, fake)

        twitch.shutdown = shutdown_and_log_in
        await asyncio.wait_for(twitch.run(), 6 * 3600)
        printed.extend(fake.printed)

    printed: list[str] = []
    run_with_fast_clock(scenario())
    waits = [
        int((later - earlier - jitter) // 60)
        for earlier, later, answer in zip(sent_at, sent_at[1:], answers)
        if answer is FAILED
    ]
    return waits, printed


@JITTER
def test_three_runs_that_end_at_once_wait_1_2_and_4_minutes_before_their_restarts(live_twitch, monkeypatch, pick):
    waits, printed = restart_waits(live_twitch, monkeypatch, pick, FAILED, FAILED, FAILED)

    assert waits == [1, 2, 4]


@JITTER
def test_a_run_that_lasts_an_hour_sets_the_next_wait_back_to_the_restart_delay(live_twitch, monkeypatch, pick):
    # the third run reloads after an hour, and that reload fails
    waits, printed = restart_waits(live_twitch, monkeypatch, pick, FAILED, FAILED, EMPTY, FAILED, FAILED)

    assert waits == [1, 2, 1, 2]


@JITTER
def test_a_wait_longer_than_the_restart_delay_is_printed_with_its_minutes(live_twitch, monkeypatch, pick):
    waits, printed = restart_waits(live_twitch, monkeypatch, pick, FAILED, FAILED, FAILED)

    assert [line for line in printed if line.startswith(LONGER)] == [
        _("status", "restart_longer").format(minutes=2),
        _("status", "restart_longer").format(minutes=4),
    ]
