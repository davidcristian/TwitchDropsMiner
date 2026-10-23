"""`Twitch`, the client object: its state, the state machine in `_run`, the watch loop and the PubSub handlers."""
from __future__ import annotations

import random
import traceback
import asyncio
import logging
from time import time
from functools import partial
from collections import abc, deque, OrderedDict
from datetime import datetime, timedelta, timezone
from contextlib import suppress
from typing import Final, NoReturn, cast, TYPE_CHECKING

import aiohttp

import gamelib
from translate import _
from savefiles import save_each
from ratelimit import RateLimiter
from restartdelay import RestartDelay
from gui import GUIManager
from channel import Channel
from websocket import WebsocketPool
from inventory import DropsCampaign
from exceptions import (
    ExitRequest,
    GQLException,
    ReloadRequest,
    MinerException,
    RequestException,
)
from gqldata import current_drop
from streamdata import channel_streams, channel_campaigns, directory_streams
from utils import (
    chunk,
    task_wrapper,
    AwaitableValue,
)
from constants import (
    CALL,
    MAX_INT,
    DUMP_PATH,
    MAX_CHANNELS,
    WATCH_INTERVAL,
    REFRESH_JITTER,
    RESTART_JITTER,
    State,
    PriorityMode,
)
from twitchapi import GQL_QUERIES, ClientType, WebsocketTopic

from .session import SessionMixin, _AuthState, save_cookies
from .requests import RequestsMixin
from .inventoryfetch import InventoryFetchMixin

if TYPE_CHECKING:
    from utils import Game
    from channel import Stream
    from settings import Settings
    from inventory import TimedDrop
    from constants import JsonType
    from twitchapi import ClientInfo, GQLOperation


logger = logging.getLogger("TwitchDrops")
# Of the states requested during one pass of Twitch._run, change_state keeps the first in this order. A reload
# goes through its states in this order, so it also runs a later state that a request names.
STATE_ORDER: Final[tuple[State, ...]] = (
    State.EXIT,
    State.RESTART,
    State.INVENTORY_FETCH,
    State.GAMES_UPDATE,
    State.CHANNELS_CLEANUP,
    State.CHANNELS_FETCH,
    State.CHANNEL_SWITCH,
    State.IDLE,
)
# The translation key, in gui.settings.detect, of the text of each kind of scan error
SCAN_ERROR_KEYS: Final[dict[gamelib.ScanErrorKind, str]] = {
    gamelib.ScanErrorKind.NOT_A_FOLDER: "not_a_folder",
    gamelib.ScanErrorKind.NO_GAMES: "no_games",
    gamelib.ScanErrorKind.FAILED: "failed",
}


