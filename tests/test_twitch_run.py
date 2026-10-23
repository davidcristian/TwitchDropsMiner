from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import twitch.channels as twitch_channels
from channel import Channel
from constants import JsonType, State
from fakes import (
    GAME,
    NO_CAMPAIGNS,
    FakeTwitch,
    GQLAnswer,
    HeldAnswer,
    campaign_data,
    directory,
    drop_data,
    gql_answers,
    inventory,
    settle,
    stream_user,
)
from inventory import TimedDrop
from livetwitch import log_in, run_with_fast_clock
from ratelimit import RateLimiter
from translate import _
from twitch import Twitch

PROGRESS_EVENT = {
    "type": "drop-progress", "data": {"drop_id": "d1", "current_progress_min": 5, "required_progress_min": 120}
}


def run_fake(*directories: JsonType | GQLAnswer) -> FakeTwitch:
    """Return a FakeTwitch with one campaign of GAME, which answers each GameDirectory request with the next answer.

    The first request of the watch loop gets no answer, so the loop sends no other request.
    """
    answers = list(directories)

    def next_directory(op: JsonType) -> JsonType | Awaitable[JsonType]:
        answer = answers.pop(0)
        return answer(op) if callable(answer) else answer

    fake = FakeTwitch(gql=gql_answers(
        Inventory=inventory([campaign_data([drop_data("d1")])]),
        Campaigns=NO_CAMPAIGNS,
        GameDirectory=next_directory,
        PlaybackAccessToken=HeldAnswer({}),
    ))
    fake.settings.priority = [GAME["name"]]
    return fake


async def until(condition: Callable[[], bool]) -> None:
    """Let the other tasks run until condition is true or 1000 turns of the event loop have passed."""
    for _turn in range(1000):
        if condition():
            return
        await asyncio.sleep(0)


def waits(twitch: Twitch) -> bool:
    """Return True when the run waits for a state change, after it chose a channel to watch or none."""
    return twitch._state in (State.CHANNEL_SWITCH, State.IDLE) and not twitch._state_change.is_set()


async def start_run(twitch: Twitch) -> asyncio.Task[None]:
    """Start the run and wait until it watches a channel."""
    run = asyncio.create_task(twitch._run())
    await until(lambda: twitch.watching_channel.has_value() and waits(twitch))
    return run


async def refresh(twitch: Twitch) -> None:
    """Fetch the channels again, as the maintenance task does every few minutes, and wait until the run waits."""
    twitch.change_state(State.CHANNELS_CLEANUP)
    await until(lambda: waits(twitch))


class FakeProgress:
    """The progress panel of the window, as the drop it shows and whether its minute countdown runs."""

    def __init__(self) -> None:
        self.drop: TimedDrop | None = None
        self.counting = False

    def display(self, drop: TimedDrop | None, *, countdown: bool = True, subone: bool = False) -> None:
        self.drop, self.counting = drop, countdown

    def stop_timer(self) -> None:
        self.counting = False

    def minute_almost_done(self) -> bool:
        return not self.counting


def progress_fake() -> tuple[FakeTwitch, FakeProgress]:
    """Return the FakeTwitch of run_fake, which lists C1 twice, with a FakeProgress in its window."""
    fake = run_fake(directory((1, 1000)), directory((1, 1000)))
    progress = FakeProgress()
    fake.gui.progress, fake.gui.display_drop = progress, progress.display
    return fake, progress


def test_the_run_fetches_the_inventory_while_every_pubsub_connection_fails(live_twitch):
    fake = FakeTwitch(gql=gql_answers(Inventory=inventory([]), Campaigns=NO_CAMPAIGNS))

    async def scenario():
        twitch = live_twitch(fake)
        run = asyncio.create_task(twitch._run())
        await until(lambda: "WS pubsub-edge.twitch.tv" in fake.http_sent and waits(twitch))
        return twitch._state, run.done()

    assert asyncio.run(scenario()) == (State.IDLE, False)
    assert fake.http_sent == ["WS pubsub-edge.twitch.tv"]
    assert fake.gql_sent == ["Inventory", "Campaigns"]
    assert fake.printed == [_("status", "no_campaign")]


def test_the_no_campaign_message_is_printed_once_each_time_no_game_is_wanted(live_twitch):
    fake = run_fake(directory((1, 1000)), directory((1, 1000)))
    fake.settings.priority = []

    async def scenario():
        twitch = live_twitch(fake)
        run = asyncio.create_task(twitch._run())
        await until(lambda: "Campaigns" in fake.gql_sent and waits(twitch))
        await refresh(twitch)
        for priority in ([GAME["name"]], []):
            fake.settings.priority = priority
            twitch.change_state(State.GAMES_UPDATE)
            await until(lambda: waits(twitch))
            await refresh(twitch)
        return run.done()

    assert asyncio.run(scenario()) is False
    assert fake.printed == [
        _("status", "no_campaign"),
        _("status", "watching").format(channel="C1"),
        _("status", "no_campaign"),
    ]
    assert fake.gql_sent == ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken", "GameDirectory"]


