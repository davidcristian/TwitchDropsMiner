"""The mixin of `_AuthState` that checks a token from cookies.jar or the Login Form and uses the token's client."""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

import browser
import browsercdp
from translate import _
from tokencheck import TokenResult, check_token
from exceptions import RequestException
from twitchapi import ClientType
from constants import BROWSER_LOGIN_TIMEOUT, INTEGRITY_CAPTURE_TIMEOUT

if TYPE_CHECKING:
    import asyncio
    from collections import abc

    import aiohttp

    from gui import LoginForm
    from browser import IntegrityToken
    from twitchapi import ClientInfo

    from .client import Twitch


logger = logging.getLogger("TwitchDrops")


class LoginMixin:
    """The methods of `_AuthState` that log in with a token Twitch accepts, and switch to the client of the token."""

    _twitch: Twitch
    _login_client: ClientInfo
    access_token: str
    user_id: int
    integrity: IntegrityToken | None
    _integrity_lock: asyncio.Lock
    _delattrs: abc.Callable[..., None]
    _oauth_login: abc.Callable[[], abc.Coroutine[Any, Any, str]]
    invalidate: abc.Callable[..., None]

    def _browser_path(self) -> str:
        """Return the browser to run, or raise when none is found."""
        path = browser.find_browser(self._twitch.settings.browser_path)
        if path is None:
            raise RequestException(_("login", "no_browser"))
        return path

    async def browser_login(self) -> str:
        """Open a visible browser, wait for the user to log in, and return the token; keep the integrity token."""
        async with browsercdp.launch(self._browser_path(), browser.login_options()) as connection:
            result = await browser.capture_login(connection, BROWSER_LOGIN_TIMEOUT.total_seconds())
        if result is None:
            raise RequestException(_("login", "browser_timeout"))
        self.integrity = result.integrity
        return result.access_token

    async def refresh_integrity(self) -> bool:
        """Run the browser to get a fresh integrity token for the current token; return whether one was captured."""
        async with self._integrity_lock:
            if not hasattr(self, "access_token"):
                return False
            try:
                options = browser.refresh_options(ClientType.WEB.USER_AGENT)
                async with browsercdp.launch(self._browser_path(), options) as connection:
                    token = await browser.capture_integrity(
                        connection, self.access_token, INTEGRITY_CAPTURE_TIMEOUT.total_seconds()
                    )
            except Exception as exc:
                # the task that calls this must keep running, so a failed refresh is logged, not raised
                logger.error(f"Integrity refresh failed: {type(exc).__name__}: {exc}")
                return False
            if token is None:
                logger.warning("The browser produced no integrity token")
                return False
            self.integrity = token
            return True

    def _use_client(self, client: ClientInfo) -> None:
        """Send the client ID, URL and user agent of client from now on."""
        if client.CLIENT_URL != self._twitch._client_type.CLIENT_URL:
            self._delattrs("device_id")
        self._twitch._client_type = client
        if (session := self._twitch._session) is not None:
            session.headers["User-Agent"] = client.USER_AGENT

    async def _log_in(self, jar: aiohttp.CookieJar) -> None:
        """Log in with the token of jar, or else with one from the Login Form, and store it in jar."""
        login_form: LoginForm = self._twitch.gui.login
        login_url = self._login_client.CLIENT_URL
        logger.info("Checking login")
        login_form.update(_("gui", "login", "logging_in"), None)
        self._use_client(self._login_client)
        while True:
            cookie = jar.filter_cookies(login_url)
            if saved := "auth-token" in cookie:
                logger.info("Restoring session from cookie")
                token = cookie["auth-token"].value
            else:
                token = await self._oauth_login()
            async with self._twitch.request(
                "GET", "https://id.twitch.tv/oauth2/validate", headers={"Authorization": f"OAuth {token}"}
            ) as response:
                # a 200 response that is not JSON, such as a network's login page, raises ContentTypeError
                check = check_token(response.status, await response.json() if response.status == 200 else None)
            if check.result is TokenResult.ACCEPTED:
                break
            elif check.result is TokenResult.FAILED:
                raise RequestException(f"Login verification failure: {response.status}")
            elif not saved:
                rejected = check.result is TokenResult.REJECTED
                self._twitch.print(_("login", "token_rejected" if rejected else "unknown_client"))
            elif check.result is TokenResult.REJECTED:
                logger.info("Restored session is invalid")
                assert login_url.host is not None
                jar.clear_domain(login_url.host)
            else:
                logger.info("Restored session is of an unknown client")
                self.invalidate(delete_cookies=True)
        assert check.client is not None
        self._use_client(check.client)
        self.access_token, self.user_id = token, check.user_id
        cookie["auth-token"] = token
        cookie["persistent"] = str(self.user_id)
        logger.info(f"Login successful, user ID: {self.user_id}")
        login_form.update(_("gui", "login", "logged_in"), self.user_id)
        jar.update_cookies(cookie, login_url)
