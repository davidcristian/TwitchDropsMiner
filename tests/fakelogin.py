"""A session and a Login Form that answer the login, and `log_in`, which runs a login of a real `Twitch` with them."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from yarl import URL

import twitch.requests as twitch_requests
import twitch.session as twitch_session
from twitchapi import ClientType
from fakes import FakeResponse, FakeTwitch
from livetwitch import FakeSession, run_with_fast_clock

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
# the expires_in and interval that Twitch sends with a device code
LIFETIME = 1800
INTERVAL = 5
DEVICE_FORM = {"client_id": ClientType.ANDROID_APP.CLIENT_ID, "scopes": ""}
WWW = URL("https://www.twitch.tv")
WEB = ClientType.WEB
REJECTED = FakeResponse(401, json.dumps({"status": 401, "message": "invalid access token"}))
# an answer to the Login Form that stands for a press of the browser login button
BROWSER_CHOICE = object()


def check_response(client_id: str, user_id: str = "7") -> FakeResponse:
    """Return the response to a token check of a token of the client with client_id, for the user user_id."""
    return FakeResponse(body=json.dumps({
        "client_id": client_id, "login": "user", "scopes": [], "user_id": user_id, "expires_in": 5000,
    }))


class LoopClock(datetime):
    """A `datetime` whose `now` follows the clock of the running event loop, which a `FastClockLoop` moves ahead."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:
        return START + timedelta(seconds=asyncio.get_running_loop().time())


class LoginSession(FakeSession):
    """A session that answers the login's requests, and adds each one but the token check to `events`.

    The first device requests and token checks get `failures` and `checks`; the user enters code number `entered`.
    """

    def __init__(
        self, fake: FakeTwitch, events: list[str], *, entered: int, failures: Sequence[FakeResponse] = (),
        checks: Sequence[FakeResponse] = (),
    ) -> None:
        super().__init__(fake)
        self.events = events
        self.entered = entered
        self.failures = list(failures)
        self.checks = list(checks)
        self.checked: list[str] = []
        self.device_forms: list[dict[str, str]] = []

    async def request(self, method: str, url: URL | str, **kwargs: Any) -> FakeResponse:
        url = URL(str(url))
        path = url.path
        if path == "/":
            # the page of a client's URL sets the unique_id cookie, here id-<host>
            self.events.append(f"page {url.host}")
            self.cookie_jar.update_cookies({"unique_id": f"id-{url.host}"}, url)
            return FakeResponse(body="<html></html>")
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
        if path == "/oauth2/revoke":
            self.events.append(f"revoke {kwargs['data']['client_id']}")
            return FakeResponse()
        assert path == "/oauth2/validate"
        self.checked.append(kwargs["headers"]["Authorization"].removeprefix("OAuth "))
        if self.checks:
            return self.checks.pop(0)
        # a token of the client of the device code login
        return check_response(DEVICE_FORM["client_id"])


class FakeLoginForm:
    """A Login Form whose user gives the next of `answers` at each ask, and reads each code shown.

    An answer is a wait in seconds before a Login press, or a token that the user enters at once.
    """

    def __init__(self, events: list[str], *answers: float | str | object) -> None:
        self.events = events
        self.answers = list(answers)
        # whether cookies.jar exists at each ask
        self.cookie_files: list[bool] = []
        self._browser = False

    @property
    def used_browser(self) -> bool:
        return self._browser

    async def ask_login(self) -> str | None:
        self.cookie_files.append(twitch_session.COOKIES_PATH.exists())
        self._browser = False
        answer = self.answers.pop(0)
        if answer is BROWSER_CHOICE:
            self._browser = True
            self.events.append("browser")
            return None
        if isinstance(answer, str):
            self.events.append(f"token {answer}")
            return answer
        await asyncio.sleep(answer)
        self.events.append("press")
        return None

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        self.events.append(f"show {user_code}")

    def update(self, status: str, user_id: int | None) -> None:
        pass


def log_in(
    live_twitch, monkeypatch, *answers: float | str | object, entered: int = 0, failures: Sequence[FakeResponse] = (),
    checks: Sequence[FakeResponse] = (), saved: str | None = None, new_run: bool = False,
    after: Callable[[Any], Awaitable[Any]] | None = None,
) -> tuple[list[str], LoginSession, Any]:
    """Log in, and return the events and lines printed, the session and the login state.

    saved is the token in cookies.jar at the start; new_run clears the login as `Twitch.shutdown` does; after runs last.
    """
    # the login sets the expiry of the code, and Twitch.request checks it
    monkeypatch.setattr(twitch_session, "datetime", LoopClock)
    monkeypatch.setattr(twitch_requests, "datetime", LoopClock)
    events: list[str] = []
    fake = FakeTwitch()
    client = live_twitch(fake)
    client._session = session = LoginSession(fake, events, entered=entered, failures=failures, checks=checks)
    fake.gui.login = FakeLoginForm(events, *answers)
    fake.gui.print = lambda message: events.append(f"print {message}")
    if new_run:
        client._auth_state.clear()
    else:
        client._auth_state.invalidate()

    async def start() -> Any:
        if saved is not None:
            session.cookie_jar.update_cookies({"auth-token": saved, "persistent": "7"}, WWW)
            twitch_session.save_cookies(session.cookie_jar)
        auth = await client.get_auth()
        if after is not None:
            await after(auth)
        return auth

    return events, session, run_with_fast_clock(start())


def saved_cookies(session: LoginSession) -> dict[str, str]:
    return {name: morsel.value for name, morsel in session.cookie_jar.filter_cookies(WWW).items()}
