from __future__ import annotations

import asyncio

import pytest

import browser
from browser import IntegrityToken, LoginResult, NetworkEvent


class FakeConnection:
    """A `BrowserConnection` for tests: it replays scripted events, cookies and response bodies."""

    def __init__(
        self,
        events: list[NetworkEvent] | None = None,
        cookie_steps: list[dict[str, str]] | None = None,
        bodies: dict[str, str] | None = None,
    ) -> None:
        self._events = list(events or [])
        self._cookie_steps = list(cookie_steps or [])
        self._bodies = bodies or {}
        self.set_cookie_args: tuple | None = None
        self.navigated: list[str] = []

    async def set_cookie(self, name: str, value: str, domain: str, path: str, secure: bool) -> None:
        self.set_cookie_args = (name, value, domain, path, secure)

    async def navigate(self, url: str) -> None:
        self.navigated.append(url)

    async def next_event(self, timeout: float) -> NetworkEvent | None:
        return self._events.pop(0) if self._events else None

    async def response_body(self, request_id: str) -> str | None:
        return self._bodies.get(request_id)

    async def cookies(self) -> dict[str, str]:
        return self._cookie_steps.pop(0) if self._cookie_steps else {}


def integrity_body(expiration: int = 1793000000000) -> str:
    return f'{{"token": "v4.local.TOKEN", "expiration": {expiration}, "request_id": "r"}}'


def request_event(device_id: str = "DEV") -> NetworkEvent:
    return NetworkEvent("request", "https://gql.twitch.tv/integrity", "req1", {"X-Device-Id": device_id})


def response_event() -> NetworkEvent:
    return NetworkEvent("response", "https://gql.twitch.tv/integrity", "req1", {})


def test_find_browser_returns_the_configured_file(tmp_path):
    chrome = tmp_path / "chrome"
    chrome.write_text("")
    assert browser.find_browser(str(chrome)) == str(chrome)


def test_find_browser_rejects_a_configured_path_that_is_not_a_file(tmp_path):
    assert browser.find_browser(str(tmp_path / "missing")) is None


def test_find_browser_returns_the_first_name_on_the_path():
    assert browser.find_browser("", names=["definitely-not-a-browser", "sh"]) == browser.shutil.which("sh")


def test_find_browser_returns_none_when_no_name_is_found():
    assert browser.find_browser("", names=["definitely-not-a-browser-xyz"]) is None


def test_launch_args_for_login_has_no_headless_or_user_agent():
    args = browser.launch_args(9222, "/tmp/p", headless=False)
    assert "--headless=new" not in args
    assert not any(arg.startswith("--user-agent=") for arg in args)
    assert args[-1] == browser.INVENTORY_URL


def test_launch_args_for_refresh_has_headless_and_the_user_agent():
    args = browser.launch_args(9222, "/tmp/p", headless=True, user_agent="UA/1")
    assert "--headless=new" in args
    assert "--user-agent=UA/1" in args


def test_login_options_is_a_visible_window_with_its_own_user_agent():
    assert browser.login_options() == browser.LaunchOptions(headless=False, user_agent="", xvfb=False)


def test_refresh_options_on_linux_is_headful_under_xvfb(monkeypatch):
    monkeypatch.setattr(browser.sys, "platform", "linux")
    assert browser.refresh_options("UA/1") == browser.LaunchOptions(headless=False, user_agent="", xvfb=True)


def test_refresh_options_off_linux_is_headless_with_the_user_agent(monkeypatch):
    monkeypatch.setattr(browser.sys, "platform", "win32")
    assert browser.refresh_options("UA/1") == browser.LaunchOptions(headless=True, user_agent="UA/1", xvfb=False)


def test_device_of_reads_the_header_without_case():
    assert browser.device_of(NetworkEvent("request", "u", "1", {"x-DEVICE-id": "abc"})) == "abc"


def test_device_of_is_empty_without_the_header():
    assert browser.device_of(NetworkEvent("request", "u", "1", {"Other": "y"})) == ""


def test_parse_integrity_reads_the_token_and_expiration():
    token = browser.parse_integrity(integrity_body(1793000000000), "DEV")
    assert token == IntegrityToken("v4.local.TOKEN", "DEV", 1793000000000)


@pytest.mark.parametrize("body", ["not json", "[]", '{"expiration": 1}', '{"token": "t"}', '{"token": "", "expiration": 1}'])
def test_parse_integrity_rejects_a_body_without_a_token_and_expiration(body):
    assert browser.parse_integrity(body, "DEV") is None


def test_parse_integrity_rejects_a_boolean_expiration():
    assert browser.parse_integrity('{"token": "t", "expiration": true}', "DEV") is None


def test_capture_integrity_sets_the_cookie_navigates_and_returns_the_token():
    conn = FakeConnection(events=[request_event("DEV"), response_event()], bodies={"req1": integrity_body()})
    token = asyncio.run(browser.capture_integrity(conn, "AUTH", 1.0))
    assert token == IntegrityToken("v4.local.TOKEN", "DEV", 1793000000000)
    assert conn.set_cookie_args == (browser.AUTH_COOKIE, "AUTH", ".twitch.tv", "/", True)
    assert conn.navigated == [browser.INVENTORY_URL]


def test_capture_integrity_returns_none_when_no_integrity_arrives():
    conn = FakeConnection(events=[])
    assert asyncio.run(browser.capture_integrity(conn, "AUTH", 0.01)) is None


def test_capture_integrity_keeps_waiting_after_a_body_it_cannot_parse():
    conn = FakeConnection(events=[request_event("DEV"), response_event()], bodies={"req1": "broken"})
    assert asyncio.run(browser.capture_integrity(conn, "AUTH", 0.01)) is None


def test_capture_login_returns_the_token_and_integrity_when_the_cookie_appears():
    conn = FakeConnection(
        cookie_steps=[{browser.AUTH_COOKIE: "AT"}],
        events=[request_event("DEV"), response_event()],
        bodies={"req1": integrity_body()},
    )
    result = asyncio.run(browser.capture_login(conn, 5.0, poll=0.01))
    assert result == LoginResult("AT", IntegrityToken("v4.local.TOKEN", "DEV", 1793000000000))


def test_capture_login_returns_none_when_no_login_happens():
    conn = FakeConnection(cookie_steps=[{}])
    assert asyncio.run(browser.capture_login(conn, 0.02, poll=0.01)) is None
