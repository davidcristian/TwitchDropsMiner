from __future__ import annotations

import asyncio
import logging
from typing import NamedTuple

import pytest

from channel import Channel
from constants import JsonType
from fakes import GAME, FakeTwitch, campaign_data, drop_data, gql_answers, stream_user
from inventory import DropsCampaign
from nullpaths import NullPath, null_paths, path_id, with_null
from utils import Game

USER = ("data", "user")
SETTINGS = (*USER, "broadcastSettings")
STREAM_INFO = {"data": {"user": {
    "id": "1",
    "login": "c1",
    "displayName": "C1",
    "stream": {"id": "101", "viewersCount": 5},
    "broadcastSettings": {"title": "Title", "game": {"id": "1", "name": "Game", "displayName": "Game"}},
}}}
# the stream that the channel has before a bulk check
EARLIER = {**stream_user(1, online=True), "stream": {"id": "99", "viewersCount": 1}}
# the app tracks the first campaign, so the channel counts as drops enabled while that one is listed
AVAILABLE = {"data": {"channel": {"id": "1", "viewerDropCampaigns": [
    {"id": "c1", "name": "Campaign"},
    {"id": "c9", "name": "Other campaign"},
]}}}
TRACKED = ("data", "channel", "viewerDropCampaigns", 0)
OTHER = ("data", "channel", "viewerDropCampaigns", 1)


class Seen(NamedTuple):
    """What the app reads of channel 1 after a check, the GQL operations it sent, and whether it logged a warning."""

    broadcast: int | None
    game: str | None
    viewers: int | None
    title: str | None
    name: str
    drops_enabled: bool
    sent: tuple[str, ...]
    warned: bool = False


BOTH = ("GetStreamInfo", "AvailableDrops")
LIVE = Seen(101, "Game", 5, "Title", "c1", True, BOTH)
OFFLINE = Seen(None, None, None, None, "c1", False, ("GetStreamInfo",))
KEPT = Seen(99, "Game", 1, "title", "c1", False, ("GetStreamInfo",))
# an online check also reads the display name
LIVE_NAMED = LIVE._replace(name="C1")


def stream_outcomes(live: Seen) -> dict[NullPath, Seen]:
    """Return the outcome of a null field of the stream, given the outcome of the complete response."""
    return {
        (*USER, "stream", "viewersCount"): live._replace(viewers=None),
        SETTINGS: live._replace(game=None, title=None, warned=True),
        (*SETTINGS, "title"): live._replace(title=None),
        (*SETTINGS, "game"): live._replace(game=None),
        (*SETTINGS, "game", "id"): live._replace(game=None, warned=True),
    }


# The outcome of each null path whose outcome differs from the complete response's.
STREAM_INFO_IN_BULK_CHECK = {
    ("data",): KEPT,
    USER: KEPT,
    (*USER, "id"): KEPT._replace(warned=True),
    (*USER, "stream"): OFFLINE,
    (*USER, "stream", "id"): OFFLINE._replace(warned=True),
    **stream_outcomes(LIVE),
}
STREAM_INFO_IN_ONLINE_CHECK = {
    ("data",): OFFLINE,
    USER: OFFLINE,
    (*USER, "displayName"): LIVE,
    (*USER, "stream"): OFFLINE._replace(name="C1"),
    (*USER, "stream", "id"): OFFLINE._replace(name="C1", warned=True),
    **stream_outcomes(LIVE_NAMED),
}
NOT_ENABLED = {"drops_enabled": False}
AVAILABLE_IN_BULK_CHECK = {
    ("data",): LIVE._replace(**NOT_ENABLED),
    ("data", "channel"): LIVE._replace(**NOT_ENABLED),
    ("data", "channel", "id"): LIVE._replace(**NOT_ENABLED, warned=True),
    ("data", "channel", "viewerDropCampaigns"): LIVE._replace(**NOT_ENABLED),
    TRACKED: LIVE._replace(**NOT_ENABLED, warned=True),
    (*TRACKED, "id"): LIVE._replace(**NOT_ENABLED, warned=True),
    OTHER: LIVE._replace(warned=True),
    (*OTHER, "id"): LIVE._replace(warned=True),
}
# an online check does not read the channel's ID
AVAILABLE_IN_ONLINE_CHECK = {
    **{path: seen._replace(name="C1") for path, seen in AVAILABLE_IN_BULK_CHECK.items()},
    ("data", "channel", "id"): LIVE_NAMED,
}


def warned(caplog: pytest.LogCaptureFixture) -> bool:
    return any(record.levelno == logging.WARNING for record in caplog.records)


def check(live_twitch, caplog, info: JsonType, available: JsonType, *, bulk: bool) -> Seen:
    """Check channel 1 with the bulk check, which ACL channels get, or with an online check, and return what is seen."""
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=info, AvailableDrops=available))
    fake.settings.available_drops_check = True
    twitch = live_twitch(fake)
    campaign = DropsCampaign(twitch, campaign_data([drop_data("d1")]), {})
    twitch._campaigns[campaign.id] = campaign
    channel = Channel(twitch, id=1, login="c1", acl_based=bulk)
    if bulk:
        channel.external_update(EARLIER, [])
    asyncio.run(twitch.bulk_check_online([channel]) if bulk else channel.update_stream())
    stream = channel._stream
    return Seen(
        stream and stream.broadcast_id,
        channel.game and channel.game.name,
        channel.viewers,
        stream and stream.title,
        channel.name,
        channel.drops_enabled,
        tuple(fake.gql_sent),
        warned(caplog),
    )


