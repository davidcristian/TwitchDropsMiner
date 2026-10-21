import copy
import json
from collections.abc import Mapping
from typing import NamedTuple

import pytest
from aiohttp import ClientHttpProxyError, RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from constants import GQLPersistedQuery
from redact import HIDDEN, redact

DOCUMENTED_SECRET_KEYS = (
    "access_token",
    "auth_token",
    "authorization",
    "cookie",
    "device_code",
    "password",
    "proxy-authorization",
    "refresh_token",
    "set-cookie",
    "token",
)
PROXY_BASIC_AUTH = "Basic dXNlcjpzM2NyZXQ="  # user:s3cret in base64


def proxy_connect_info():
    headers = CIMultiDictProxy(CIMultiDict([
        ("Host", "gql.twitch.tv"),
        ("Proxy-Authorization", PROXY_BASIC_AUTH),
    ]))
    return RequestInfo(
        URL("https://gql.twitch.tv/gql"),
        "CONNECT",
        headers,
        URL("http://user:s3cret@proxy.example:8080"),
    )


@pytest.mark.parametrize("key", DOCUMENTED_SECRET_KEYS)
def test_redact_hides_the_value_of_each_secret_key(key):
    assert redact({key: "s3cret", "client_id": "abc"}) == {key: HIDDEN, "client_id": "abc"}


@pytest.mark.parametrize("key", ["Authorization", "SET-COOKIE", "Access_Token"])
def test_redact_compares_key_names_lowercase(key):
    assert redact({key: "s3cret"}) == {key: HIDDEN}


def test_redact_hides_the_whole_value_of_a_secret_key():
    assert redact({"cookie": {"auth-token": "s3cret"}, "token": ["a", "b"]}) == {
        "cookie": HIDDEN,
        "token": HIDDEN,
    }


def test_redact_hides_secrets_in_nested_values():
    message = {"type": "LISTEN", "data": {"topics": ["user-drop-events.123"], "auth_token": "s3cret"}}
    assert redact(message) == {
        "type": "LISTEN",
        "data": {"topics": ["user-drop-events.123"], "auth_token": HIDDEN},
    }


def test_redact_keeps_lists_as_lists_and_tuples_as_tuples():
    result = redact([{"token": "a"}, ({"password": "b"}, "plain")])
    assert result == [{"token": HIDDEN}, ({"password": HIDDEN}, "plain")]
    assert type(result) is list
    assert type(result[1]) is tuple


def test_redact_hides_every_secret_of_the_request_arguments():
    kwargs = {
        "headers": {"Authorization": "OAuth s3cret", "Client-Id": "abc"},
        "data": {"client_id": "abc", "device_code": "s3cret"},
        "proxy": URL("http://user:s3cret@proxy.example:8080"),
    }
    result = redact(kwargs)
    assert result["headers"] == {"Authorization": HIDDEN, "Client-Id": "abc"}
    assert result["data"] == {"client_id": "abc", "device_code": HIDDEN}
    assert "s3cret" not in repr(result)


def test_redact_hides_the_password_of_a_url():
    result = redact(URL("http://user:s3cret@proxy.example:8080/path"))
    assert result.password == HIDDEN
    assert str(result) == "http://user:%3Chidden%3E@proxy.example:8080/path"


def test_redact_returns_a_url_without_a_password_as_it_is():
    url = URL("http://user@proxy.example:8080")
    assert redact(url) is url


def test_redact_hides_the_playback_token_in_an_usher_url():
    playback_token = json.dumps({"channel": "abc", "user_id": 123, "user_ip": "203.0.113.5"})
    url = URL(f"https://usher.ttvnw.net/api/channel/hls/abc.m3u8?sig=0123abcd&token={playback_token}")
    result = redact(url)
    assert str(result) == "https://usher.ttvnw.net/api/channel/hls/abc.m3u8?sig=0123abcd&token=%3Chidden%3E"
    assert "203.0.113.5" not in repr(result)


@pytest.mark.parametrize("key", DOCUMENTED_SECRET_KEYS)
def test_redact_hides_the_query_value_of_each_secret_key(key):
    result = redact(URL(f"https://a.example/path?{key}=s3cret&client_id=abc"))
    assert list(result.query.items()) == [(key, HIDDEN), ("client_id", "abc")]


