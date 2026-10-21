from __future__ import annotations

import asyncio
import math

from fakes import CLAIMED, FakeTwitch, campaign_data, drop_data
from inventory import DropsCampaign, TimedDrop


def totals(campaign: DropsCampaign) -> tuple[int, int, float, float]:
    return (campaign.required_minutes, campaign.remaining_minutes, campaign.progress, campaign.availability)


def claimable_drop(twitch: FakeTwitch) -> TimedDrop:
    campaign = DropsCampaign(twitch, campaign_data([drop_data("d1", watched=120, claim_id="7#c1#d1")]), {})
    return campaign.timed_drops["d1"]


def test_a_campaign_without_drops_has_the_totals_of_one_whose_drops_need_no_minutes():
    empty = DropsCampaign(FakeTwitch(), campaign_data([]), {})
    no_minutes = DropsCampaign(FakeTwitch(), campaign_data([drop_data("d1", minutes=0)]), {})

    assert totals(empty) == totals(no_minutes) == (0, 0, 0.0, math.inf)


def test_a_second_claim_of_a_drop_sends_no_request_and_reports_nothing():
    twitch = FakeTwitch(gql=lambda op: CLAIMED)
    drop = claimable_drop(twitch)

    assert asyncio.run(drop.claim()) is True
    assert asyncio.run(drop.claim()) is True
    assert twitch.gql_sent == ["ClaimDrop"]
    assert len(twitch.printed) == 1
    assert len(twitch.gui.notified) == 1


def test_a_claim_whose_response_has_null_data_fails(caplog):
    response = {"data": None, "errors": [{"message": "server error", "path": ["claimDropRewards"]}]}
    twitch = FakeTwitch(gql=lambda op: response)
    drop = claimable_drop(twitch)

    assert asyncio.run(drop.claim()) is False
    assert drop.is_claimed is False
    assert (twitch.printed, twitch.gui.notified) == ([], [])
    assert "Drop claim has potentially failed" in caplog.text
