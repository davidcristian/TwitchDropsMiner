import pytest

from devicecode import CODE_FIELDS, device_code_error, read_json

CODE = {
    "device_code": "device", "user_code": "CODE", "interval": 5, "expires_in": 1800,
    "verification_uri": "https://www.twitch.tv/activate",
}


def test_read_json_returns_the_value_of_a_json_body():
    assert read_json(b'{"status": 400, "message": "invalid client"}') == {"status": 400, "message": "invalid client"}
    assert read_json(b"[1, null]") == [1, None]


@pytest.mark.parametrize("body", [b"", b"<html>Forbidden</html>", b'{"message": ', b"\x80\x81"])
def test_read_json_returns_none_for_a_body_that_is_not_json(body):
    assert read_json(body) is None


def test_device_code_error_returns_none_for_a_200_with_every_field():
    assert device_code_error(200, CODE) is None
    assert device_code_error(200, {**CODE, "message": "ok", "scope": []}) is None


@pytest.mark.parametrize("field", CODE_FIELDS)
def test_device_code_error_returns_the_status_for_a_200_that_lacks_a_field(field):
    body = {key: value for key, value in CODE.items() if key != field}
    assert device_code_error(200, body) == "200"


def test_device_code_error_returns_twitchs_message():
    assert device_code_error(400, {"status": 400, "message": "invalid client"}) == "invalid client"
    assert device_code_error(200, {"message": "no code"}) == "no code"


def test_device_code_error_returns_the_message_for_a_status_other_than_200_with_every_field():
    assert device_code_error(400, {**CODE, "message": "invalid client"}) == "invalid client"
    assert device_code_error(201, CODE) == "201"


@pytest.mark.parametrize("message", [None, "", 400, ["invalid client"]])
def test_device_code_error_returns_the_status_for_an_empty_message_or_one_that_is_not_text(message):
    assert device_code_error(400, {"status": 400, "message": message}) == "400"


@pytest.mark.parametrize("body", [None, [], "invalid client", 400])
def test_device_code_error_returns_the_status_for_a_body_that_is_not_an_object(body):
    assert device_code_error(400, body) == "400"
    assert device_code_error(200, body) == "200"
