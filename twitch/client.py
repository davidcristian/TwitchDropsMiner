"""`Twitch`, the client object: its attributes, `run`, the state requests and the choice of the channel to watch."""
from __future__ import annotations

import asyncio
from functools import partial
from collections import abc, deque, OrderedDict
from datetime import datetime
from typing import Final, TYPE_CHECKING

import aiohttp

import gamelib
from translate import _
from ratelimit import RateLimiter
from restartdelay import RestartDelay
from gui import GUIManager
from channel import Channel
from websocket import WebsocketPool
from inventory import DropsCampaign
from exceptions import (
    ExitRequest,
    ReloadRequest,
    RequestException,
)
from utils import AwaitableValue
from constants import (
    MAX_INT,
    DUMP_PATH,
    State,
)
from twitchapi import ClientType

from .session import SessionMixin, _AuthState
from .requests import RequestsMixin
from .inventoryfetch import InventoryFetchMixin
from .lifecycle import LifecycleMixin
from .states import StatesMixin
from .channels import ChannelsMixin
from .discovery import DiscoveryMixin
from .pubsub import PubSubMixin

if TYPE_CHECKING:
    from utils import Game
    from settings import Settings
    from inventory import TimedDrop
    from twitchapi import ClientInfo


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


class Twitch(
    SessionMixin, RequestsMixin, InventoryFetchMixin, LifecycleMixin, StatesMixin, ChannelsMixin, DiscoveryMixin,
    PubSubMixin,
):
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
