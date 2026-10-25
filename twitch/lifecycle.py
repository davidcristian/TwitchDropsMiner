"""The mixin of `Twitch` with the watch loop, the maintenance task, the shutdown and the wait before a restart."""
from __future__ import annotations

import random
import traceback
import asyncio
import logging
from time import time
from datetime import datetime, timedelta, timezone
from contextlib import suppress
from typing import Any, NoReturn, cast, TYPE_CHECKING

import aiohttp

from translate import _
from exceptions import GQLException
from gqldata import current_drop
from utils import task_wrapper
from constants import CALL, WATCH_INTERVAL, REFRESH_JITTER, RESTART_JITTER, State
from twitchapi import GQL_QUERIES

from .session import save_cookies

if TYPE_CHECKING:
    from collections import abc, deque, OrderedDict

    import gamelib
    from gui import GUIManager
    from channel import Channel
    from settings import Settings
    from websocket import WebsocketPool
    from restartdelay import RestartDelay
    from utils import AwaitableValue, Game
    from inventory import DropsCampaign, TimedDrop
    from constants import JsonType

    from .session import _AuthState


logger = logging.getLogger("TwitchDrops")


class LifecycleMixin:
    """The methods of `Twitch` that run the two tasks of a run, shut a run down and wait before a restart."""

    settings: Settings
    gui: GUIManager
    websocket: WebsocketPool
    channels: OrderedDict[int, Channel]
    inventory: list[DropsCampaign]
    wanted_games: list[Game]
    watching_channel: AwaitableValue[Channel]
    _drops: dict[str, TimedDrop]
    _campaigns: dict[str, DropsCampaign]
    _mnt_triggers: deque[datetime]
    _mnt_task: asyncio.Task[None] | None
    _no_campaign_printed: bool
    _no_channel_printed: bool
    _scan_errors_printed: set[gamelib.ScanError]
    _task_error: Exception | None
    _state: State
    _state_change: asyncio.Event
    _reload_pressed: bool
    _restart_delay: RestartDelay
    _session: aiohttp.ClientSession | None
    _auth_state: _AuthState
    _watching_task: asyncio.Task[None] | None
    _watching_restart: asyncio.Event
    print: abc.Callable[[str], None]
    change_state: abc.Callable[[State], None]
    stop_watching: abc.Callable[[], None]
    get_active_campaign: abc.Callable[[Channel | None], DropsCampaign | None]
    gql_request: abc.Callable[..., abc.Coroutine[Any, Any, Any]]

    async def shutdown(self) -> None:
        start_time = time()
        self.stop_watching()
        if self._watching_task is not None:
            self._watching_task.cancel()
            self._watching_task = None
        if self._mnt_task is not None:
            self._mnt_task.cancel()
            self._mnt_task = None
        # stop websocket, close session and save cookies
        await self.websocket.stop(clear_topics=True)
        if self._session is not None:
            cookie_jar = cast(aiohttp.CookieJar, self._session.cookie_jar)
            # clear empty cookie entries off the cookies file before saving
            # NOTE: Unfortunately, aiohttp provides no easy way of clearing empty cookies,
            # so we need to access the private '_cookies' attribute for this.
            for cookie_key, cookie in list(cookie_jar._cookies.items()):
                if not cookie:
                    del cookie_jar._cookies[cookie_key]
            save_cookies(cookie_jar)
            await self._session.close()
            self._session = None
        self._drops.clear()
        self._campaigns.clear()
        for channel in self.channels.values():
            channel.cancel_online_check()
        self.channels.clear()
        self.gui.channels.clear()
        self.inventory.clear()
        self._auth_state.clear()
        self.wanted_games.clear()
        self._mnt_triggers.clear()
        # the next run starts fresh, so let the suppressed messages through again
        self._no_campaign_printed = False
        self._no_channel_printed = False
        self._scan_errors_printed.clear()
        self._task_error = None
        # wait at least half a second + whatever it takes to complete the closing
        # this allows aiohttp to safely close the session
        await asyncio.sleep(start_time + 0.5 - time())

    async def _await_restart(self, error: BaseException) -> bool:
        """
        Prints a message for a fatal error, shuts down and waits for the restart delay.
        Returns False when the restart is turned off, so the error ends the app.
        """
        setting: int = self.settings.restart_delay
        if setting <= 0:
            return False
        minutes: int = self._restart_delay.next_minutes(setting)
        logger.error("Fatal error encountered", exc_info=error)
        self.print(_("status", "fatal_error"))
        self.print(
            ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        )
        # tear everything down, so the retry starts from the same place a fresh run would
        await self.shutdown()
        delay = timedelta(
            minutes=minutes, seconds=random.uniform(0, RESTART_JITTER.total_seconds())
        )
        restart_at: datetime = (datetime.now(timezone.utc) + delay).astimezone()
        restart_time: str = restart_at.strftime(
            "%X" if restart_at.date() == datetime.now().date() else "%x %X"
        )
        self.gui.tray.change_icon("error")
        self.gui.status.update(_("gui", "status", "restarting").format(time=restart_time))
        if minutes > setting:
            self.print(_("status", "restart_longer").format(minutes=minutes))
        self.print(_("status", "restarting").format(time=restart_time))
        self.print(_("status", "restart_now"))
        logger.log(CALL, f"Restarting at: {restart_time}")
        # closing the window or a Reload press cuts the wait short, so the user never has to sit through it
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._wait_for_reload(), timeout=delay.total_seconds())
        if self._reload_pressed:
            # a press starts the waits again from the setting, as a start of the app does
            self._restart_delay.reset()
        return True

    async def _wait_for_reload(self) -> None:
        """Return when the window closes or the Reload button is pressed."""
        self._reload_pressed = False
        while self._state is not State.EXIT and not self._reload_pressed:
            await self._state_change.wait()
            self._state_change.clear()

    async def _watch_sleep(self, delay: float) -> None:
        # we use wait_for here to allow an asyncio.sleep-like that can be ended prematurely
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._watching_restart.wait(), timeout=delay)

    @task_wrapper(critical=True)
    async def _watch_loop(self) -> NoReturn:
        interval: float = WATCH_INTERVAL.total_seconds()
        while True:
            channel: Channel = await self.watching_channel.get()
            if not channel.online:
                # if the channel isn't online anymore, we stop watching it
                self.stop_watching()
                continue
            # logger.log(CALL, f"Sending watch payload to: {channel.name}")
            # This request is the one that an earlier restart asked for, so only a restart
            # during the cycle ends its last wait
            self._watching_restart.clear()
            last_sent: float = time()
            succeeded: bool = await channel.send_watch()
            if not succeeded:
                logger.log(CALL, f"Watch requested failed for channel: {channel.name}")
            # wait ~15 seconds for a progress update
            await asyncio.sleep(15 - min(time() - last_sent, 15))
            if self.gui.progress.minute_almost_done():
                # The minute countdown has stopped or nearly ended, so no progress update came
                # from Twitch for about a minute. Ask GQL for the current drop, or, as a last
                # resort, add an estimated minute to the likely campaign.
                handled: bool = False

                # Solution 1: use GQL to query for the currently mined drop status
                try:
                    context = await self.gql_request(
                        GQL_QUERIES["CurrentDrop"].with_variables(
                            {"channelID": str(channel.id)}
                        )
                    )
                    drop_data: JsonType | None = current_drop(context)
                except GQLException:
                    drop_data = None
                if drop_data is not None and drop_data["currentMinutesWatched"] is not None:
                    gql_drop: TimedDrop | None = self._drops.get(drop_data["dropID"])
                    if gql_drop is not None and gql_drop.can_earn(channel):
                        gql_drop.update_minutes(drop_data["currentMinutesWatched"])
                        drop_text: str = (
                            f"{gql_drop.name} ({gql_drop.campaign.game}, "
                            f"{gql_drop.current_minutes}/{gql_drop.required_minutes})"
                        )
                        logger.log(CALL, f"Drop progress from GQL: {drop_text}")
                        handled = True

                # Solution 2: If GQL fails, figure out which campaign we're most likely mining
                # right now, and then bump up the minutes on it's drops
                if not handled:
                    if (active_campaign := self.get_active_campaign(channel)) is not None:
                        active_campaign.bump_minutes(channel)
                        # NOTE: This usually gets overwritten below
                        drop_text = f"Unknown drop ({active_campaign.game})"
                        if (active_drop := active_campaign.first_drop) is not None:
                            active_drop.display()
                            drop_text = (
                                f"{active_drop.name} ({active_drop.campaign.game}, "
                                f"{active_drop.current_minutes}/{active_drop.required_minutes})"
                            )
                        logger.log(CALL, f"Drop progress from active search: {drop_text}")
                        handled = True
                    else:
                        logger.log(CALL, "No active drop could be determined")
            await self._watch_sleep(interval - min(time() - last_sent, interval))

    @task_wrapper(critical=True)
    async def _maintenance_task(self) -> None:
        now = datetime.now(timezone.utc)
        next_period = now + timedelta(hours=1)
        while True:
            # exit if there's no need to repeat the loop
            now = datetime.now(timezone.utc)
            if now >= next_period:
                break
            next_trigger = next_period
            trigger_type: str = "Reload"
            # Periodically re-scan for channels that went live since the last time we looked.
            # Without this, campaigns with no ACL are only ever discovered during the hourly
            # reload, because their channels come from a point-in-time directory query.
            interval_minutes: int = self.settings.refresh_interval
            if interval_minutes > 0:
                refresh_at = now + timedelta(minutes=interval_minutes) + timedelta(
                    seconds=random.uniform(0, REFRESH_JITTER.total_seconds())
                )
                if refresh_at < next_trigger:
                    next_trigger = refresh_at
                    trigger_type = "Refresh"
            # NOTE: only consume a real trigger if it ends up being the earliest one,
            # otherwise it'd be silently skipped by the refresh scheduled above
            while self._mnt_triggers and self._mnt_triggers[0] <= next_trigger:
                next_trigger = self._mnt_triggers.popleft()
                trigger_type = "Cleanup"
            logger.log(
                CALL,
                (
                    "Maintenance task waiting until: "
                    f"{next_trigger.astimezone().strftime('%X')} ({trigger_type})"
                )
            )
            await asyncio.sleep((next_trigger - now).total_seconds())
            # exit after waiting, before the actions
            now = datetime.now(timezone.utc)
            if now >= next_period:
                break
            if next_trigger != next_period:
                logger.log(CALL, "Maintenance task requests channels cleanup")
                self.change_state(State.CHANNELS_CLEANUP)
        # this triggers a restart of this task every (up to) 60 minutes
        logger.log(CALL, "Maintenance task requests a reload")
        self.change_state(State.INVENTORY_FETCH)
