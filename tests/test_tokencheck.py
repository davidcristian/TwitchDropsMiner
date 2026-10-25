import pytest
from yarl import URL

from twitchapi import ClientInfo, ClientType
from tokencheck import CLIENT_TYPES, TokenCheck, TokenResult, check_token, client_of, entered_token

OTHER = ClientInfo(URL("https://other.example"), "other-id", "Other/1.0")


def test_client_types_are_the_entries_of_client_type():
    assert CLIENT_TYPES == (ClientType.WEB, ClientType.MOBILE_WEB, ClientType.ANDROID_APP, ClientType.SMARTBOX)


@pytest.mark.parametrize("client", CLIENT_TYPES)
def test_client_of_returns_the_client_type_with_the_client_id(client):
    assert client_of(client.CLIENT_ID) is client


@pytest.mark.parametrize("client_id", ["unknown", "", None, 7, ClientType.WEB.CLIENT_ID.upper()])
def test_client_of_returns_none_for_a_client_id_of_no_client_type(client_id):
    assert client_of(client_id) is None


def test_client_of_looks_only_in_the_given_clients():
    assert client_of("other-id", [OTHER]) is OTHER
    assert client_of(ClientType.WEB.CLIENT_ID, [OTHER]) is None


@pytest.mark.parametrize("client", CLIENT_TYPES)
def test_a_token_of_a_client_type_is_accepted_with_its_client_and_user_id(client):
    body = {"client_id": client.CLIENT_ID, "login": "user", "scopes": [], "user_id": "123", "expires_in": 5000}

    assert check_token(200, body) == TokenCheck(TokenResult.ACCEPTED, client, 123)


def test_a_user_id_given_as_a_number_is_accepted():
    assert check_token(200, {"client_id": "other-id", "user_id": 7}, [OTHER]) == TokenCheck(
        TokenResult.ACCEPTED, OTHER, 7
    )


@pytest.mark.parametrize("body", [None, {}, {"message": "invalid access token"}])
def test_a_401_rejects_the_token_whatever_the_body(body):
    assert check_token(401, body) == TokenCheck(TokenResult.REJECTED)


@pytest.mark.parametrize("body", [
    {"client_id": "unknown", "user_id": "123"},
    {"client_id": None, "user_id": "123"},
    {"user_id": "123"},
    {"client_id": "unknown"},
])
def test_a_token_of_no_client_type_is_of_an_unknown_client(body):
    assert check_token(200, body) == TokenCheck(TokenResult.UNKNOWN_CLIENT)


@pytest.mark.parametrize("status", [400, 403, 404, 429])
def test_another_status_fails(status):
    body = {"client_id": ClientType.WEB.CLIENT_ID, "user_id": "123"}

    assert check_token(status, body) == TokenCheck(TokenResult.FAILED)


@pytest.mark.parametrize("body", [None, [], "text", 7])
def test_a_200_body_that_is_not_an_object_fails(body):
    assert check_token(200, body) == TokenCheck(TokenResult.FAILED)


@pytest.mark.parametrize("user_id", [None, "", "abc", "-1", "1.5", True, 1.5, [1]])
def test_a_200_response_without_a_whole_number_user_id_fails(user_id):
    body = {"client_id": ClientType.WEB.CLIENT_ID, "user_id": user_id}

    assert check_token(200, body) == TokenCheck(TokenResult.FAILED)


def test_a_200_response_without_a_user_id_fails():
    assert check_token(200, {"client_id": ClientType.WEB.CLIENT_ID}) == TokenCheck(TokenResult.FAILED)


@pytest.mark.parametrize(("text", "token"), [
    ("abc123", "abc123"),
    ("  abc123\n", "abc123"),
    ("abc\r\n123\t", "abc123"),
    ("abc\x00\x7f\x1b123", "abc123"),
    ("a-b_c.1", "a-b_c.1"),
])
def test_entered_token_removes_whitespace_and_control_characters(text, token):
    assert entered_token(text) == token


@pytest.mark.parametrize("text", ["", "   ", "\n\t", "\x00"])
def test_entered_token_returns_an_empty_text_for_an_entry_without_a_token(text):
    assert entered_token(text) == ""
