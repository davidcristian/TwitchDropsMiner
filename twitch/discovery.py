"""The mixin of `Twitch` that detects the installed games and finds the live channels to watch."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Final, TYPE_CHECKING

import gamelib
from translate import _
from channel import Channel
from exceptions import GQLException, MinerException
from streamdata import channel_streams, channel_campaigns, directory_streams
from utils import chunk
from constants import CALL, State
from twitchapi import GQL_QUERIES

if TYPE_CHECKING:
    from collections import abc

    from gui import GUIManager
    from utils import Game
    from settings import Settings
    from inventory import DropsCampaign
    from constants import JsonType
    from twitchapi import GQLOperation


logger = logging.getLogger("TwitchDrops")
# The translation key, in gui.settings.detect, of the text of each kind of scan error
SCAN_ERROR_KEYS: Final[dict[gamelib.ScanErrorKind, str]] = {
    gamelib.ScanErrorKind.NOT_A_FOLDER: "not_a_folder",
    gamelib.ScanErrorKind.NO_GAMES: "no_games",
    gamelib.ScanErrorKind.FAILED: "failed",
}


class DiscoveryMixin:
    """The methods of `Twitch` that scan the game folders, list the live channels of a game and check channels."""

    settings: Settings
    gui: GUIManager
    inventory: list[DropsCampaign]
    _scan_errors_printed: set[gamelib.ScanError]
    _scanning_games: bool
    print: abc.Callable[[str], None]
    change_state: abc.Callable[[State], None]
    gql_request: abc.Callable[..., abc.Coroutine[Any, Any, Any]]

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
