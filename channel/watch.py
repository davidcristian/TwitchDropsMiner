"""The mixin of `Channel` that sends the requests that watch its stream."""
from __future__ import annotations

import re
import json
import asyncio
import logging
from typing import Any, TYPE_CHECKING

from exceptions import MinerException, RequestException
from constants import URLType

if TYPE_CHECKING:
    from collections import abc

    from twitch import Twitch
    from constants import JsonType
    from .stream import Stream


logger = logging.getLogger("TwitchDrops")


class WatchMixin:
    """The methods of `Channel` that send the watch requests of its stream."""

    __slots__ = ()

    _twitch: Twitch
    _spade_url: URLType | None
    _stream: Stream | None
    _pending_stream_up: asyncio.Task[Any] | None
    url: URLType
    check_online: abc.Callable[[], None]

    async def get_spade_url(self) -> URLType:
        """
        Returns the spade URL read from the channel page, or from the settings script it links.
        """
        SETTINGS_PATTERN: str = r'src="(https://[\w.]+/config/settings\.[0-9a-f]{32}\.js)"'
        SPADE_PATTERN: str = r'"spade_?url": ?"(https://[.\w\-/]+)"'
        async with self._twitch.request("GET", self.url) as response1:
            streamer_html: str = await response1.text(encoding="utf8")
        match = re.search(SPADE_PATTERN, streamer_html, re.I)
        if not match:
            match = re.search(SETTINGS_PATTERN, streamer_html, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #1")
            streamer_settings = match.group(1)
            async with self._twitch.request("GET", streamer_settings) as response2:
                settings_js: str = await response2.text(encoding="utf8")
            match = re.search(SPADE_PATTERN, settings_js, re.I)
            if not match:
                raise MinerException("Error while spade_url extraction: step #2")
        return URLType(match.group(1))

    # async def _send_watch_playlist(self) -> bool:
    async def send_watch(self) -> bool:
        """
        This performs a HEAD request on the stream's current playlist,
        to simulate watching the stream.
        Optimally, send every ~20 seconds to advance drops.
        """
        stream = self._stream
        if stream is None:
            return False
        # get the stream url
        stream_url = await stream.get_stream_url()
        if stream_url is None:
            return False
        # fetch a list of chunks available to download for the stream
        # NOTE: the CDN is configured to forcibly disconnect shortly after serving the list,
        # if we don't do it yourselves. Lets help it by actually doing it ourselves instead.
        async with self._twitch.request(
            "GET", stream_url, headers={"Connection": "close"}
        ) as chunks_response:
            if chunks_response.status >= 400:
                # The playlist returns 404 once the stream has ended, and stream-down can be missed.
                # Request usher again and check the stream, once per online check, not every cycle.
                if self._stream is stream and self._pending_stream_up is None:
                    stream._stream_url = None
                    self.check_online()
                return False
            available_chunks: str = await chunks_response.text()
        # the response may contain some invalid JSON with duplicate double quotes
        # in the value strings: we need to get rid of them by removing the "url" key entirely
        # if no JSON can be found within the response, this is a NOOP
        available_chunks = re.sub(r'"url": ?".+}",', '', available_chunks)
        # try to decode the suspected JSON
        try:
            available_json: JsonType = json.loads(available_chunks)
        except json.JSONDecodeError:
            # No JSON: this is the expected path. Do nothing and continue with the below.
            pass
        else:
            # JSON was decoded - if there's an error, log it and report failure
            if isinstance(available_json, list):
                available_json = available_json[0]
            if "error" in available_json:
                logger.error(f"Send watch error: \"{available_json['error']}\"")
            return False
        # the list contains ~15 chunks of the stream at ~2s intervals
        chunks_list: list[URLType] = [
            URLType(chunk)
            for chunk in available_chunks.strip().split("\n")
            if chunk.startswith("http")
        ]
        for stream_chunk_url in chunks_list:
            # sending a HEAD request is enough to advance the drops,
            # without downloading the actual stream data
            async with self._twitch.request("HEAD", stream_chunk_url) as head_response:
                if head_response.status != 200:
                    return False
        return True

    # No caller. It stays, with get_spade_url and the Stream payloads, in case Twitch stops counting send_watch.
    async def _send_watch_spade(self) -> bool:
        if self._stream is None:
            return False
        if self._spade_url is None:
            self._spade_url = await self.get_spade_url()
        try:
            async with self._twitch.request(
                "POST", self._spade_url, data=self._stream.spade_payload
            ) as response:
                return response.status == 204
        except RequestException:
            return False

    # No caller. It stays in case Twitch stops counting the HEAD requests of send_watch.
    async def _send_watch_gql(self) -> bool:
        if self._stream is None:
            return False
        try:
            watch_response = await self._twitch.gql_request(self._stream.gql_payload)
            return watch_response["data"]["sendSpadeEvents"]["statusCode"] == 204
        except RequestException:
            return False
