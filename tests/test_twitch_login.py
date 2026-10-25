from __future__ import annotations

import json
import logging

import pytest

from translate import _
from fakes import FakeResponse
from twitchapi import ClientType
from fakelogin import DEVICE_FORM, INTERVAL, LIFETIME, log_in


# A press any time after the request of the code would make it valid for a shorter time, or expired
@pytest.mark.parametrize("wait", [0, LIFETIME - 20, LIFETIME - 10, LIFETIME, 2 * 3600])
def test_the_code_is_requested_after_the_login_press_so_a_late_press_shows_a_valid_code(
    live_twitch, monkeypatch, wait
):
    events, session, auth = log_in(live_twitch, monkeypatch, wait, entered=1)

    assert events == ["press", "device", "show CODE1", "poll"]
    assert session.device_forms == [DEVICE_FORM]
    assert (auth.access_token, auth.user_id) == ("new-token", 7)


def test_an_expired_code_is_replaced_only_after_the_next_login_press(live_twitch, monkeypatch):
    events, session, auth = log_in(live_twitch, monkeypatch, 0, 600, entered=2)

    assert [event for event in events if event != "poll"] == [
        "press", "device", "show CODE1", "press", "device", "show CODE2"
    ]
    assert events[-1] == "poll"
    assert session.device_forms == [DEVICE_FORM, DEVICE_FORM]
    assert (auth.access_token, auth.user_id) == ("new-token", 7)


# Since about 2026-09-18 Twitch sends the 400 to the device request of the Android app client ID
@pytest.mark.parametrize(("response", "message"), [
    (FakeResponse(400, json.dumps({"status": 400, "message": "invalid client"})), "invalid client"),
    (FakeResponse(body=json.dumps({"user_code": "CODE", "interval": INTERVAL, "expires_in": LIFETIME})), "200"),
    (FakeResponse(403, "<html>Forbidden</html>"), "403"),
])
def test_a_device_response_without_a_code_prints_twitchs_message_and_the_next_press_sends_one_request(
    live_twitch, monkeypatch, response, message
):
    events, session, auth = log_in(live_twitch, monkeypatch, 0, 0, entered=2, failures=[response])

    assert events == [
        "press", "device", f"print {_('login', 'no_code').format(message=message)}",
        "press", "device", "show CODE2", "poll",
    ]
    assert session.device_forms == [DEVICE_FORM, DEVICE_FORM]
    assert (auth.access_token, auth.user_id) == ("new-token", 7)


def test_the_warning_for_a_device_response_without_a_code_shows_the_status_and_hides_the_device_code(
    live_twitch, monkeypatch, caplog
):
    response = FakeResponse(400, json.dumps({"device_code": "secret", "message": "invalid client"}))
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        log_in(live_twitch, monkeypatch, 0, 0, entered=2, failures=[response])

    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert warnings == ["Twitch sent no device code: 400 {'device_code': '<hidden>', 'message': 'invalid client'}"]


def test_the_device_code_login_of_a_new_run_reads_the_device_id_after_the_login_press(live_twitch, monkeypatch):
    events, session, auth = log_in(live_twitch, monkeypatch, 0, entered=1, new_run=True)

    assert events == ["press", "page www.twitch.tv", "device", "show CODE1", "poll"]
    assert (auth.device_id, auth._twitch._client_type) == ("id-www.twitch.tv", ClientType.ANDROID_APP)
