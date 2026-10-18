import copy

import pytest
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
    "refresh_token",
    "set-cookie",
    "token",
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