@pytest.mark.parametrize("query", ["Token=s3cret", "%74oken=s3cret", "token=a&token=b", "token"])
def test_redact_hides_a_secret_query_value_under_the_name_that_yarl_reads(query):
    result = redact(URL(f"https://a.example/path?{query}", encoded=True))
    assert set(result.query.values()) == {HIDDEN}


@pytest.mark.parametrize("text", [
    "https://user@a.example:8080/p%20q?a=1+2&token=s3cret&b=%7E&c&d=#frag",
    "/relative?token=s3cret&a=1",
])
def test_redact_changes_only_the_secret_query_value_of_a_url(text):
    url = URL(text)
    assert str(redact(url)) == str(url).replace("token=s3cret", "token=%3Chidden%3E")


def test_redact_hides_the_password_and_a_secret_query_value_of_one_url():
    result = redact(URL("http://user:s3cret@proxy.example:8080/?token=s3cret"))
    assert str(result) == "http://user:%3Chidden%3E@proxy.example:8080/?token=%3Chidden%3E"


def test_redact_returns_a_url_without_a_secret_query_parameter_as_it_is():
    url = URL("https://usher.ttvnw.net/api/channel/hls/abc.m3u8?sig=0123abcd&client_id=abc#token=x")
    assert redact(url) is url


def test_redact_hides_the_proxy_password_in_a_request_info():
    result = redact(proxy_connect_info())
    assert type(result) is RequestInfo
    assert result.url == URL("https://gql.twitch.tv/gql")
    assert result.method == "CONNECT"
    assert result.headers == {"Host": "gql.twitch.tv", "Proxy-Authorization": HIDDEN}
    assert str(result.real_url) == "http://user:%3Chidden%3E@proxy.example:8080"


def test_a_proxy_error_with_a_redacted_request_info_hides_the_proxy_password_in_its_text():
    error = ClientHttpProxyError(proxy_connect_info(), (), status=407, message="Proxy Authentication Required")
    error.request_info = redact(error.request_info)
    assert "s3cret" not in str(error)
    assert "user:%3Chidden%3E@proxy.example:8080" in str(error)


def test_redact_reads_a_tuple_with_the_same_fields_and_another_name_as_a_tuple():
    class Other(NamedTuple):
        url: URL
        method: str
        headers: Mapping[str, str]
        real_url: URL

    value = Other(URL("https://a.example"), "GET", {"Authorization": "OAuth s3cret"}, URL("https://a.example"))
    result = redact(value)
    assert type(result) is tuple
    assert result[2] == {"Authorization": HIDDEN}


def test_redact_does_not_change_its_argument():
    value = {
        "headers": {"Authorization": "OAuth s3cret"},
        "json": [{"variables": {"token": "s3cret"}}],
        "proxy": URL("http://user:s3cret@proxy.example:8080"),
    }
    before = copy.deepcopy(value)
    redact(value)
    assert value == before


def test_redact_turns_response_headers_into_a_dict_with_one_entry_per_key():
    headers = CIMultiDictProxy(CIMultiDict([
        ("Content-Type", "application/json"),
        ("Set-Cookie", "unique_id=s3cret"),
        ("Set-Cookie", "server_session_id=s3cret"),
    ]))
    result = redact(headers)
    assert type(result) is dict
    assert result == {"Content-Type": "application/json", "Set-Cookie": HIDDEN}


def test_redact_gives_a_gql_operation_as_a_plain_dict_with_the_same_text():
    operation = GQLPersistedQuery("Inventory", "0123abcd", variables={"fetchRewardCampaigns": False})
    result = redact(operation)
    assert type(result) is dict
    assert repr(result) == repr(operation)


@pytest.mark.parametrize("value", ["OAuth s3cret", 42, 1.5, None, b"s3cret", {"s3cret"}])
def test_redact_returns_other_values_as_they_are(value):
    assert redact(value) is value


@pytest.mark.parametrize("value", [{}, [], ()])
def test_redact_returns_an_empty_container_of_the_same_type(value):
    result = redact(value)
    assert result == value
    assert type(result) is type(value)