def test_a_run_after_a_shutdown_prints_the_no_campaign_message_again(live_twitch):
    fake = FakeTwitch(gql=gql_answers(Inventory=inventory([]), Campaigns=NO_CAMPAIGNS))

    async def scenario():
        twitch = live_twitch(fake)
        for runs in (1, 2):
            run = asyncio.create_task(twitch._run())
            await until(lambda: fake.gql_sent.count("Campaigns") == runs and waits(twitch))
            run.cancel()
            await twitch.shutdown()
            # the next run logs in again
            log_in(twitch, fake)

    run_with_fast_clock(scenario())

    assert fake.printed == [_("status", "no_campaign")] * 2
    assert fake.gql_sent == ["Inventory", "Campaigns"] * 2


def test_a_stream_down_during_the_requests_of_the_channel_fetch_reaches_the_channel(live_twitch):
    async def scenario():
        async def stream_down_during_the_request(op):
            await twitch.process_stream_state(1, {"type": "stream-down"})
            return directory((1, 1000))

        fake = run_fake(directory((1, 1000)), stream_down_during_the_request)
        twitch = live_twitch(fake)
        await start_run(twitch)
        await refresh(twitch)
        return fake, twitch

    fake, twitch = asyncio.run(scenario())

    assert twitch.watching_channel.get_with_default(None) is None
    assert [(channel.id, channel.online) for channel in twitch.channels.values()] == [(1, False)]
    assert fake.gui.channels.rows == {"1": "OFFLINE"}
    assert fake.printed == [
        _("status", "watching").format(channel="C1"),
        _("status", "goes_offline").format(channel="C1"),
        _("status", "no_channel"),
    ]
    assert fake.gql_sent == ["Inventory", "Campaigns", "GameDirectory", "PlaybackAccessToken", "GameDirectory"]


def test_a_directory_stream_whose_broadcaster_id_a_server_error_set_to_null_leaves_the_run_going(live_twitch):
    edge = ["game", "streams", "edges", 0, "node", "broadcaster", "id"]
    response = {**directory((1, 1000), (2, 10)), "errors": [{"message": "server error", "path": edge}]}

    async def scenario():
        twitch = live_twitch(run_fake(response))
        run = await start_run(twitch)
        return twitch, run.done()

    twitch, ended = asyncio.run(scenario())

    assert ended is False
    assert list(twitch.channels) == [2]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]


def test_the_channel_fetch_cancels_the_online_check_of_a_channel_over_the_limit(live_twitch, monkeypatch):
    monkeypatch.setattr(twitch_channels, "MAX_CHANNELS", 1)

    async def scenario():
        async def restart_during_the_request(op):
            # C1 ends its stream and starts it again, so it waits for its online check and sorts last
            await twitch.process_stream_state(1, {"type": "stream-down"})
            await twitch.process_stream_state(1, {"type": "stream-up"})
            return directory((2, 1000))

        twitch = live_twitch(run_fake(directory((1, 1000)), restart_during_the_request))
        await start_run(twitch)
        first = twitch.channels[1]
        await refresh(twitch)
        return twitch, first

    twitch, first = asyncio.run(scenario())

    assert list(twitch.channels) == [2]
    assert twitch.watching_channel.get_with_default(None) is twitch.channels[2]
    assert (first.pending_online, first.offline) == (False, True)


def test_shutdown_cancels_the_online_checks_and_empties_the_channel_list(live_twitch):
    async def scenario():
        held = HeldAnswer({"data": {"user": stream_user(1, online=True)}})
        fake = FakeTwitch(gql=held)
        twitch = live_twitch(fake)
        channel = Channel(twitch, id=1, login="c1")
        twitch.channels[channel.id] = channel
        channel.display(add=True)
        channel.check_online()
        await held.started.wait()
        await twitch.shutdown()
        held.release.set()
        await settle()
        return fake, channel

    fake, channel = run_with_fast_clock(scenario())

    assert (channel.online, channel.offline) == (False, True)
    assert fake.gui.channels.rows == {}
    assert fake.gql_sent == ["GetStreamInfo"]


def test_a_stream_refresh_that_keeps_the_watched_channel_leaves_the_drop_countdown_running(live_twitch):
    fake, progress = progress_fake()

    async def scenario():
        twitch = live_twitch(fake)
        await start_run(twitch)
        # the drop's first progress update starts its countdown
        await twitch.process_drops(1, PROGRESS_EVENT)
        await refresh(twitch)
        return twitch._drops["d1"]

    drop = asyncio.run(scenario())

    assert progress.drop is drop
    assert progress.counting is True


def test_a_reload_that_keeps_the_watched_channel_shows_the_drop_of_the_new_inventory(live_twitch):
    fake, progress = progress_fake()

    async def scenario():
        twitch = live_twitch(fake)
        # the limiter's default clock is the system's, which the skipped waits of this event loop do not move
        twitch._qgl_limiter = RateLimiter(capacity=5, window=1, clock=asyncio.get_running_loop().time)
        await start_run(twitch)
        await twitch.process_drops(1, PROGRESS_EVENT)
        old = twitch._drops["d1"]
        twitch.change_state(State.INVENTORY_FETCH)
        # the reload sends the run's sixth GQL request, which waits a second for the limiter
        await asyncio.sleep(2)
        await until(lambda: waits(twitch))
        return twitch, old

    twitch, old = run_with_fast_clock(scenario())

    assert twitch.watching_channel.get_with_default(None) is twitch.channels[1]
    assert progress.drop is twitch._drops["d1"]
    assert progress.drop is not old
    assert progress.counting is False
