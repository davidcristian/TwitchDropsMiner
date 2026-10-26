from __future__ import annotations

from browser import IntegrityToken
from fakelogin import WEB, check_response, log_in


def logged_in_web(live_twitch, monkeypatch):
    _, session, auth = log_in(live_twitch, monkeypatch, "web-token", checks=[check_response(WEB.CLIENT_ID, "123")])
    return session, auth


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
