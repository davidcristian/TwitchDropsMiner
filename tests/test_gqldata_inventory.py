import copy
import logging

import pytest

from exceptions import GQLException
from gqldata import current_drop, user_inventory, claim_succeeded, campaign_summaries, complete_campaigns


def campaign(campaign_id, status="ACTIVE", **fields):
    return {
        "id": campaign_id,
        "status": status,
        "game": {"id": "1"},
        "self": {"isAccountConnected": True},
        "allow": {"channels": None, "isEnabled": True},
        "timeBasedDrops": [],
        **fields,
    }


def drop(drop_id, *preconditions):
    return {
        "id": drop_id,
        "benefitEdges": [{"benefit": {"id": f"{drop_id}-benefit"}}],
        "preconditionDrops": [{"id": pre} for pre in preconditions] or None,
        "self": {"dropInstanceID": None, "isClaimed": False},
    }


def campaign_with(*drops):
    return {"A": campaign("A", timeBasedDrops=list(drops))}


def drops_of(campaigns):
    return campaigns["A"]["timeBasedDrops"]


def test_complete_campaigns_keeps_drops_without_a_null_field():
    campaigns = campaign_with(drop("d1"), drop("d2", "d1"))
    assert complete_campaigns(campaigns) == campaigns


def test_complete_campaigns_leaves_out_a_null_drop_and_logs_it(caplog):
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaign_with(None, drop("d2")))
    assert drops_of(result) == [drop("d2")]
    assert [record.getMessage() for record in caplog.records] == ["Skipped a null drop of campaign A"]


@pytest.mark.parametrize("edge", [None, {"benefit": None}])
def test_complete_campaigns_leaves_out_a_null_benefit_and_keeps_its_drop(edge, caplog):
    null_benefit = {**drop("d1"), "benefitEdges": [edge, {"benefit": {"id": "kept"}}]}
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaign_with(null_benefit))
    assert drops_of(result) == [{**drop("d1"), "benefitEdges": [{"benefit": {"id": "kept"}}]}]
    assert "Skipped a null benefit of drop d1 in campaign A" in caplog.text


def test_complete_campaigns_reads_a_null_self_of_a_drop_as_missing():
    result = complete_campaigns(campaign_with({**drop("d1"), "self": None}))
    assert drops_of(result) == [{key: value for key, value in drop("d1").items() if key != "self"}]


def test_complete_campaigns_leaves_out_a_drop_with_a_null_precondition_and_every_drop_after_it(caplog):
    null_precondition = {**drop("d2"), "preconditionDrops": [None]}
    drops = [drop("d1"), null_precondition, drop("d3", "d2"), drop("d4", "d3"), drop("d5", "d1")]
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaign_with(*drops))
    assert drops_of(result) == [drop("d1"), drop("d5", "d1")]
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped drop d2 of campaign A, which has a null precondition",
        "Skipped drop d3 of campaign A, whose precondition was skipped",
        "Skipped drop d4 of campaign A, whose precondition was skipped",
    ]


def test_complete_campaigns_leaves_out_every_drop_after_a_null_one():
    assert drops_of(complete_campaigns(campaign_with(None, drop("d2", "d1"), drop("d3", "d2")))) == []


def test_complete_campaigns_does_not_change_its_argument():
    campaigns = campaign_with(None, {**drop("d1"), "self": None, "benefitEdges": [None]}, drop("d2", "d0"))
    before = copy.deepcopy(campaigns)
    complete_campaigns(campaigns)
    assert campaigns == before


def inventory_response(in_progress, claimed):
    return {"data": {"currentUser": {"inventory": {
        "dropCampaignsInProgress": in_progress,
        "gameEventDrops": claimed,
    }}}}


CLAIMED = [{"id": "benefit", "lastAwardedAt": "2026-10-20T00:00:00Z"}]


def test_user_inventory_returns_the_inventory_without_a_null_campaign_in_progress():
    response = inventory_response([campaign("P"), None], CLAIMED)
    assert user_inventory(response) == {"dropCampaignsInProgress": [campaign("P")], "gameEventDrops": CLAIMED}


def test_user_inventory_reads_a_null_list_of_campaigns_in_progress_as_empty():
    assert user_inventory(inventory_response(None, []))["dropCampaignsInProgress"] == []


@pytest.mark.parametrize("response", [
    {"data": None},
    {"data": {"currentUser": None}},
    {"data": {"currentUser": {"inventory": None}}},
    inventory_response([campaign("P")], None),
    inventory_response([campaign("P")], [CLAIMED[0], None]),
])
def test_user_inventory_raises_for_a_null_inventory_or_claimed_drop(response):
    with pytest.raises(GQLException, match="null inventory or claimed drop"):
        user_inventory(response)


def summaries_response(campaigns):
    return {"data": {"currentUser": {"dropCampaigns": campaigns}}}


def test_campaign_summaries_maps_the_active_and_upcoming_campaigns_by_id():
    active, upcoming, expired = campaign("A"), campaign("U", "UPCOMING"), campaign("E", "EXPIRED")
    response = summaries_response([active, upcoming, expired, None])
    assert campaign_summaries(response) == {"A": active, "U": upcoming}


def test_campaign_summaries_reads_a_null_list_as_no_campaigns():
    assert campaign_summaries(summaries_response(None)) == {}


@pytest.mark.parametrize("response", [{"data": None}, {"data": {"currentUser": None}}])
def test_campaign_summaries_raises_for_a_null_user(response):
    with pytest.raises(GQLException, match="null user"):
        campaign_summaries(response)


def current_drop_response(session):
    return {"data": {"currentUser": {"dropCurrentSession": session}}}


def test_current_drop_returns_the_drop_session():
    session = {"dropID": "d1", "currentMinutesWatched": 3}
    assert current_drop(current_drop_response(session)) == session


@pytest.mark.parametrize("response", [
    current_drop_response(None),
    {"data": {"currentUser": None}},
    {"data": None},
])
def test_current_drop_returns_none_for_a_null_session_or_user(response):
    assert current_drop(response) is None


@pytest.mark.parametrize("status", ["ELIGIBLE_FOR_ALL", "DROP_INSTANCE_ALREADY_CLAIMED"])
def test_claim_succeeded_for_a_claimed_status(status):
    assert claim_succeeded({"data": {"claimDropRewards": {"status": status}}}) is True


@pytest.mark.parametrize("response", [
    {"data": {"claimDropRewards": {"status": "DROP_INSTANCE_NOT_ELIGIBLE"}}},
    {"data": {"claimDropRewards": None}},
    {"data": {"errors": ["failed"], "claimDropRewards": {"status": "ELIGIBLE_FOR_ALL"}}},
    {"data": {}},
    {"data": None},
    {},
])
def test_claim_succeeded_is_false_without_a_claimed_status(response):
    assert claim_succeeded(response) is False
