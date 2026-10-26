from __future__ import annotations

import asyncio

import pytest

import browser
import browsercdp
from browser import IntegrityToken, LoginResult
from exceptions import RequestException
from fakelogin import BROWSER_CHOICE, WEB, check_response, log_in


def logged_in_web(live_twitch, monkeypatch):
    _, session, auth = log_in(live_twitch, monkeypatch, "web-token", checks=[check_response(WEB.CLIENT_ID, "123")])
    return session, auth


class FakeLaunch:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def patch_engine(monkeypatch, *, path="/x/chrome", login=None, integrity=None):
    monkeypatch.setattr(browser, "find_browser", lambda configured="", names=None: path)
    monkeypatch.setattr(browsercdp, "launch", lambda browser_path, options: FakeLaunch())

    async def fake_login(connection, timeout, poll=1.0):
        return login

    async def fake_integrity(connection, access_token, timeout):
        return integrity

    monkeypatch.setattr(browser, "capture_login", fake_login)
    monkeypatch.setattr(browser, "capture_integrity", fake_integrity)


def test_gql_headers_send_the_integrity_token_and_its_device_id(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    auth.integrity = IntegrityToken("itok", "idev", 1793000000000)
    gql = auth.headers(user_agent=WEB.USER_AGENT, gql=True)
    assert gql["Client-Integrity"] == "itok"
    assert gql["X-Device-Id"] == "idev"


def test_gql_headers_omit_the_integrity_token_when_there_is_none(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    assert auth.integrity is None
    gql = auth.headers(user_agent=WEB.USER_AGENT, gql=True)
    assert "Client-Integrity" not in gql
    assert gql["X-Device-Id"] != "idev"


def test_non_gql_headers_never_include_the_integrity_token(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    auth.integrity = IntegrityToken("itok", "idev", 1)
    assert "Client-Integrity" not in auth.headers()


def test_browser_login_returns_the_token_and_stores_the_integrity(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, login=LoginResult("newtok", IntegrityToken("i", "d", 5)))
    assert asyncio.run(auth.browser_login()) == "newtok"
    assert auth.integrity == IntegrityToken("i", "d", 5)


def test_browser_login_raises_when_the_login_times_out(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, login=None)
    with pytest.raises(RequestException):
        asyncio.run(auth.browser_login())


def test_browser_login_raises_without_a_browser(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, path=None)
    with pytest.raises(RequestException):
        asyncio.run(auth.browser_login())


def test_refresh_integrity_stores_a_new_token(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, integrity=IntegrityToken("i2", "d2", 9))
    assert asyncio.run(auth.refresh_integrity()) is True
    assert auth.integrity == IntegrityToken("i2", "d2", 9)


def test_refresh_integrity_returns_false_when_the_browser_gives_no_token(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, integrity=None)
    assert asyncio.run(auth.refresh_integrity()) is False
    assert auth.integrity is None


def test_refresh_integrity_returns_false_without_a_browser(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    patch_engine(monkeypatch, path=None, integrity=IntegrityToken("i", "d", 1))
    assert asyncio.run(auth.refresh_integrity()) is False


def test_refresh_integrity_returns_false_before_login(live_twitch, monkeypatch):
    _, auth = logged_in_web(live_twitch, monkeypatch)
    del auth.access_token
    patch_engine(monkeypatch, integrity=IntegrityToken("i", "d", 1))
    assert asyncio.run(auth.refresh_integrity()) is False


def test_the_browser_button_logs_in_and_keeps_the_integrity(live_twitch, monkeypatch):
    patch_engine(monkeypatch, login=LoginResult("browser-token", IntegrityToken("i", "d", 5)))
    events, _, auth = log_in(
        live_twitch, monkeypatch, BROWSER_CHOICE, checks=[check_response(WEB.CLIENT_ID, "7")]
    )
    assert "browser" in events
    assert auth.access_token == "browser-token"
    assert auth._twitch._client_type is WEB
    assert auth.integrity == IntegrityToken("i", "d", 5)
