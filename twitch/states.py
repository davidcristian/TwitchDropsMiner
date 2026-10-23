"""The mixin of `Twitch` with `_run`, the state machine, and the states that add or remove no tracked channel."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Final, NoReturn, TYPE_CHECKING

import gamelib
from translate import _
from savefiles import save_each
from exceptions import ReloadRequest
from constants import MAX_INT, State, PriorityMode
from twitchapi import WebsocketTopic

if TYPE_CHECKING:
    from collections import abc, OrderedDict

    from gui import GUIManager
    from channel import Channel
    from settings import Settings
    from websocket import WebsocketPool
    from inventory import DropsCampaign
    from utils import AwaitableValue, Game
    from constants import JsonType

    from .session import _AuthState


logger = logging.getLogger("TwitchDrops")


class StatesMixin:
    """The methods of `Twitch` that run `_run` and its states `INVENTORY_FETCH`, `GAMES_UPDATE` and `CHANNEL_SWITCH`."""

    settings: Settings
    gui: GUIManager
    websocket: WebsocketPool
    channels: OrderedDict[int, Channel]
    inventory: list[DropsCampaign]
    wanted_games: list[Game]
    watching_channel: AwaitableValue[Channel]
    _state: State
    _state_change: asyncio.Event
    _task_error: Exception | None
    _no_channel_printed: bool
    _watching_task: asyncio.Task[None] | None
    _watch_loop: abc.Callable[[], abc.Coroutine[Any, Any, NoReturn]]
    get_auth: abc.Callable[[], abc.Coroutine[Any, Any, _AuthState]]
    fetch_inventory: abc.Callable[[], abc.Coroutine[Any, Any, None]]
    detect_games: abc.Callable[[], abc.Coroutine[Any, Any, None]]
    print: abc.Callable[[str], None]
    change_state: abc.Callable[[State], None]
    get_priority: abc.Callable[[Channel], int]
    can_watch: abc.Callable[[Channel], bool]
    should_switch: abc.Callable[[Channel], bool]
    watch: abc.Callable[..., None]
    stop_watching: abc.Callable[[], None]
    restart_watching: abc.Callable[[], None]
    process_drops: abc.Callable[[int, JsonType], abc.Coroutine[Any, Any, None]]
    process_notifications: abc.Callable[[int, JsonType], abc.Coroutine[Any, Any, None]]
    _run_channels_cleanup: abc.Callable[..., tuple[bool, int | None]]
    _run_channels_fetch: abc.Callable[..., abc.Coroutine[Any, Any, bool]]

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
                await self._run_inventory_fetch()
            elif self._state is State.GAMES_UPDATE:
                full_cleanup, watch_restarted = await self._run_games_update()
            elif self._state is State.CHANNELS_CLEANUP:
                full_cleanup, removed_selection = self._run_channels_cleanup(channels, full_cleanup)
            elif self._state is State.CHANNELS_FETCH:
                watch_restarted = await self._run_channels_fetch(channels, watch_restarted, removed_selection)
            elif self._state is State.CHANNEL_SWITCH:
                if self.settings.dump:
                    self.gui.close()
                    continue
                self._run_channel_switch(channels)
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

    async def _run_inventory_fetch(self) -> None:
        """Run State.INVENTORY_FETCH: reload the inventory, detect the installed games and save the state."""
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

    async def _run_games_update(self) -> tuple[bool, bool]:
        """
        Run State.GAMES_UPDATE: claim the drops that can be claimed and compute wanted_games.
        Returns full_cleanup and watch_restarted, both True, which CHANNELS_CLEANUP and CHANNELS_FETCH read.
        """
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
        return full_cleanup, watch_restarted

    def _run_channel_switch(self, channels: OrderedDict[int, Channel]) -> None:
        """Run State.CHANNEL_SWITCH: watch the selected channel or the first that should_switch accepts."""
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