@pytest.mark.parametrize("path", null_paths(STREAM_INFO), ids=path_id)
def test_a_null_in_stream_info_gives_the_documented_stream_in_the_bulk_check(live_twitch, caplog, path):
    seen = check(live_twitch, caplog, with_null(STREAM_INFO, path), AVAILABLE, bulk=True)

    assert seen == STREAM_INFO_IN_BULK_CHECK.get(path, LIVE)


@pytest.mark.parametrize("path", null_paths(STREAM_INFO), ids=path_id)
def test_a_null_in_stream_info_gives_the_documented_stream_in_an_online_check(live_twitch, caplog, path):
    seen = check(live_twitch, caplog, with_null(STREAM_INFO, path), AVAILABLE, bulk=False)

    assert seen == STREAM_INFO_IN_ONLINE_CHECK.get(path, LIVE_NAMED)


@pytest.mark.parametrize("path", null_paths(AVAILABLE), ids=path_id)
def test_a_null_in_available_drops_gives_the_documented_drops_status_in_the_bulk_check(live_twitch, caplog, path):
    seen = check(live_twitch, caplog, STREAM_INFO, with_null(AVAILABLE, path), bulk=True)

    assert seen == AVAILABLE_IN_BULK_CHECK.get(path, LIVE)


@pytest.mark.parametrize("path", null_paths(AVAILABLE), ids=path_id)
def test_a_null_in_available_drops_gives_the_documented_drops_status_in_an_online_check(live_twitch, caplog, path):
    seen = check(live_twitch, caplog, STREAM_INFO, with_null(AVAILABLE, path), bulk=False)

    assert seen == AVAILABLE_IN_ONLINE_CHECK.get(path, LIVE_NAMED)


class Listed(NamedTuple):
    """A channel that the directory lists: its ID, name, broadcast ID, game, viewers and title."""

    id: int
    name: str
    broadcast: int
    game: str | None
    viewers: int | None
    title: str | None


def node(channel_id: int, viewers: int) -> JsonType:
    return {
        "id": str(100 + channel_id),
        "title": "Title",
        "viewersCount": viewers,
        "broadcaster": {"id": str(channel_id), "login": f"c{channel_id}", "displayName": f"C{channel_id}"},
        "game": {"id": "1", "name": "Game", "displayName": "Game"},
    }


DIRECTORY = {"data": {"game": {"id": "1", "slug": "game", "displayName": "Game", "streams": {"edges": [
    {"cursor": "1", "node": node(1, 10)},
    {"cursor": "2", "node": node(2, 5)},
]}}}}
EDGES = ("data", "game", "streams", "edges")
LISTED = (Listed(1, "C1", 101, "Game", 10, "Title"), Listed(2, "C2", 102, "Game", 5, "Title"))


def edge_outcomes(index: int) -> dict[NullPath, tuple[tuple[Listed, ...], bool]]:
    """Return the channels listed and whether a warning is logged, for a null field of the edge at index."""
    edge, others = (*EDGES, index), LISTED[:index] + LISTED[index + 1:]
    node = (*edge, "node")

    def changed(**fields) -> tuple[Listed, ...]:
        return LISTED[:index] + (LISTED[index]._replace(**fields),) + LISTED[index + 1:]

    return {
        edge: (others, False),
        node: (others, False),
        (*node, "id"): (others, True),
        (*node, "broadcaster"): (others, False),
        (*node, "broadcaster", "id"): (others, True),
        (*node, "broadcaster", "login"): (others, True),
        (*node, "broadcaster", "displayName"): (changed(name=f"c{index + 1}"), False),
        (*node, "game"): (changed(game=None), False),
        (*node, "game", "id"): (changed(game=None), True),
        (*node, "viewersCount"): (changed(viewers=None), False),
        (*node, "title"): (changed(title=None), False),
    }


DIRECTORY_OUTCOMES = {
    **{EDGES[:end]: ((), False) for end in range(1, len(EDGES) + 1)},
    **edge_outcomes(0),
    **edge_outcomes(1),
}


@pytest.mark.parametrize("path", null_paths(DIRECTORY), ids=path_id)
def test_a_null_in_the_game_directory_gives_the_documented_channels(live_twitch, caplog, path):
    fake = FakeTwitch(gql=gql_answers(GameDirectory=with_null(DIRECTORY, path)))

    channels = asyncio.run(live_twitch(fake).get_live_streams(Game(GAME)))

    listed = tuple(
        Listed(ch.id, ch.name, ch._stream.broadcast_id, ch.game and ch.game.name, ch.viewers, ch._stream.title)
        for ch in channels
    )
    assert (listed, warned(caplog)) == DIRECTORY_OUTCOMES.get(path, (LISTED, False))
    assert fake.gql_sent == ["GameDirectory"]


@pytest.mark.parametrize("response, outcomes", [
    (STREAM_INFO, STREAM_INFO_IN_BULK_CHECK),
    (STREAM_INFO, STREAM_INFO_IN_ONLINE_CHECK),
    (AVAILABLE, AVAILABLE_IN_BULK_CHECK),
    (AVAILABLE, AVAILABLE_IN_ONLINE_CHECK),
    (DIRECTORY, DIRECTORY_OUTCOMES),
])
def test_each_outcome_table_names_only_paths_of_its_response(response, outcomes):
    assert set(outcomes) <= set(null_paths(response))
