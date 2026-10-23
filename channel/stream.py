"""`Stream`, the current broadcast of a channel, and the request for its playlist URL."""
from __future__ import annotations

import gzip
import json
import logging
from base64 import b64encode
from functools import cached_property
from typing import SupportsInt, cast, TYPE_CHECKING

import aiohttp
from yarl import URL

from streamdata import playback_token
from utils import Game, json_minify, isonow
from twitchapi import GQL_QUERIES, GQLQuery
from constants import URLType

if TYPE_CHECKING:
    from constants import JsonType
    from .tracked import Channel


logger = logging.getLogger("TwitchDrops")


class Stream:
    def __init__(
        self,
        channel: Channel,
        *,
        id: SupportsInt,
        game: JsonType | None,
        viewers: int,
        title: str,
    ):
        self.channel: Channel = channel
        self.broadcast_id = int(id)
        self.viewers: int = viewers
        self.drops_enabled: bool = not channel._twitch.settings.available_drops_check
        self.game: Game | None = Game(game) if game else None
        self.title: str = title
        self._stream_url: URLType | None = None
        self._token_missing: bool = False

    @cached_property
    def _watch_payload(self) -> list[JsonType]:
        return [
            {
                "event": "minute-watched",
                "properties": {
                    "broadcast_id": str(self.broadcast_id),
                    "channel_id": str(self.channel.id),
                    "channel": self.channel._login,
                    "client_time": isonow(),
                    "game": self.game.name if self.game is not None else "",
                    "game_id": str(self.game.id) if self.game is not None else "",
                    "hidden": False,
                    "is_live": True,
                    "live": True,
                    "logged_in": True,
                    "minutes_logged": 1,
                    "muted": False,
                    "user_id": self.channel._twitch._auth_state.user_id,
                }
            }
        ]

    @cached_property
    def spade_payload(self) -> JsonType:
        return {
            "data": (b64encode(json_minify(self._watch_payload).encode("utf8"))).decode("utf8")
        }

    @cached_property
    def gql_payload(self) -> GQLQuery:
        return GQLQuery(
            (
                "\n mutation SendEvents($input: SendSpadeEventsInput!) "
                "{\n sendSpadeEvents(input: $input) {\n statusCode\n}\n}\n"
            ),
            b64encode(
                gzip.compress(json_minify(self._watch_payload).encode("utf8"))
            ).decode("utf8")
        )

    @classmethod
    def from_get_stream(cls, channel: Channel, channel_data: JsonType) -> Stream:
        stream = channel_data["stream"]
        settings = channel_data["broadcastSettings"]
        return cls(
            channel,
            id=stream["id"],
            game=settings["game"],
            viewers=stream["viewersCount"],
            title=settings["title"],
        )

    @classmethod
    def from_directory(
        cls, channel: Channel, channel_data: JsonType, *, drops_enabled: bool = False
    ) -> Stream:
        self = cls(
            channel,
            id=channel_data["id"],
            game=channel_data["game"],
            viewers=channel_data["viewersCount"],
            title=channel_data["title"],
        )
        self.drops_enabled = drops_enabled
        return self

    def __eq__(self, other: object) -> bool:
        if isinstance(other, self.__class__):
            return self.broadcast_id == other.broadcast_id
        return NotImplemented

    async def get_stream_url(self) -> URLType | None:
        if self._stream_url is not None:
            return self._stream_url
        if self._token_missing:
            # one query per Stream, not one per watch cycle: the online check replaces this Stream
            self.channel.check_online()
            return None
        # get the stream playback access token from GQL
        playback_token_response: JsonType = await self.channel._twitch.gql_request(
            GQL_QUERIES["PlaybackAccessToken"].with_variables({"login": self.channel._login})
        )
        token = playback_token(playback_token_response)
        if token is None:
            logger.warning(f"No playback token for {self.channel.name}, so its stream is checked again")
            self._token_missing = True
            self.channel.check_online()
            return None
        token_value, token_signature = token
        # using the token, query Twitch for a list of all available stream qualities
        available_qualities: str = ''
        try:
            async with self.channel._twitch.request(
                "GET",
                URL(
                    "https://usher.ttvnw.net/api/channel/hls/"
                    f"{self.channel._login}.m3u8?sig={token_signature}&token={token_value}"
                ),
            ) as qualities_response:
                available_qualities = await qualities_response.text()
            # try to decode the suspected JSON
            try:
                available_json: JsonType = json.loads(available_qualities)
            except json.JSONDecodeError:
                # No JSON: this is the expected path. Do nothing and continue with the below.
                pass
            else:
                # JSON was decoded - if there's an error, log it and report failure
                if isinstance(available_json, list):
                    available_json = available_json[0]
                if "error" in available_json:
                    logger.error(f"Stream URL get error: \"{available_json['error']}\"")
                    self.channel.set_offline()
                return None
            # pick the last URL from the list, usually with the lowest quality stream
            self._stream_url = cast(URLType, URL(available_qualities.strip().split("\n")[-1]))
        except (aiohttp.InvalidURL, ValueError):
            self.channel._twitch.print(available_qualities)
            raise
        return self._stream_url
