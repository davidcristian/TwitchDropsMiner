import copy

import pytest

from exceptions import MinerException
from gqldata import (
    CAMPAIGN_FIELDS,
    get_field,
    merge_data,
    campaign_details,
    channel_campaigns,
    clear_error_field,
    playback_token,
    directory_streams,
    complete_campaigns,
)

START, END = "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z"
SERVER_ERROR_DATA = {"user": {"dropCampaign": {"id": "A", "timeBasedDrops": [{"id": "d", "benefitEdges": []}]}}}


def summary(campaign_id):
    return {
        "id": campaign_id,
        "name": campaign_id,
        "startAt": START,
        "endAt": END,
        "game": {"id": "1", "name": "G", "boxArtURL": "https://example.invalid/1-285x380.jpg"},
        "self": {"isAccountConnected": True},
    }


def details(campaign_id):
    drop = {"id": f"{campaign_id}-drop", "startAt": START, "endAt": END, "requiredMinutesWatched": 60}
    return {**summary(campaign_id), "allow": {"channels": None, "isEnabled": True}, "timeBasedDrops": [drop]}


def details_response(campaign):
    return {"data": {"user": {"id": "7", "dropCampaign": campaign}}}


def test_get_field_follows_dict_keys_and_list_indexes():
    assert get_field(SERVER_ERROR_DATA, "user", "dropCampaign", "timeBasedDrops", 0, "id") == "d"


def test_get_field_with_no_path_returns_the_data():
    assert get_field(SERVER_ERROR_DATA) is SERVER_ERROR_DATA


@pytest.mark.parametrize("path", [
    ("user", "missing", "id"),
    ("user", "dropCampaign", "timeBasedDrops", 1, "id"),
    ("user", "dropCampaign", "timeBasedDrops", "0"),
    ("user", "dropCampaign", "id", "x"),
])
def test_get_field_returns_none_for_a_missing_field(path):
    assert get_field(SERVER_ERROR_DATA, *path) is None


@pytest.mark.parametrize("data", [None, {"user": None}, {"user": {"dropCampaign": None}}])
def test_get_field_returns_none_below_a_null_field(data):
    assert get_field(data, "user", "dropCampaign", "id") is None


def test_clear_error_field_sets_the_named_field_to_none():
    data = copy.deepcopy(SERVER_ERROR_DATA)
    assert clear_error_field(data, ["user", "dropCampaign"]) is True
    assert data == {"user": {"dropCampaign": None}}


def test_clear_error_field_follows_a_list_index():
    data = copy.deepcopy(SERVER_ERROR_DATA)
    assert clear_error_field(data, ["user", "dropCampaign", "timeBasedDrops", 0, "benefitEdges"]) is True
    assert data["user"]["dropCampaign"]["timeBasedDrops"] == [{"id": "d", "benefitEdges": None}]


@pytest.mark.parametrize("data, path", [
    (copy.deepcopy(SERVER_ERROR_DATA), []),
    ({"user": {"dropCampaign": None}}, ["user", "dropCampaign", "game"]),
    ({"user": None}, ["user", "dropCampaign", "game"]),
    (copy.deepcopy(SERVER_ERROR_DATA), ["user", "dropCampaign", "timeBasedDrops", 3]),
    (None, ["user"]),
])
def test_clear_error_field_returns_false_and_changes_nothing_without_a_field(data, path):
    before = copy.deepcopy(data)
    assert clear_error_field(data, path) is False
    assert data == before


def test_merge_data_keeps_the_primary_value_and_adds_the_rest():
    primary = {"id": "A", "status": "ACTIVE", "self": {"isAccountConnected": True}}
    secondary = {"id": "A", "status": "EXPIRED", "self": {"dropInstanceID": "x"}, "allow": {"channels": []}}
    assert merge_data(primary, secondary) == {
        "id": "A",
        "status": "ACTIVE",
        "self": {"isAccountConnected": True, "dropInstanceID": "x"},
        "allow": {"channels": []},
    }