class Twitch(SessionMixin, RequestsMixin, InventoryFetchMixin):
    def __init__(self, settings: Settings):
        self.settings: Settings = settings
        # State management
        self._state: State = State.IDLE
        self._state_change = asyncio.Event()
        self.wanted_games: list[Game] = []
        self.inventory: list[DropsCampaign] = []
        self._drops: dict[str, TimedDrop] = {}
        self._campaigns: dict[str, DropsCampaign] = {}
        self._mnt_triggers: deque[datetime] = deque()
        # A stream refresh enters CHANNELS_CLEANUP and CHANNEL_SWITCH every few minutes, so these flags keep
        # the messages that nothing can be mined or watched from being printed again on each refresh
        self._no_campaign_printed: bool = False
        self._no_channel_printed: bool = False
        # NOTE: the game folder scan re-runs on every reload, so remember which problems
        # we've already reported - a folder on an unplugged drive would print hourly otherwise
        self._scan_errors_printed: set[gamelib.ScanError] = set()
        # the Rescan button can be pressed while a scan is already running
        self._scanning_games: bool = False
        # the error of a failed critical task, which _run raises as its own
        self._task_error: Exception | None = None
        self._restart_delay = RestartDelay(lambda: asyncio.get_running_loop().time())
        # NOTE: GQL is pretty volatile and breaks everything if one runs into their rate limit.
        # Do not modify the default, safe values.
        self._qgl_limiter = RateLimiter(capacity=5, window=1)
        # Client type, session and auth
        self._client_type: ClientInfo = ClientType.ANDROID_APP
        self._session: aiohttp.ClientSession | None = None
        self._auth_state: _AuthState = _AuthState(self)
        # GUI
        self.gui = GUIManager(self)
        # Storing and watching channels
        self.channels: OrderedDict[int, Channel] = OrderedDict()
        self.watching_channel: AwaitableValue[Channel] = AwaitableValue()
        self._watching_task: asyncio.Task[None] | None = None
        self._watching_restart = asyncio.Event()
        # Websocket
        self.websocket = WebsocketPool(self)
        # Maintenance task
        self._mnt_task: asyncio.Task[None] | None = None

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

    def change_state(self, state: State) -> None:
        """Request the state that _run handles next."""
        # _run clears the event as it starts each pass, so a set event means that this pass has a request already.
        # Once the state is EXIT it no longer changes, so a late call cannot restart an app that is closing.
        if self._state is not State.EXIT and (
            not self._state_change.is_set() or STATE_ORDER.index(state) < STATE_ORDER.index(self._state)
        ):
            self._state = state
        self._state_change.set()

    def state_change(self, state: State) -> abc.Callable[[], None]:
        # this is identical to change_state, but defers the call
        # perfect for GUI usage
        return partial(self.change_state, state)

    def close(self):
        """
        Called when the application is requested to close by the user,
        usually by the console or application window being closed.
        """
        self.change_state(State.EXIT)

    def task_failed(self, error: Exception) -> None:
        """End the run with the error of a failed critical task, so the run restarts as after a fatal error."""
        if self._task_error is None:
            self._task_error = error
        self.change_state(State.RESTART)

    def prevent_close(self):
        """
        Called when the application window has to be prevented from closing, even after the user
        closes it with X. Usually used solely to display tracebacks from the closing sequence.
        """
        self.gui.prevent_close()

    def print(self, message: str):
        """
        Can be used to print messages within the GUI.
        """
        self.gui.print(message)

    def save(self, *, force: bool = False) -> None:
        """
        Saves the application state.
        """
        self.gui.save(force=force)
        self.settings.save(force=force)

    async def detect_games(self) -> None:
        """
        Scans the game folders and stores the Twitch names of the installed games that match
        a campaign's game in the detected_games setting.
        """
        # a copy, because the scan thread must not read the list while a folder button changes it
        game_dirs: list[str] = list(self.settings.game_dirs)
        if not game_dirs:
            # nothing configured - make sure we don't keep a stale list around
            if self.settings.detected_games:
                self.settings.detected_games = []
                # the games we were mining because of a detection are no longer wanted
                self.change_state(State.GAMES_UPDATE)
            self._scan_errors_printed.clear()
            self.gui.settings.set_detected([])
            return
        if self._scanning_games:
            # the running scan checks the folders when it ends, and scans again if they changed
            return
        self._scanning_games = True
        self.gui.settings.set_scanning(True)
        try:
            # walking the filesystem blocks, so keep it off the event loop
            result: gamelib.ScanResult = await asyncio.to_thread(
                gamelib.scan_directories, game_dirs
            )
        except Exception:
            logger.exception("Game folder scan failed")
            self.gui.settings.set_scanning(False)
            return
        finally:
            self._scanning_games = False
        if self.settings.game_dirs != game_dirs:
            await self.detect_games()
            return
        for error in result.errors:
            if error not in self._scan_errors_printed:
                text: str = _("gui", "settings", "detect", SCAN_ERROR_KEYS[error.kind])
                self.print(
                    _("gui", "settings", "detect", "scan_error").format(
                        error=text.format(path=error.path, reason=error.reason)
                    )
                )
        # only keep the problems that are still current, so a folder that breaks again later
        # gets reported again instead of staying silent
        self._scan_errors_printed = set(result.errors)
        matches: list[gamelib.GameMatch] = gamelib.match_games(
            result.games, (campaign.game.name for campaign in self.inventory)
        )
        # NOTE: copy, because assigning below would otherwise mutate what we compare against
        previous: list[str] = list(self.settings.detected_games)
        detected: list[str] = [match.game_name for match in matches]
        self.gui.settings.set_detected(matches, len(result.games))
        if detected != previous:
            self.settings.detected_games = detected
            # wanted_games is computed from this list, so a game found by Rescan is mined now and
            # not after the next hourly reload. GAMES_UPDATE sends no inventory request, but its
            # full cleanup makes CHANNELS_FETCH check the wanted campaigns' ACL channels again.
            self.change_state(State.GAMES_UPDATE)
        logger.log(
            CALL,
            (
                f"Game detection: {len(result.games)} installed, "
                f"{sum(match.local_count for match in matches)} matched to a campaign"
            ),
        )

    def get_priority(self, channel: Channel) -> int:
        """
        Returns the index of the channel's game in wanted_games, where 0 is the highest priority,
        or MAX_INT when the channel's game is None (as when offline) or not wanted.
        """
        if (
            (game := channel.game) is None  # None when OFFLINE or no game set
            or game not in self.wanted_games  # we don't care about the played game
        ):
            return MAX_INT
        return self.wanted_games.index(game)

    @staticmethod
    def _viewers_key(channel: Channel) -> int:
        if (viewers := channel.viewers) is not None:
            return viewers
        return -1

    def _slot_order(
        self, channels: list[Channel], acl_priority: dict[Channel, int], selected_id: int | None
    ) -> list[Channel]:
        """
        Returns the channels in the order in which they keep one of the MAX_CHANNELS slots.
        channels is sorted by get_priority, and acl_priority maps a channel to the best priority of the wanted
        games whose campaigns list it in their ACL.
        """
        best = next((self.get_priority(channel) for channel in channels if self.can_watch(channel)), None)

        def key(channel: Channel) -> tuple[bool, int]:
            priority = self.get_priority(channel)
            # CHANNEL_SWITCH watches one of these next, so they keep their slots first
            if (priority == best or channel.id == selected_id) and self.can_watch(channel):
                return (False, priority)
            # An offline ACL channel, or one that streams another game, ranks with the game of its campaign, ahead of
            # the live channels of games with a lower priority, so it keeps the subscription to its stream-up event.
            if priority == MAX_INT:
                priority = acl_priority.get(channel, MAX_INT)
            return (True, priority)

        return sorted(channels, key=key)

    async def run(self):
        if self.settings.dump:
            with open(DUMP_PATH, 'w', encoding="utf8"):
                # replace the existing file with an empty one
                pass
        while True:
            self._restart_delay.started()
            try:
                await self._run()
                break
            except ReloadRequest:
                await self.shutdown()
            except ExitRequest:
                break
            except Exception as exc:
                error: Exception = exc
                if isinstance(exc, aiohttp.ContentTypeError):
                    # this one gets a friendlier explanation than the raw aiohttp error
                    error = RequestException(_("login", "unexpected_content"))
                    error.__cause__ = exc
                if not await self._await_restart(error):
                    # restarting is turned off, so the error terminates us like it used to
                    raise error
                if self.gui.close_requested:
                    # the window was closed while we were waiting out the delay
                    break

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
        logger.log(CALL, f"Restarting at: {restart_time}")
        # closing the window cuts the wait short, so the user never has to sit through it
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                self.gui.wait_until_closed(), timeout=delay.total_seconds()
            )
        return True

    async def _run(self):
        """
        Logs in and runs the state machine, which claims drops and picks and watches channels.
        """
        self.gui.start()
        auth_state = await self.get_auth()
        self.websocket.start()
        # NOTE: watch task is explicitly restarted on each new run
        if self._watching_task is not None:
            self._watching_task.cancel()
        self._watching_task = asyncio.create_task(self._watch_loop())
        # Add default topics
        self.websocket.add_topics([
            WebsocketTopic("User", "Drops", auth_state.user_id, self.process_drops),
            WebsocketTopic(
                "User", "Notifications", auth_state.user_id, self.process_notifications
            ),
        ])
        full_cleanup: bool = False
        watch_restarted: bool = False
        # the ID of the selected channel when the last cleanup removed it
        removed_selection: int | None = None
        channels: Final[OrderedDict[int, Channel]] = self.channels
        # a run starts with a reload, so of the requests made before it only EXIT is kept
        self._state_change.clear()
        self.change_state(State.INVENTORY_FETCH)
        while True:
            self._state_change.clear()
            if self._state is State.IDLE:
                if self.settings.dump:
                    self.gui.close()
                    continue
                self.gui.tray.change_icon("idle")
                self.gui.status.update(_("gui", "status", "idle"))
                self.stop_watching()
            elif self._state is State.INVENTORY_FETCH:
                self.gui.tray.change_icon("maint")
                # ensure the websocket is running
                self.websocket.start()
                await self.fetch_inventory()
                self.gui.set_games(set(campaign.game for campaign in self.inventory))
                # match installed games against the campaigns we've just fetched
                await self.detect_games()
                # Save state on every inventory fetch
                save_each(
                    (self.gui.save, self.settings.save),
                    lambda error: logger.error(_("error", "save_failed").format(error=error)),
                )
                if self._state is State.INVENTORY_FETCH:
                    # a reload requested while this one ran is merged into it, so it sends no second reload
                    self._state_change.clear()
                self.change_state(State.GAMES_UPDATE)
            elif self._state is State.GAMES_UPDATE:
                # claim drops from expired and active campaigns
                for campaign in self.inventory:
                    if not campaign.upcoming:
                        for drop in campaign.drops:
                            if drop.can_claim:
                                await drop.claim()
                # figure out which games we want
                self.wanted_games.clear()
                exclude = self.settings.exclude
                priority = self.settings.priority
                detected = self.settings.detected_games
                priority_mode = self.settings.priority_mode
                priority_only = priority_mode is PriorityMode.PRIORITY_ONLY
                # List entries ignore case, accents and punctuation, and can use '*' and '?'
                # wildcards, so a single entry can stand in for a whole series of games.
                priority_patterns = gamelib.compile_patterns(priority)
                exclude_patterns = gamelib.compile_patterns(exclude)
                # Games detected as installed rank below every manually prioritized one,
                # so an explicit choice always wins over an automatic one.
                detected_order: dict[str, int] = {
                    name: len(priority) + index for index, name in enumerate(detected)
                }
                # NOTE: resolve each game's rank once here, rather than on every comparison
                # the sort below makes - matching a pattern is more expensive than a lookup
                priority_order: dict[str, int] = {}
                for campaign in self.inventory:
                    game_name: str = campaign.game.name
                    if game_name not in priority_order:
                        rank: int | None = gamelib.match_rank(priority_patterns, game_name)
                        priority_order[game_name] = (
                            rank if rank is not None
                            else detected_order.get(game_name, MAX_INT)
                        )
                next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
                # sorted_campaigns: list[DropsCampaign] = list(self.inventory)
                sorted_campaigns: list[DropsCampaign] = self.inventory
                if not priority_only:
                    if priority_mode is PriorityMode.ENDING_SOONEST:
                        sorted_campaigns.sort(key=lambda c: c.ends_at)
                    elif priority_mode is PriorityMode.LOW_AVBL_FIRST:
                        sorted_campaigns.sort(key=lambda c: c.availability)
                sorted_campaigns.sort(
                    key=lambda c: priority_order.get(c.game.name, MAX_INT)
                )
                for campaign in sorted_campaigns:
                    game: Game = campaign.game
                    if (
                        game not in self.wanted_games  # isn't already there
                        # and isn't excluded by list or priority mode
                        and not gamelib.any_match(exclude_patterns, game.name)
                        # NOTE: a rank below MAX_INT means the game either matched a priority
                        # list entry, or was detected as installed - both count as wanted
                        # under priority-only mode
                        and (
                            not priority_only
                            or priority_order.get(game.name, MAX_INT) < MAX_INT
                        )
                        # and can be progressed within the next hour
                        and campaign.can_earn_within(next_hour)
                    ):
                        # non-excluded games with no priority are placed last, below priority ones
                        self.wanted_games.append(game)
                # show the user what all of the above actually settled on
                self.gui.settings.set_wanted_games(self.wanted_games)
                full_cleanup = True
                self.restart_watching()
                watch_restarted = True
                self.change_state(State.CHANNELS_CLEANUP)
            elif self._state is State.CHANNELS_CLEANUP:
                self.gui.status.update(_("gui", "status", "cleanup"))
                if not self.wanted_games or full_cleanup:
                    # no games selected or we're doing full cleanup: remove everything
                    to_remove_channels: list[Channel] = list(channels.values())
                else:
                    # remove all channels that:
                    to_remove_channels = [
                        channel
                        for channel in channels.values()
                        if (
                            not channel.acl_based  # aren't ACL-based
                            and (
                                channel.offline  # and are offline
                                # or online but aren't streaming the game we want anymore
                                or (channel.game is None or channel.game not in self.wanted_games)
                            )
                        )
                    ]
                full_cleanup = False
                # removing a channel's row drops its selection, which the fetch restores when it adds the channel back
                selection = self.gui.channels.get_selection()
                removed_selection = (
                    selection.id if selection is not None and selection in to_remove_channels else None
                )
                if to_remove_channels:
                    to_remove_topics: list[str] = []
                    for channel in to_remove_channels:
                        to_remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamState", channel.id)
                        )
                        to_remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamUpdate", channel.id)
                        )
                    self.websocket.remove_topics(to_remove_topics)
                    for channel in to_remove_channels:
                        del channels[channel.id]
                        channel.remove()
                    del to_remove_channels, to_remove_topics
                if self.wanted_games:
                    self._no_campaign_printed = False
                    self.change_state(State.CHANNELS_FETCH)
                else:
                    # with no games available, we switch to IDLE after cleanup
                    if not self._no_campaign_printed:
                        self.print(_("status", "no_campaign"))
                        self._no_campaign_printed = True
                    self.change_state(State.IDLE)
            elif self._state is State.CHANNELS_FETCH:
                self.gui.status.update(_("gui", "status", "gathering"))
                # start with all current channels
                # NOTE: the GUI list is only rebuilt further below, and only if needed
                new_channels: set[Channel] = set(channels.values())
                # gather and add ACL channels from campaigns
                # NOTE: we consider only campaigns that can be progressed
                # NOTE: we use another set so that we can set them online separately
                no_acl: set[Game] = set()
                acl_channels: set[Channel] = set()
                # the best priority of the wanted games whose campaigns list the channel in their ACL
                acl_priority: dict[Channel, int] = {}
                next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
                for campaign in self.inventory:
                    if (
                        campaign.game in self.wanted_games
                        and campaign.can_earn_within(next_hour)
                    ):
                        if campaign.allowed_channels:
                            acl_channels.update(campaign.allowed_channels)
                            game_priority = self.wanted_games.index(campaign.game)
                            for channel in campaign.allowed_channels:
                                acl_priority[channel] = min(game_priority, acl_priority.get(channel, game_priority))
                        else:
                            no_acl.add(campaign.game)
                # remove all ACL channels that already exist from the other set
                acl_channels.difference_update(new_channels)
                # use the other set to set them online if possible
                await self.bulk_check_online(acl_channels)
                # finally, add them as new channels
                new_channels.update(acl_channels)
                for game in no_acl:
                    # for every campaign without an ACL, for it's game,
                    # add a list of live channels with drops enabled
                    new_channels.update(await self.get_live_streams(game, drops_enabled=True))
                # sort them descending by viewers, by priority and by game priority
                # NOTE: Viewers sort also ensures ONLINE channels are sorted to the top
                # NOTE: We can drop using the set now, because there's no more channels being added
                ordered_channels: list[Channel] = sorted(
                    new_channels, key=self._viewers_key, reverse=True
                )
                ordered_channels.sort(key=lambda ch: ch.acl_based, reverse=True)
                ordered_channels.sort(key=self.get_priority)
                # ensure that we won't end up with more channels than we can handle,
                # keeping the list in this order
                selection = self.gui.channels.get_selection()
                kept_channels = set(
                    self._slot_order(
                        ordered_channels,
                        acl_priority,
                        selection.id if selection is not None else removed_selection,
                    )[:MAX_CHANNELS]
                )
                to_remove_channels = [ch for ch in ordered_channels if ch not in kept_channels]
                ordered_channels = [ch for ch in ordered_channels if ch in kept_channels]
                if to_remove_channels:
                    # the tracked channels and the gui list are replaced below,
                    # so unsubscribe from their topics and cancel their online checks
                    to_remove_topics = []
                    for channel in to_remove_channels:
                        channel.cancel_online_check()
                        to_remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamState", channel.id)
                        )
                        to_remove_topics.append(
                            WebsocketTopic.as_str("Channel", "StreamUpdate", channel.id)
                        )
                    self.websocket.remove_topics(to_remove_topics)
                    del to_remove_channels, to_remove_topics
                # Only tear the gui list down when the set of channels actually changed.
                # A periodic refresh usually ends up with the exact same channels, and
                # rebuilding the table every time would flicker and drop the user's selection.
                gui_selection: Channel | None = None
                if self.gui.channels.get_iids() != set(
                    channel.iid for channel in ordered_channels
                ):
                    gui_selection = selection
                    self.gui.channels.clear()
                # set our new channel list
                # NOTE: a stream event during the awaits above looks up its channel in this map,
                # so the old channels stay in it until no await is left
                channels.clear()
                for channel in ordered_channels:
                    channels[channel.id] = channel
                    channel.display(add=True)
                # restore the selection, or the one the cleanup removed, as long as the channel is still on the list
                selection_id = gui_selection.id if gui_selection is not None else removed_selection
                if selection_id is not None and selection_id in channels:
                    self.gui.channels.set_selection(channels[selection_id])
                # subscribe to these channel's state updates
                to_add_topics: list[WebsocketTopic] = []
                for channel_id in channels:
                    to_add_topics.append(
                        WebsocketTopic(
                            "Channel", "StreamState", channel_id, self.process_stream_state
                        )
                    )
                    to_add_topics.append(
                        WebsocketTopic(
                            "Channel", "StreamUpdate", channel_id, self.process_stream_update
                        )
                    )
                self.websocket.add_topics(to_add_topics)
                # relink watching channel after cleanup,
                # or stop watching it if it no longer qualifies
                # NOTE: this replaces 'self.watching_channel's internal value with the new object
                watching_channel = self.watching_channel.get_with_default(None)
                if watching_channel is not None:
                    new_watching: Channel | None = channels.get(watching_channel.id)
                    if new_watching is not None and self.can_watch(new_watching):
                        self.watch(new_watching, update_status=False)
                    else:
                        # we've removed a channel we were watching
                        self.stop_watching()
                    del new_watching
                # Show the active drop one minute lower when a watch starts or GAMES_UPDATE restarted it.
                # This stops the countdown, so a refresh that keeps the watched channel skips it.
                if watch_restarted or not self.watching_channel.has_value():
                    for channel in channels.values():
                        # check if there's any channels we can watch first
                        if self.can_watch(channel):
                            if (
                                (active_campaign := self.get_active_campaign(channel)) is not None
                                and (active_drop := active_campaign.first_drop) is not None
                            ):
                                active_drop.display(countdown=False, subone=True)
                            break
                watch_restarted = False
                self.change_state(State.CHANNEL_SWITCH)
                del (
                    no_acl,
                    acl_channels,
                    acl_priority,
                    kept_channels,
                    new_channels,
                    to_add_topics,
                    ordered_channels,
                    watching_channel,
                )
            elif self._state is State.CHANNEL_SWITCH:
                if self.settings.dump:
                    self.gui.close()
                    continue
                self.gui.status.update(_("gui", "status", "switching"))
                # Change into the selected channel, stay in the watching channel,
                # or select a new channel that meets the required conditions
                new_watching = None
                selected_channel = self.gui.channels.get_selection()
                if selected_channel is not None and self.can_watch(selected_channel):
                    # selected channel is checked first, and set as long as we can watch it
                    new_watching = selected_channel
                else:
                    # other channels, the watched one included, must pass should_switch
                    # NOTE: sorted on every switch, because a channel can change its game
                    for channel in sorted(channels.values(), key=self.get_priority):
                        if self.should_switch(channel):
                            new_watching = channel
                            break
                watching_channel = self.watching_channel.get_with_default(None)
                # NOTE: a GUI-selected channel skips the 'should_switch' check above, so it ends
                # up here even when it's already the one being watched - re-watching it would
                # reprint the status, which gets noisy with periodic refreshes enabled
                if new_watching is not None and new_watching != watching_channel:
                    # if we have a better switch target - do so
                    self.watch(new_watching)
                elif watching_channel is not None and self.can_watch(watching_channel):
                    # otherwise, continue watching what we had before
                    self.gui.status.update(
                        _("status", "watching").format(channel=watching_channel.name)
                    )
                else:
                    # not watching anything and there isn't anything to watch either
                    if not self._no_channel_printed:
                        self.print(_("status", "no_channel"))
                        self._no_channel_printed = True
                    self.change_state(State.IDLE)
                del new_watching, selected_channel, watching_channel
            elif self._state is State.RESTART:
                if self._task_error is not None:
                    raise self._task_error
                raise ReloadRequest()
            elif self._state is State.EXIT:
                self.gui.tray.change_icon("pickaxe")
                self.gui.status.update(_("gui", "status", "exiting"))
                # we've been requested to exit the application
                break
            await self._state_change.wait()

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

    def can_watch(self, channel: Channel) -> bool:
        """
        Determines if the given channel qualifies as a watching candidate.
        """
        # exit early if stream is offline
        if not channel.online:
            return False
        for campaign in self.inventory:
            if (
                # limit watching to the games the user wants
                campaign.game in self.wanted_games
                and campaign.can_earn(channel)  # let the campaign do the "special games" check
                and (
                    channel.game is not None
                    and channel.drops_enabled
                    and channel.game in self.wanted_games
                    # let the campaign ignore all channel-related checks
                    or campaign.game.is_special()
                )
            ):
                return True
        return False

    def should_switch(self, channel: Channel) -> bool:
        """
        Determines if the given channel qualifies as a switch candidate.
        """
        if not self.can_watch(channel):
            return False
        watching_channel = self.watching_channel.get_with_default(None)
        if watching_channel is None or not self.can_watch(watching_channel):
            return True
        channel_order = self.get_priority(channel)
        watching_order = self.get_priority(watching_channel)
        return (
            # this channel's game is higher order than the watching one's
            channel_order < watching_order
            or channel_order == watching_order  # or the order is the same
            # and this channel is ACL-based and the watching channel isn't
            and channel.acl_based > watching_channel.acl_based
        )

    def watch(self, channel: Channel, *, update_status: bool = True):
        # we have something to watch again, so allow the "no channels" message through next time
        self._no_channel_printed = False
        self.gui.tray.change_icon("active")
        self.gui.channels.set_watching(channel)
        self.watching_channel.set(channel)
        if update_status:
            status_text = _("status", "watching").format(channel=channel.name)
            self.print(status_text)
            self.gui.status.update(status_text)

    def stop_watching(self):
        self.gui.clear_drop()
        self.watching_channel.clear()
        self.gui.channels.clear_watching()

    def restart_watching(self):
        self.gui.progress.stop_timer()
        self._watching_restart.set()

    @task_wrapper
    async def process_stream_state(self, channel_id: int, message: JsonType):
        msg_type = message["type"]
        channel = self.channels.get(channel_id)
        if channel is None:
            logger.error(f"Stream state change for a non-existing channel: {channel_id}")
            return
        if msg_type == "viewcount":
            if not channel.online:
                # if it's not online for some reason, set it so
                channel.check_online()
            else:
                viewers = message["viewers"]
                channel.viewers = viewers
                channel.display()
                # logger.debug(f"{channel.name} viewers: {viewers}")
        elif msg_type == "stream-down":
            channel.set_offline()
        elif msg_type == "stream-up":
            channel.check_online()
        elif msg_type == "commercial":
            # skip these
            pass
        else:
            logger.warning(f"Unknown stream state: {msg_type}")

    @task_wrapper
    async def process_stream_update(self, channel_id: int, message: JsonType):
        # The message has "channel_id", "type" ("broadcast_settings_update"), "channel", and
        # "status" (the title), "game" and "game_id", each with its "old_" value.
        channel = self.channels.get(channel_id)
        if channel is None:
            logger.error(f"Broadcast settings update for a non-existing channel: {channel_id}")
            return
        if message["old_game"] != message["game"]:
            game_change = f", game changed: {message['old_game']} -> {message['game']}"
        else:
            game_change = ''
        logger.log(CALL, f"Channel update from websocket: {channel.name}{game_change}")
        # The message has no tags, but Twitch sends it when the tags change too. check_online
        # fetches the stream after a delay, so several changes in a row cost one fetch, and
        # that fetch calls on_channel_update.
        channel.check_online()

    def on_channel_update(
        self, channel: Channel, stream_before: Stream | None, stream_after: Stream | None
    ):
        """
        Called by a Channel when it's status is updated (ONLINE, OFFLINE, title/tags change).

        NOTE: 'stream_before' gets dealocated once this function finishes.
        """
        if stream_before is None:
            if stream_after is not None:
                # Channel going ONLINE
                if self.should_switch(channel):
                    # we can watch the channel, and we should
                    self.print(_("status", "goes_online").format(channel=channel.name))
                    self.watch(channel)
                else:
                    logger.info(f"{channel.name} goes ONLINE")
            else:
                # Channel was OFFLINE and stays that way
                logger.log(CALL, f"{channel.name} stays OFFLINE")
        else:
            watching_channel = self.watching_channel.get_with_default(None)
            # check if the watching channel was the one updated
            if watching_channel is not None and watching_channel == channel:
                # NOTE: In these cases, channel was the watching channel
                if not self.can_watch(channel):
                    # we can't watch it anymore
                    if stream_after is None:
                        # Channel going OFFLINE
                        self.print(_("status", "goes_offline").format(channel=channel.name))
                    else:
                        # Channel stays ONLINE, but we can't watch it anymore
                        logger.info(
                            f"{channel.name} status has been updated, switching... "
                            f"(🎁: {stream_before.drops_enabled and '✔' or '❌'} -> "
                            f"{stream_after.drops_enabled and '✔' or '❌'})"
                        )
                    self.change_state(State.CHANNEL_SWITCH)
                else:
                    # Channel stays ONLINE, and we can still watch it - no change
                    pass
            # NOTE: In these cases, it wasn't the watching channel
            elif stream_after is None:
                logger.info(f"{channel.name} goes OFFLINE")
            else:
                # Channel stays ONLINE, but has been updated
                logger.info(
                    f"{channel.name} status has been updated "
                    f"(🎁: {stream_before.drops_enabled and '✔' or '❌'} -> "
                    f"{stream_after.drops_enabled and '✔' or '❌'})"
                )
                if self.should_switch(channel):
                    # ... and we should watch it
                    self.watch(channel)
        channel.display()

    @task_wrapper
    async def process_drops(self, user_id: int, message: JsonType):
        # Message examples:
        # {"type": "drop-progress", data: {"current_progress_min": 3, "required_progress_min": 10}}
        # {"type": "drop-claim", data: {"drop_instance_id": ...}}
        msg_type: str = message["type"]
        if msg_type not in ("drop-progress", "drop-claim"):
            return
        drop_id: str = message["data"]["drop_id"]
        drop: TimedDrop | None = self._drops.get(drop_id)
        watching_channel: Channel | None = self.watching_channel.get_with_default(None)
        if msg_type == "drop-claim":
            if drop is None:
                logger.error(
                    f"Received a drop claim ID for a non-existing drop: {drop_id}\n"
                    f"Drop claim ID: {message['data']['drop_instance_id']}"
                )
                return
            if drop.is_claimed:
                # GAMES_UPDATE or an earlier event claimed it and already restarted watching or reloaded
                return
            drop.update_claim(message["data"]["drop_instance_id"])
            campaign = drop.campaign
            await drop.claim()
            drop.display()
            # About 4-20s after claiming the drop, next drop can be started
            # by re-sending the watch payload. We can test for it by fetching the current drop
            # via GQL, and then comparing drop IDs.
            await asyncio.sleep(4)
            if watching_channel is not None:
                for attempt in range(8):
                    context = await self.gql_request(
                        GQL_QUERIES["CurrentDrop"].with_variables(
                            {"channelID": str(watching_channel.id)}
                        )
                    )
                    drop_data: JsonType | None = current_drop(context)
                    if drop_data is None or drop_data["dropID"] != drop.id:
                        break
                    await asyncio.sleep(2)
            if campaign.can_earn(watching_channel):
                self.restart_watching()
            else:
                self.change_state(State.INVENTORY_FETCH)
            return
        assert msg_type == "drop-progress"
        if drop is not None:
            drop_text = (
                f"{drop.name} ({drop.campaign.game}, "
                f"{message['data']['current_progress_min']}/"
                f"{message['data']['required_progress_min']})"
            )
        else:
            drop_text = "<Unknown>"
        logger.log(CALL, f"Drop update from websocket: {drop_text}")
        if drop is not None and drop.can_earn(self.watching_channel.get_with_default(None)):
            # the received payload is for the drop we expected
            drop.update_minutes(message["data"]["current_progress_min"])

    @task_wrapper
    async def process_notifications(self, user_id: int, message: JsonType):
        if message["type"] == "create-notification":
            data: JsonType = message["data"]["notification"]
            if data["type"] in (
                "user_drop_reward_reminder_notification",  # drop confirmation
                "quests_viewer_reward_campaign_earned_emote",  # emote confirmation
                # badge confirmation?
            ):
                self.change_state(State.INVENTORY_FETCH)
                await self.gql_request(
                    GQL_QUERIES["NotificationsDelete"].with_variables(
                        {"input": {"id": data["id"]}}
                    )
                )

    def get_active_campaign(self, channel: Channel | None = None) -> DropsCampaign | None:
        if not self.wanted_games:
            return None
        watching_channel = self.watching_channel.get_with_default(channel)
        if watching_channel is None:
            # with no watched channel, no drop makes progress
            return None
        campaigns: list[DropsCampaign] = []
        for campaign in self.inventory:
            if campaign.can_earn(watching_channel):
                campaigns.append(campaign)
        if campaigns:
            campaigns.sort(key=lambda c: c.remaining_minutes)
            return campaigns[0]
        return None

    async def get_live_streams(
        self, game: Game, *, limit: int = 20, drops_enabled: bool = True
    ) -> list[Channel]:
        filters: list[str] = []
        if drops_enabled:
            filters.append("DROPS_ENABLED")
        try:
            response = await self.gql_request(
                GQL_QUERIES["GameDirectory"].with_variables({
                    "limit": limit,
                    "slug": game.slug,
                    "options": {
                        "includeRestricted": ["SUB_ONLY_LIVE"],
                        "systemFilters": filters,
                    },
                })
            )
        except GQLException as exc:
            raise MinerException(f"Game: {game.slug}") from exc
        return [
            Channel.from_directory(self, stream_data, drops_enabled=drops_enabled)
            for stream_data in directory_streams(response)
        ]

    async def bulk_check_online(self, channels: abc.Iterable[Channel]):
        """
        Uses batched GQL requests to check the ONLINE status of many channels at once.
        Also handles the drops_enabled check (if enabled).
        """
        acl_streams_map: dict[int, JsonType] = {}
        stream_gql_ops: list[GQLOperation] = [channel.stream_gql for channel in channels]
        if not stream_gql_ops:
            # shortcut for nothing to process
            # NOTE: Have to do this here, becase "channels" can be any iterable
            return
        stream_gql_tasks: list[asyncio.Task[list[JsonType]]] = [
            asyncio.create_task(self.gql_request(stream_gql_chunk))
            for stream_gql_chunk in chunk(stream_gql_ops, 20)
        ]
        try:
            for coro in asyncio.as_completed(stream_gql_tasks):
                acl_streams_map.update(channel_streams(await coro))
        except Exception:
            # asyncio.as_completed doesn't cancel tasks on errors
            for task in stream_gql_tasks:
                task.cancel()
            raise
        # for all channels with an active stream, check the available drops as well
        acl_available_drops_map: dict[int, list[JsonType]] = {}
        if self.settings.available_drops_check:
            available_gql_ops: list[GQLOperation] = [
                GQL_QUERIES["AvailableDrops"].with_variables({"channelID": str(channel_id)})
                for channel_id, channel_data in acl_streams_map.items()
                if channel_data["stream"] is not None  # only do this for ONLINE channels
            ]
            available_gql_tasks: list[asyncio.Task[list[JsonType]]] = [
                asyncio.create_task(self.gql_request(available_gql_chunk))
                for available_gql_chunk in chunk(available_gql_ops, 20)
            ]
            try:
                for coro in asyncio.as_completed(available_gql_tasks):
                    acl_available_drops_map.update(channel_campaigns(await coro))
            except Exception:
                # asyncio.as_completed doesn't cancel tasks on errors
                for task in available_gql_tasks:
                    task.cancel()
                raise
        for channel in channels:
            channel_id = channel.id
            if channel_id not in acl_streams_map:
                # a server error also sets the user to null, so a missing channel keeps its stream
                continue
            channel_data = acl_streams_map[channel_id]
            available_drops: list[JsonType] = acl_available_drops_map.get(channel_id, [])
            channel.external_update(channel_data, available_drops)
