import logging

import pytest

from streamdata import (
    channel_stream,
    playback_token,
    channel_streams,
    channel_campaigns,
    directory_streams,
    available_campaigns,
)

GAME = {"id": "1", "name": "G"}


def user(channel_id="10", **fields):
    return {
        "id": channel_id,
        "displayName": f"C{channel_id}",
        "stream": {"id": "100", "viewersCount": 5},
        "broadcastSettings": {"title": "title", "game": GAME},
        **fields,
    }


def info_response(data):
    return {"data": {"user": data}}


def warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]


def test_channel_streams_maps_each_channel_id_to_its_user():
    responses = [info_response(user("10")), info_response(user("11", stream=None))]
    assert channel_streams(responses) == {10: user("10"), 11: user("11", stream=None)}


def test_channel_streams_leaves_out_a_null_user_and_a_user_with_a_null_id(caplog):
    responses = [info_response(None), {"data": None}, info_response(user(None)), info_response(user("10"))]
    assert channel_streams(responses) == {10: user("10")}
    assert warnings(caplog) == ["Skipped a channel with a null ID in a GetStreamInfo response"]


@pytest.mark.parametrize("response", [info_response(None), {"data": None}, {}])
def test_channel_stream_returns_none_for_a_null_user(response):
    assert channel_stream(response, 10) is None


@pytest.mark.parametrize("data", [user(), user(stream=None), user(stream=None, broadcastSettings=None)])
def test_channel_stream_keeps_a_readable_user_and_an_offline_one_without_a_warning(data, caplog):
    assert channel_stream(info_response(data), 10) == data
    assert warnings(caplog) == []


def test_channel_stream_keeps_a_stream_with_no_game_without_a_warning(caplog):
    data = user(broadcastSettings={"title": "title", "game": None})
    assert channel_stream(info_response(data), 10) == data
    assert warnings(caplog) == []


def test_channel_stream_reads_a_stream_with_a_null_id_as_no_stream(caplog):
    result = channel_stream(info_response(user(stream={"id": None, "viewersCount": 5})), 10)
    assert result == user(stream=None)
    assert warnings(caplog) == ["Read channel 10 as offline, because its stream has a null ID"]


@pytest.mark.parametrize("game", [
    {"id": None, "name": "G"},
    {"id": "1", "name": None},
    {"id": "1", "displayName": None, "name": None},
    {"id": "1"},
])
def test_channel_stream_reads_a_game_with_a_null_id_or_name_as_no_game(game, caplog):
    result = channel_stream(info_response(user(broadcastSettings={"title": "title", "game": game})), 10)
    assert result == user(broadcastSettings={"title": "title", "game": None})
    assert warnings(caplog) == ["Read the stream of channel 10 without a game, because its game has a null ID or name"]


def test_channel_stream_keeps_a_game_named_only_by_its_display_name():
    game = {"id": "1", "displayName": "G", "name": None}
    data = user(broadcastSettings={"title": "title", "game": game})
    assert channel_stream(info_response(data), 10) == data


def test_channel_stream_reads_null_broadcast_settings_as_no_game_and_no_title(caplog):
    result = channel_stream(info_response(user(broadcastSettings=None)), 10)
    assert result == user(broadcastSettings={"title": None, "game": None})
    assert warnings(caplog) == [
        "Read the stream of channel 10 without a game, because its broadcast settings are null"
    ]


def directory_node(**fields):
    return {
        "id": "100",
        "broadcaster": {"id": "10", "login": "c10", "displayName": "C10"},
        "game": GAME,
        "viewersCount": 5,
        "title": "title",
        **fields,
    }


def directory_response(*nodes):
    return {"data": {"game": {"streams": {"edges": [{"node": node} for node in nodes]}}}}


@pytest.mark.parametrize("node", [
    directory_node(id=None),
    directory_node(broadcaster={"id": None, "login": "c11", "displayName": "C11"}),
    directory_node(broadcaster={"id": "11", "login": None, "displayName": "C11"}),
])
def test_directory_streams_leaves_out_a_stream_with_a_null_id_broadcaster_id_or_login(node, caplog):
    assert directory_streams(directory_response(node, directory_node())) == [directory_node()]
    assert warnings(caplog) == ["Skipped a GameDirectory stream with a null ID, broadcaster ID or login"]


@pytest.mark.parametrize("game", [{"id": None, "name": "G"}, {"id": "1", "name": None}])
def test_directory_streams_reads_a_game_with_a_null_id_or_name_as_no_game(game, caplog):
    assert directory_streams(directory_response(directory_node(game=game))) == [directory_node(game=None)]
    assert warnings(caplog) == ["Read the stream of channel 10 without a game, because its game has a null ID or name"]


def game_response(game):
    return {"data": {"game": game}}


def test_directory_streams_returns_the_streams_with_a_broadcaster():
    live = {"id": "1", "broadcaster": {"id": "9", "login": "c9"}, "game": None}
    edges = [{"node": live}, {"node": {"id": "2", "broadcaster": None}}, {"node": None}]
    assert directory_streams(game_response({"streams": {"edges": edges}})) == [live]


@pytest.mark.parametrize("response", [
    game_response(None),
    game_response({"streams": None}),
    game_response({"streams": {"edges": None}}),
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


def test_channel_campaigns_leaves_out_a_channel_with_a_null_id(caplog):
    null_id = {"id": None, "viewerDropCampaigns": [{"id": "A"}]}
    responses = [available_response(null_id), available_response({"id": "10", "viewerDropCampaigns": []})]
    assert channel_campaigns(responses) == {10: []}
    assert warnings(caplog) == ["Skipped a channel with a null ID in an AvailableDrops response"]


def test_channel_campaigns_leaves_out_a_null_campaign_and_one_with_a_null_id(caplog):
    channel = {"id": "10", "viewerDropCampaigns": [None, {"id": None}, {"id": "A"}]}
    assert channel_campaigns([available_response(channel)]) == {10: [{"id": "A"}]}
    assert warnings(caplog) == ["Skipped 2 available campaigns of channel 10, which are null or have a null ID"]


def test_available_campaigns_reads_the_campaigns_without_the_channel_id(caplog):
    channel = {"id": None, "viewerDropCampaigns": [{"id": "A"}, None]}
    assert available_campaigns(available_response(channel), 10) == [{"id": "A"}]
    assert warnings(caplog) == ["Skipped 1 available campaigns of channel 10, which are null or have a null ID"]


@pytest.mark.parametrize("response", [
    available_response(None),
    available_response({"id": "10", "viewerDropCampaigns": None}),
    {"data": None},
])
def test_available_campaigns_returns_no_campaigns_for_a_null_channel_or_list(response, caplog):
    assert available_campaigns(response, 10) == []
    assert warnings(caplog) == []


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
