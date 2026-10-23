"""The mixin of `Channel` that checks whether the channel is live and stores its stream."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from streamdata import channel_stream, available_campaigns
from exceptions import ExitRequest, MinerException
from twitchapi import GQL_QUERIES
from constants import CALL, ONLINE_DELAY, ONLINE_TRIES

from .stream import Stream

if TYPE_CHECKING:
    from collections import abc

    from twitch import Twitch
    from constants import JsonType
    from twitchapi import GQLPersistedQuery


logger = logging.getLogger("TwitchDrops")


class OnlineMixin:
    """The methods of `Channel` that fetch its stream and change its online status."""

    __slots__ = ()

    _twitch: Twitch
    id: int
    _login: str
    _display_name: str | None
    _stream: Stream | None
    _pending_stream_up: asyncio.Task[Any] | None
    stream_gql: GQLPersistedQuery
    name: str
    online: bool
    display: abc.Callable[..., None]
    cancel_online_check: abc.Callable[[], None]

    def _check_drops_enabled(self, available_drops: list[JsonType]) -> bool:
        return any(
            (
                (campaign := self._twitch._campaigns.get(campaign_data["id"])) is not None
                and campaign.can_earn(self, ignore_channel_status=True)
            )
            for campaign_data in available_drops
        )

    def external_update(self, channel_data: JsonType, available_drops: list[JsonType]):
        """
        Update stream information based on data provided externally.

        Used for bulk-updates of channel statuses during reload.
        """
        if not channel_data["stream"]:
            self._stream = None
            return
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            stream.drops_enabled = self._check_drops_enabled(available_drops)
        self._stream = stream

    async def get_stream(self) -> Stream | None:
        try:
            response: JsonType = await self._twitch.gql_request(self.stream_gql)
        except MinerException as exc:
            raise MinerException(f"Channel: {self._login}") from exc
        channel_data = channel_stream(response, self.id)
        if not channel_data:
            return None
        # fill in display name
        if self._display_name is None:
            self._display_name = channel_data["displayName"]
        if not channel_data["stream"]:
            return None
        stream = Stream.from_get_stream(self, channel_data)
        if not stream.drops_enabled:
            try:
                available_drops_campaigns: JsonType = await self._twitch.gql_request(
                    GQL_QUERIES["AvailableDrops"].with_variables({"channelID": str(self.id)})
                )
            except MinerException:
                logger.log(CALL, f"AvailableDrops GQL call failed for channel: {self._login}")
            else:
                stream.drops_enabled = self._check_drops_enabled(
                    available_campaigns(available_drops_campaigns, self.id)
                )
        return stream

    async def update_stream(self, *, tries: int = 1) -> bool:
        """
        Fetches and stores the stream, and returns True when the channel is online.
        A channel that was offline is fetched up to tries times, ONLINE_DELAY apart, until it has a stream.
        """
        try:
            stream = await self.get_stream()
            for _ in range(tries - 1):
                if stream is not None or self._stream is not None:
                    break
                # Twitch can send 'stream-up' more than ONLINE_DELAY before the stream data
                await asyncio.sleep(ONLINE_DELAY.total_seconds())
                stream = await self.get_stream()
        finally:
            # An online check can be cancelled until its last request returns, and ends
            # before on_channel_update displays the new status.
            if self._pending_stream_up is asyncio.current_task():
                self._pending_stream_up = None
        if tries > 1 and stream is None and self._stream is None:
            logger.info(f"{self.name} has no stream after {tries} checks")
        old_stream = self._stream
        self._stream = stream
        self._twitch.on_channel_update(self, old_stream, stream)
        return stream is not None

    async def _online_delay(self):
        """
        The 'stream-up' event is sent before the stream actually goes online,
        so just wait a bit and check if it's actually online by then.
        """
        await asyncio.sleep(ONLINE_DELAY.total_seconds())
        try:
            await self.update_stream(tries=ONLINE_TRIES)
        except MinerException as exc:
            # nothing awaits this task, so its error is logged here, unless the window is closing
            if not isinstance(exc.__cause__, ExitRequest):
                logger.warning(f"The online check of {self.name} failed", exc_info=True)
                self.display()

    def check_online(self):
        """
        Starts a task that fetches the stream after ONLINE_DELAY, unless one is already waiting.
        """
        if self._pending_stream_up is None:
            self._pending_stream_up = asyncio.create_task(self._online_delay())
            self.display()

    def set_offline(self):
        """
        Sets the channel status to OFFLINE. Cancels PENDING_ONLINE if applicable.

        This is called externally, if we receive an event indicating the channel is now OFFLINE.
        """
        needs_display: bool = self._pending_stream_up is not None
        self.cancel_online_check()
        if self.online:
            old_stream = self._stream
            self._stream = None
            self._twitch.on_channel_update(self, old_stream, self._stream)
            needs_display = False  # calling on_channel_update always does a display at the end
        if needs_display:
            self.display()
