from __future__ import annotations

import asyncio
import logging

import pytest

from channel import Channel
from constants import JsonType
from fakes import FakeTwitch, campaign_data, drop_data, gql_answers, stream_user
from inventory import DropsCampaign
from nullpaths import NullPath, null_paths, path_id, with_null

ONLINE = {"data": {"user": stream_user(1, online=True)}}
# the app tracks the first campaign, so the channel counts as drops enabled while that one is listed
AVAILABLE = {"data": {"channel": {"id": "1", "viewerDropCampaigns": [
    {"id": "c1", "name": "Campaign"},
    {"id": "c9", "name": "Other campaign"},
]}}}
TRACKED = ("data", "channel", "viewerDropCampaigns", 0)
OTHER = ("data", "channel", "viewerDropCampaigns", 1)
# The outcome of each null path that differs from the full response's (True, False): whether the channel counts
# as drops enabled, and whether a warning is logged.
AVAILABLE_IN_BULK_CHECK: dict[NullPath, tuple[bool, bool]] = {
    ("data",): (False, False),
    ("data", "channel"): (False, False),
    ("data", "channel", "id"): (False, True),
    ("data", "channel", "viewerDropCampaigns"): (False, False),
    TRACKED: (False, True),
    (*TRACKED, "id"): (False, True),
    OTHER: (True, True),
    (*OTHER, "id"): (True, True),
}
# an online check does not read the channel's ID
AVAILABLE_IN_ONLINE_CHECK = {**AVAILABLE_IN_BULK_CHECK, ("data", "channel", "id"): (True, False)}


def warned(caplog: pytest.LogCaptureFixture) -> bool:
    return any(record.levelno == logging.WARNING for record in caplog.records)


def drops_enabled(live_twitch, available: JsonType, *, bulk: bool) -> tuple[bool, list[str]]:
    """Return whether the live channel 1 counts as drops enabled after a bulk check or an online check, and the GQL sent."""
    fake = FakeTwitch(gql=gql_answers(GetStreamInfo=ONLINE, AvailableDrops=available))
    fake.settings.available_drops_check = True
    twitch = live_twitch(fake)
    campaign = DropsCampaign(twitch, campaign_data([drop_data("d1")]), {})
    twitch._campaigns[campaign.id] = campaign
    channel = Channel(twitch, id=1, login="c1", acl_based=bulk)
    asyncio.run(twitch.bulk_check_online([channel]) if bulk else channel.update_stream())
    return channel.drops_enabled, fake.gql_sent


@pytest.mark.parametrize("path", null_paths(AVAILABLE), ids=path_id)
def test_a_null_in_available_drops_gives_the_documented_drops_status_in_the_bulk_check(live_twitch, caplog, path):
    enabled, sent = drops_enabled(live_twitch, with_null(AVAILABLE, path), bulk=True)

    assert (enabled, warned(caplog)) == AVAILABLE_IN_BULK_CHECK.get(path, (True, False))
    assert sent == ["GetStreamInfo", "AvailableDrops"]


@pytest.mark.parametrize("path", null_paths(AVAILABLE), ids=path_id)
def test_a_null_in_available_drops_gives_the_documented_drops_status_in_an_online_check(live_twitch, caplog, path):
    enabled, sent = drops_enabled(live_twitch, with_null(AVAILABLE, path), bulk=False)

    assert (enabled, warned(caplog)) == AVAILABLE_IN_ONLINE_CHECK.get(path, (True, False))
    assert sent == ["GetStreamInfo", "AvailableDrops"]


@pytest.mark.parametrize("response, outcomes", [
    (AVAILABLE, AVAILABLE_IN_BULK_CHECK),
    (AVAILABLE, AVAILABLE_IN_ONLINE_CHECK),
])
def test_each_outcome_table_names_only_paths_of_its_response(response, outcomes):
    assert set(outcomes) <= set(null_paths(response))
