"""Read the stream and channel data of GQL responses, in which a server error leaves the field it names null."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gqldata import get_field

if TYPE_CHECKING:
    from constants import JsonType


logger = logging.getLogger("TwitchDrops")


def _stream_game(channel_id: int, game: JsonType | None) -> JsonType | None:
    """Return the game of a channel's stream, or None when it is null or Game cannot read its ID or name."""
    if game is None:
        return None
    if game.get("id") is None or (game.get("displayName") or game.get("name")) is None:
        logger.warning(
            f"Read the stream of channel {channel_id} without a game, because its game has a null ID or name"
        )
        return None
    return game


def _readable_user(channel_id: int, user: JsonType) -> JsonType:
    """Return a GetStreamInfo user whose stream and game Stream can read, or with no stream when its ID is null."""
    stream = user.get("stream")
    if stream is not None and stream.get("id") is None:
        logger.warning(f"Read channel {channel_id} as offline, because its stream has a null ID")
        stream = None
    if stream is None:
        return {**user, "stream": None}
    settings = user.get("broadcastSettings")
    if settings is None:
        logger.warning(
            f"Read the stream of channel {channel_id} without a game, because its broadcast settings are null"
        )
        settings = {"title": None}
    return {**user, "broadcastSettings": {**settings, "game": _stream_game(channel_id, settings.get("game"))}}


def channel_streams(responses: list[JsonType]) -> dict[int, JsonType]:
    """Return the user of each GetStreamInfo response by its channel ID, leaving out a null user or ID."""
    users: dict[int, JsonType] = {}
    for response in responses:
        user = get_field(response, "data", "user")
        if user is None:
            continue
        if user.get("id") is None:
            logger.warning("Skipped a channel with a null ID in a GetStreamInfo response")
            continue
        channel_id = int(user["id"])
        users[channel_id] = _readable_user(channel_id, user)
    return users


def channel_stream(response: JsonType, channel_id: int) -> JsonType | None:
    """Return the user of a channel's GetStreamInfo response, or None when it is null."""
    user = get_field(response, "data", "user")
    return None if user is None else _readable_user(channel_id, user)


def directory_streams(response: JsonType) -> list[JsonType]:
    """Return the streams of a GameDirectory response that Channel and Stream can read, or none for a null game."""
    edges = get_field(response, "data", "game", "streams", "edges") or []
    streams: list[JsonType] = []
    for node in (get_field(edge, "node") for edge in edges):
        broadcaster = get_field(node, "broadcaster")
        if broadcaster is None:
            continue
        if any(value is None for value in (node.get("id"), broadcaster.get("id"), broadcaster.get("login"))):
            logger.warning("Skipped a GameDirectory stream with a null ID, broadcaster ID or login")
            continue
        streams.append({**node, "game": _stream_game(int(broadcaster["id"]), node.get("game"))})
    return streams


def _readable_campaigns(channel_id: int, campaigns: list[JsonType | None] | None) -> list[JsonType]:
    """Return a channel's AvailableDrops campaigns without a null campaign or one with a null ID."""
    campaigns = campaigns or []
    readable = [campaign for campaign in campaigns if get_field(campaign, "id") is not None]
    if len(readable) < len(campaigns):
        logger.warning(
            f"Skipped {len(campaigns) - len(readable)} available campaigns of channel {channel_id},"
            " which are null or have a null ID"
        )
    return readable


def channel_campaigns(responses: list[JsonType]) -> dict[int, list[JsonType]]:
    """Return the drop campaigns of each channel in AvailableDrops responses, leaving out a null channel or ID."""
    campaigns: dict[int, list[JsonType]] = {}
    for response in responses:
        channel = get_field(response, "data", "channel")
        if channel is None:
            continue
        if channel.get("id") is None:
            logger.warning("Skipped a channel with a null ID in an AvailableDrops response")
            continue
        channel_id = int(channel["id"])
        campaigns[channel_id] = _readable_campaigns(channel_id, channel.get("viewerDropCampaigns"))
    return campaigns


def available_campaigns(response: JsonType, channel_id: int) -> list[JsonType]:
    """Return the drop campaigns of one channel's AvailableDrops response, or none when its channel is null."""
    return _readable_campaigns(channel_id, get_field(response, "data", "channel", "viewerDropCampaigns"))


def playback_token(response: JsonType) -> tuple[str, str] | None:
    """Return the value and signature of a PlaybackAccessToken response, or None when the token or either is null."""
    token = get_field(response, "data", "streamPlaybackAccessToken")
    value, signature = get_field(token, "value"), get_field(token, "signature")
    if value is None or signature is None:
        return None
    return value, signature

