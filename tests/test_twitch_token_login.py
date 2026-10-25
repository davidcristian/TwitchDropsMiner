from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

import twitch.session as twitch_session
from twitchapi import ClientType
from translate import _
from exceptions import RequestException
from ui.helptab import HelpTab
from fakes import FakeResponse
from fakelogin import DEVICE_FORM, REJECTED, WEB, check_response, log_in, saved_cookies


def test_an_entered_token_of_the_web_client_is_used_with_the_web_client_from_then_on(live_twitch, monkeypatch):
    events, session, auth = log_in(live_twitch, monkeypatch, "web-token", checks=[check_response(WEB.CLIENT_ID, "123")])

    assert events == ["token web-token"]
    assert session.checked == ["web-token"]
    assert (auth.access_token, auth.user_id) == ("web-token", 123)
    assert auth._twitch._client_type is WEB
    assert session.headers["User-Agent"] == WEB.USER_AGENT
    gql = auth.headers(user_agent=auth._twitch._client_type.USER_AGENT, gql=True)
    assert (gql["Client-Id"], gql["User-Agent"], gql["Authorization"]) == (
        WEB.CLIENT_ID, WEB.USER_AGENT, "OAuth web-token"
    )
    assert saved_cookies(session) == {"auth-token": "web-token", "persistent": "123"}
    assert "web-token" in twitch_session.COOKIES_PATH.read_text()


def test_a_rejected_token_prints_that_twitch_did_not_accept_it_and_asks_again(live_twitch, monkeypatch):
    events, session, auth = log_in(
        live_twitch, monkeypatch, "bad-token", "web-token", checks=[REJECTED, check_response(WEB.CLIENT_ID)]
    )

    assert events == ["token bad-token", f"print {_('login', 'token_rejected')}", "token web-token"]
    assert session.checked == ["bad-token", "web-token"]
    assert (auth.access_token, auth._twitch._client_type) == ("web-token", WEB)


def test_a_token_of_an_unknown_client_prints_so_and_asks_again(live_twitch, monkeypatch):
    events, session, auth = log_in(
        live_twitch, monkeypatch, "other-token", "web-token",
        checks=[check_response("unknown-client-id"), check_response(WEB.CLIENT_ID)],
    )

    assert events == ["token other-token", f"print {_('login', 'unknown_client')}", "token web-token"]
    assert session.checked == ["other-token", "web-token"]
    assert (auth.access_token, auth._twitch._client_type) == ("web-token", WEB)


def test_a_check_with_another_status_ends_the_run_with_an_error(live_twitch, monkeypatch):
    with pytest.raises(RequestException, match="400"):
        log_in(live_twitch, monkeypatch, "web-token", checks=[FakeResponse(400, "{}")])


def test_a_saved_token_of_the_web_client_switches_to_the_web_client_and_keeps_cookies_jar(live_twitch, monkeypatch):
    events, session, auth = log_in(live_twitch, monkeypatch, saved="web-token", checks=[check_response(WEB.CLIENT_ID)])

    assert events == []
    assert session.checked == ["web-token"]
    assert (auth.access_token, auth._twitch._client_type) == ("web-token", WEB)
    assert session.headers["User-Agent"] == WEB.USER_AGENT
    assert saved_cookies(session)["auth-token"] == "web-token"
    assert "web-token" in twitch_session.COOKIES_PATH.read_text()


def test_a_saved_token_of_an_unknown_client_deletes_cookies_jar_and_asks_for_a_login(live_twitch, monkeypatch):
    events, session, auth = log_in(
        live_twitch, monkeypatch, "web-token", saved="old-token",
        checks=[check_response("unknown-client-id"), check_response(WEB.CLIENT_ID)],
    )

    assert events == ["token web-token"]
    assert session.checked == ["old-token", "web-token"]
    assert auth._twitch.gui.login.cookie_files == [False]
    assert saved_cookies(session) == {"auth-token": "web-token", "persistent": "7"}


def test_a_rejected_saved_token_is_removed_and_the_login_form_asks_without_a_message(live_twitch, monkeypatch):
    events, session, auth = log_in(
        live_twitch, monkeypatch, "web-token", saved="old-token", checks=[REJECTED, check_response(WEB.CLIENT_ID)]
    )

    assert events == ["token web-token"]
    assert session.checked == ["old-token", "web-token"]
    assert saved_cookies(session)["auth-token"] == "web-token"


def test_a_new_run_with_a_saved_token_reads_the_device_id_from_the_url_of_its_client(live_twitch, monkeypatch):
    mobile = ClientType.MOBILE_WEB
    events, session, auth = log_in(
        live_twitch, monkeypatch, saved="mobile-token", new_run=True, checks=[check_response(mobile.CLIENT_ID)]
    )

    # one GET, of the URL of the token's client, so the device ID is read after the token check
    assert events == ["page m.twitch.tv"]
    assert (auth._twitch._client_type, auth.device_id) == (mobile, "id-m.twitch.tv")
    # cookies.jar keeps the token at the URL of the client that each login starts with
    assert saved_cookies(session)["auth-token"] == "mobile-token"


def test_a_token_of_a_client_with_another_url_replaces_the_device_id(live_twitch, monkeypatch):
    smartbox = ClientType.SMARTBOX
    events, session, auth = log_in(live_twitch, monkeypatch, "tv-token", checks=[check_response(smartbox.CLIENT_ID)])

    assert events == ["token tv-token", "page android.tv.twitch.tv"]
    assert auth.headers()["X-Device-Id"] == "id-android.tv.twitch.tv"


def test_a_login_after_a_run_with_the_web_client_starts_with_the_android_app_client(live_twitch, monkeypatch):
    async def log_in_again(auth) -> None:
        auth._twitch._session.cookie_jar.clear()
        auth.clear()
        await auth._twitch.get_auth()

    events, session, auth = log_in(
        live_twitch, monkeypatch, "web-token", 0, entered=1, checks=[check_response(WEB.CLIENT_ID)],
        after=log_in_again,
    )

    assert session.device_forms == [DEVICE_FORM]
    assert (auth.access_token, auth._twitch._client_type) == ("new-token", ClientType.ANDROID_APP)
    assert session.headers["User-Agent"] == ClientType.ANDROID_APP.USER_AGENT


def test_invalidate_revokes_the_token_with_the_client_id_of_the_token(live_twitch, monkeypatch):
    async def invalidate(auth) -> None:
        await HelpTab._invalidate_token(SimpleNamespace(_twitch=auth._twitch))

    events, session, auth = log_in(
        live_twitch, monkeypatch, "web-token", checks=[check_response(WEB.CLIENT_ID)], after=invalidate
    )

    assert events == ["token web-token", f"revoke {WEB.CLIENT_ID}"]
    assert not twitch_session.COOKIES_PATH.exists()


def test_the_token_is_in_no_log_record(live_twitch, monkeypatch, caplog):
    with caplog.at_level(logging.DEBUG, logger="TwitchDrops"):
        events, session, auth = log_in(
            live_twitch, monkeypatch, "s3cret-bad", "s3cret-web", saved="s3cret-old",
            checks=[REJECTED, REJECTED, check_response(WEB.CLIENT_ID)],
        )

    assert session.checked == ["s3cret-old", "s3cret-bad", "s3cret-web"]
    messages = [record.getMessage() for record in caplog.records]
    assert sum("oauth2/validate" in message for message in messages) >= 3
    assert [message for message in messages if "s3cret" in message] == []
    assert [event for event in events if "print" in event and "s3cret" in event] == []