def test_merge_data_takes_the_other_value_where_one_side_is_null():
    primary = {"self": None, "game": {"id": "1"}, "name": None}
    secondary = {"self": {"isAccountConnected": True}, "game": None}
    assert merge_data(primary, secondary) == {
        "self": {"isAccountConnected": True},
        "game": {"id": "1"},
        "name": None,
    }


def test_merge_data_raises_for_two_values_of_different_types():
    with pytest.raises(MinerException, match="Inconsistent merge data"):
        merge_data({"allow": {"channels": []}}, {"allow": []})


def test_merge_data_of_empty_dicts_is_empty():
    assert merge_data({}, {}) == {}


def test_campaign_details_maps_each_campaign_by_id():
    responses = [details_response(details("A")), details_response(details("B"))]
    assert campaign_details(responses) == {"A": details("A"), "B": details("B")}


@pytest.mark.parametrize("response", [
    details_response(None),
    {"data": {"user": None}},
    {"data": None},
])
def test_campaign_details_leaves_out_a_null_campaign(response):
    assert campaign_details([details_response(details("A")), response]) == {"A": details("A")}


def test_complete_campaigns_keeps_a_campaign_with_every_field():
    assert complete_campaigns({"A": details("A")}) == {"A": details("A")}


@pytest.mark.parametrize("field", CAMPAIGN_FIELDS)
def test_complete_campaigns_leaves_out_a_campaign_with_a_null_or_missing_field(field):
    null = {**details("N"), field: None}
    missing = {key: value for key, value in details("M").items() if key != field}
    assert complete_campaigns({"A": details("A"), "N": null, "M": missing}) == {"A": details("A")}


def test_complete_campaigns_leaves_out_a_campaign_whose_self_is_null():
    assert complete_campaigns({"A": details("A"), "N": {**details("N"), "self": None}}) == {"A": details("A")}


def test_null_details_keep_a_campaign_in_progress_and_leave_out_one_with_only_a_summary():
    inventory = {"P": details("P")}
    chunk = merge_data(
        {"P": summary("P"), "Q": summary("Q"), "R": summary("R")},
        campaign_details([details_response(None), details_response(None), details_response(details("R"))]),
    )
    assert sorted(complete_campaigns(merge_data(inventory, chunk))) == ["P", "R"]


def directory_response(game):
    return {"data": {"game": game}}


def test_directory_streams_returns_the_streams_with_a_broadcaster():
    live = {"id": "1", "broadcaster": {"id": "9", "login": "c9"}, "game": None}
    edges = [{"node": live}, {"node": {"id": "2", "broadcaster": None}}, {"node": None}]
    assert directory_streams(directory_response({"streams": {"edges": edges}})) == [live]


@pytest.mark.parametrize("response", [
    directory_response(None),
    directory_response({"streams": None}),
    directory_response({"streams": {"edges": None}}),
    {"data": {}},
    {"data": None},
])
def test_directory_streams_returns_no_streams_for_a_null_game(response):
    assert directory_streams(response) == []


def available_response(channel):
    return {"data": {"channel": channel}}


def test_channel_campaigns_maps_each_channel_id_to_its_campaigns():
    responses = [
        available_response({"id": "10", "viewerDropCampaigns": [{"id": "A"}]}),
        available_response({"id": "11", "viewerDropCampaigns": None}),
    ]
    assert channel_campaigns(responses) == {10: [{"id": "A"}], 11: []}


def test_channel_campaigns_leaves_out_a_null_channel():
    responses = [available_response(None), available_response({"id": "10", "viewerDropCampaigns": []})]
    assert channel_campaigns(responses) == {10: []}


def token_response(token):
    return {"data": {"streamPlaybackAccessToken": token}}


def test_playback_token_returns_the_value_and_the_signature():
    assert playback_token(token_response({"value": "v", "signature": "s"})) == ("v", "s")


@pytest.mark.parametrize("response", [
    token_response({"value": None, "signature": "s"}),
    token_response({"value": "v", "signature": None}),
    token_response(None),
    {"data": None},
])
def test_playback_token_returns_none_for_a_null_token_value_or_signature(response):
    assert playback_token(response) is None
