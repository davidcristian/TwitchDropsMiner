from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest

import twitch.lifecycle as twitch_lifecycle
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


class Run(NamedTuple):
    """The event loop time of each Inventory request and of the end of `Twitch.run`, and the printed lines."""

    sent_at: list[float]
    ended_at: float
    printed: list[str]


def run_app(
    live_twitch, monkeypatch, pick, *answers: JsonType, delay: int = 1, in_wait: Callable[[Any], None] | None = None
) -> Run:
    """Return the `Run` of the app with restart_delay set to delay, whose Inventory requests get answers in turn.

    The app closes at the request after the last answer, and in_wait gets the Twitch a minute after the first FAILED.
    """
    monkeypatch.setattr(twitch_lifecycle, "random", SimpleNamespace(uniform=pick))
    pending = list(answers)
    hooks = [in_wait] if in_wait is not None else []
    sent_at: list[float] = []
    ended_at: list[float] = []

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
            elif answer is FAILED and hooks:
                loop.call_later(60, hooks.pop(), twitch)
            return answer

        fake = FakeTwitch(gql=gql_answers(Inventory=user_inventory, Campaigns=NO_CAMPAIGNS))
        fake.settings.restart_delay = delay
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
        ended_at.append(loop.time())
        printed.extend(fake.printed)

    printed: list[str] = []
    run_with_fast_clock(scenario())
    return Run(sent_at, ended_at[0], printed)


def restart_waits(live_twitch, monkeypatch, pick, *answers: JsonType) -> tuple[list[int], list[str]]:
    """Return the whole minutes from each failed Inventory request to the next, less the jitter, and the printed lines."""
    run = run_app(live_twitch, monkeypatch, pick, *answers)
    jitter = pick(0, RESTART_JITTER.total_seconds())
    waits = [
        int((later - earlier - jitter) // 60)
        for earlier, later, answer in zip(run.sent_at, run.sent_at[1:], answers)
        if answer is FAILED
    ]
    return waits, run.printed


def press_reload(twitch: Any) -> None:
    """Press the Reload button, whose command is the function that state_change returns."""
    twitch.state_change(State.INVENTORY_FETCH)()


def reload_from_a_task(twitch: Any) -> None:
    """Request a reload as a task does, with change_state and no press."""
    twitch.change_state(State.INVENTORY_FETCH)


def close_window(twitch: Any) -> None:
    """Close the window as GUIManager.close does: set the close request, then request EXIT."""
    twitch.gui.close_requested = True
    twitch.gui._closed.set()
    twitch.close()


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


@JITTER
def test_a_reload_press_during_the_wait_restarts_the_run_at_once(live_twitch, monkeypatch, pick):
    run = run_app(live_twitch, monkeypatch, pick, FAILED, delay=10, in_wait=press_reload)

    assert len(run.sent_at) == 2
    assert run.sent_at[1] - run.sent_at[0] == pytest.approx(60, abs=1)
    assert _("status", "restart_now") in run.printed


@JITTER
def test_a_reload_that_a_task_requests_during_the_wait_does_not_end_it(live_twitch, monkeypatch, pick):
    # process_drops requests a reload at the end of a drop claim, which can end after the shutdown of the failed run
    run = run_app(live_twitch, monkeypatch, pick, FAILED, delay=10, in_wait=reload_from_a_task)
    jitter = pick(0, RESTART_JITTER.total_seconds())

    assert len(run.sent_at) == 2
    assert int((run.sent_at[1] - run.sent_at[0] - jitter) // 60) == 10


@JITTER
def test_closing_the_window_during_the_wait_exits_at_once(live_twitch, monkeypatch, pick):
    run = run_app(live_twitch, monkeypatch, pick, FAILED, delay=10, in_wait=close_window)

    assert len(run.sent_at) == 1
    assert run.ended_at - run.sent_at[0] == pytest.approx(60, abs=1)


@JITTER
def test_the_wait_after_a_run_that_a_reload_press_started_is_the_restart_delay(live_twitch, monkeypatch, pick):
    run = run_app(live_twitch, monkeypatch, pick, FAILED, FAILED, delay=10, in_wait=press_reload)
    jitter = pick(0, RESTART_JITTER.total_seconds())

    assert len(run.sent_at) == 3
    assert int((run.sent_at[2] - run.sent_at[1] - jitter) // 60) == 10
