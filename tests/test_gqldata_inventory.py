import copy
import logging

import pytest

from exceptions import GQLException
from gqldata import TIME_FIELDS, current_drop, user_inventory, claim_succeeded, campaign_summaries, complete_campaigns

START, END = "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z"
GAME = {"id": "1", "name": "G", "boxArtURL": "https://example.invalid/1-285x380.jpg"}


def campaign(campaign_id, status="ACTIVE", **fields):
    return {
        "id": campaign_id,
        "status": status,
        "startAt": START,
        "endAt": END,
        "game": GAME,
        "self": {"isAccountConnected": True},
        "allow": {"channels": None, "isEnabled": True},
        "timeBasedDrops": [],
        **fields,
    }


def drop(drop_id, *preconditions):
    return {
        "id": drop_id,
        "startAt": START,
        "endAt": END,
        "benefitEdges": [{"benefit": {"id": f"{drop_id}-benefit"}}],
        "preconditionDrops": [{"id": pre} for pre in preconditions] or None,
        "requiredMinutesWatched": 60,
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


def without(data, field):
    return {key: value for key, value in data.items() if key != field}


@pytest.mark.parametrize("field", TIME_FIELDS)
def test_complete_campaigns_leaves_out_a_drop_with_a_null_or_missing_time_and_every_drop_after_it(field, caplog):
    drops = [drop("d1"), {**drop("d2"), field: None}, without(drop("d3"), field), drop("d4", "d2"), drop("d5", "d1")]
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaign_with(*drops))
    assert drops_of(result) == [drop("d1"), drop("d5", "d1")]
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped drop d2 of campaign A, which has a null start or end time",
        "Skipped drop d3 of campaign A, which has a null start or end time",
        "Skipped drop d4 of campaign A, whose precondition was skipped",
    ]


def test_complete_campaigns_leaves_out_a_drop_with_null_or_missing_minutes_and_every_drop_after_it(caplog):
    drops = [drop("d1"), {**drop("d2"), "requiredMinutesWatched": None}, without(drop("d3"), "requiredMinutesWatched")]
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaign_with(*drops, drop("d4", "d2")))
    assert drops_of(result) == [drop("d1")]
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped drop d2 of campaign A, which has null required minutes",
        "Skipped drop d3 of campaign A, which has null required minutes",
        "Skipped drop d4 of campaign A, whose precondition was skipped",
    ]


@pytest.mark.parametrize("game", [
    {**GAME, "id": None},
    without(GAME, "id"),
    {**GAME, "boxArtURL": None},
    {**GAME, "name": None},
    {**GAME, "displayName": None, "name": None},
])
def test_complete_campaigns_leaves_out_a_campaign_whose_game_has_a_null_id_name_or_box_art(game, caplog):
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns({"A": campaign("A"), "N": campaign("N", game=game)})
    assert result == {"A": campaign("A")}
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped campaign N, whose game has a null ID, name or box art",
    ]


def test_complete_campaigns_keeps_a_game_whose_display_name_stands_for_a_null_name():
    game = {**GAME, "displayName": "G", "name": None}
    assert complete_campaigns({"A": campaign("A", game=game)}) == {"A": campaign("A", game=game)}


def test_complete_campaigns_reads_a_null_game_slug_as_missing():
    assert complete_campaigns({"A": campaign("A", game={**GAME, "slug": None})}) == {"A": campaign("A")}


@pytest.mark.parametrize("field", TIME_FIELDS)
def test_complete_campaigns_leaves_out_a_campaign_with_a_null_or_missing_time_and_logs_it(field, caplog):
    campaigns = {"A": campaign("A"), "N": campaign("N", **{field: None}), "M": without(campaign("M"), field)}
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns(campaigns)
    assert result == {"A": campaign("A")}
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped campaign N, which has a null start or end time",
        "Skipped campaign M, which has a null start or end time",
    ]


def acl(*channels, enabled=True):
    return {"channels": list(channels), "isEnabled": enabled}


CHANNEL = {"id": "1", "name": "c1", "displayName": "C1"}
NULL_CHANNELS = [None, {**CHANNEL, "id": None}, {**CHANNEL, "name": None}]


def test_complete_campaigns_leaves_out_an_acl_channel_that_is_null_or_has_a_null_id_or_name(caplog):
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns({"A": campaign("A", allow=acl(CHANNEL, *NULL_CHANNELS))})
    assert result == {"A": campaign("A", allow=acl(CHANNEL))}
    assert [record.getMessage() for record in caplog.records] == [
        "Skipped 3 ACL channels of campaign A, which are null or have a null ID or name",
    ]


def test_complete_campaigns_leaves_out_a_campaign_whose_enabled_acl_has_only_null_channels(caplog):
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        result = complete_campaigns({"A": campaign("A"), "N": campaign("N", allow=acl(*NULL_CHANNELS))})
    assert result == {"A": campaign("A")}
    assert "Skipped campaign N, whose ACL has no readable channel" in caplog.text


def test_complete_campaigns_keeps_a_campaign_whose_disabled_acl_has_only_null_channels():
    result = complete_campaigns({"A": campaign("A", allow=acl(*NULL_CHANNELS, enabled=False))})
    assert result == {"A": campaign("A", allow=acl(enabled=False))}


def test_complete_campaigns_does_not_change_its_argument():
    campaigns = campaign_with(None, {**drop("d1"), "self": None, "benefitEdges": [None]}, drop("d2", "d0"))
    campaigns["B"] = campaign("B", allow=acl(CHANNEL, None))
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
    inventory_response([campaign("P")], [CLAIMED[0], {**CLAIMED[0], "lastAwardedAt": None}]),
])
def test_user_inventory_raises_for_a_null_inventory_claimed_drop_or_award_time(response):
    with pytest.raises(GQLException, match="null inventory, claimed drop or award time"):
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
