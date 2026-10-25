from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from yarl import URL

import twitch.requests as twitch_requests
import twitch.session as twitch_session
from twitchapi import ClientType
from translate import _
from fakes import FakeResponse, FakeTwitch
from livetwitch import FakeSession, run_with_fast_clock

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
# the expires_in and interval that Twitch sends with a device code
LIFETIME = 1800
INTERVAL = 5
DEVICE_FORM = {"client_id": ClientType.ANDROID_APP.CLIENT_ID, "scopes": ""}


class LoopClock(datetime):
    """A `datetime` whose `now` follows the clock of the running event loop, which a `FastClockLoop` moves ahead."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return START + timedelta(seconds=asyncio.get_running_loop().time())


class LoginSession(FakeSession):
    """A session that answers the requests of the device code login and adds each one to `events`.

    The first device requests get `failures`. The user enters the code of the request numbered `entered`, from 1.
    """

    def __init__(
        self, fake: FakeTwitch, events: list[str], *, entered: int, failures: Sequence[FakeResponse] = ()
    ) -> None:
        super().__init__(fake)
        self.events = events
        self.entered = entered
        self.failures = list(failures)
        self.device_forms: list[dict[str, str]] = []

    async def request(self, method: str, url: URL | str, **kwargs: Any) -> FakeResponse:
        path = URL(str(url)).path
        if path == "/oauth2/device":
            self.device_forms.append(kwargs["data"])
            number = len(self.device_forms)
            self.events.append("device")
            if self.failures:
                return self.failures.pop(0)
            return FakeResponse(body=json.dumps({
                "device_code": f"device{number}", "user_code": f"CODE{number}", "interval": INTERVAL,
                "expires_in": LIFETIME, "verification_uri": "https://www.twitch.tv/activate",
            }))
        if path == "/oauth2/token":
            self.events.append("poll")
            if kwargs["data"]["device_code"] != f"device{self.entered}":
                return FakeResponse(400, json.dumps({"message": "authorization_pending"}))
            return FakeResponse(body=json.dumps({"access_token": "new-token"}))
        assert path == "/oauth2/validate"
        return FakeResponse(body=json.dumps({"client_id": DEVICE_FORM["client_id"], "user_id": "7"}))


class FakeLoginForm:
    """A Login Form whose user presses Login after the next wait in `waits`, in seconds, and reads each code shown."""

    def __init__(self, events: list[str], *waits: float) -> None:
        self.events = events
        self.waits = list(waits)

    async def ask_login(self) -> None:
        await asyncio.sleep(self.waits.pop(0))
        self.events.append("press")

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        self.events.append(f"show {user_code}")

    def update(self, status: str, user_id: int | None) -> None:
        pass


def log_in(
    live_twitch, monkeypatch, *waits: float, entered: int, failures: Sequence[FakeResponse] = ()
) -> tuple[list[str], LoginSession, Any]:
    """Log in from an empty cookie jar, and return the events and lines printed, the session and the login state."""
    # the login sets the expiry of the code, and Twitch.request checks it
    monkeypatch.setattr(twitch_session, "datetime", LoopClock)
    monkeypatch.setattr(twitch_requests, "datetime", LoopClock)
    events: list[str] = []
    fake = FakeTwitch()
    client = live_twitch(fake)
    client._session = session = LoginSession(fake, events, entered=entered, failures=failures)
    fake.gui.login = FakeLoginForm(events, *waits)
    fake.gui.print = lambda message: events.append(f"print {message}")
    client._auth_state.invalidate()
    return events, session, run_with_fast_clock(client.get_auth())


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
