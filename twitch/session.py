"""`_AuthState`, the login session, with the save of cookies.jar and the mixin that returns the HTTP session."""
from __future__ import annotations

import asyncio
import logging
from functools import partial
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast, TYPE_CHECKING

import aiohttp
from yarl import URL

from translate import _
from redact import redact
from savefiles import save_each, replace_file
from devicecode import device_code_error, read_json
from exceptions import RequestInvalid
from utils import CHARS_HEX_LOWER, create_nonce
from constants import COOKIES_PATH

from .login import LoginMixin

if TYPE_CHECKING:
    from collections import abc

    from gui import LoginForm
    from settings import Settings
    from browser import IntegrityToken
    from constants import JsonType
    from twitchapi import ClientInfo

    from .client import Twitch


logger = logging.getLogger("TwitchDrops")


def save_cookies(jar: aiohttp.CookieJar) -> None:
    """Save the cookie jar to cookies.jar, or log the OSError of a failed save and keep the old file."""
    save_each(
        [partial(replace_file, COOKIES_PATH, jar.save)],
        lambda error: logger.error(_("error", "file_not_saved").format(file=COOKIES_PATH.name, error=error)),
    )


class _AuthState(LoginMixin):
    def __init__(self, twitch: Twitch):
        self._twitch: Twitch = twitch
        self._lock = asyncio.Lock()
        self._logged_in = asyncio.Event()
        # the client of the device code login, at whose URL cookies.jar keeps the token; each login starts with it
        self._login_client: ClientInfo = twitch._client_type
        # the current integrity token, with the device id it is bound to and its expiry, or None for no web token
        self.integrity: IntegrityToken | None = None
        # one browser runs at a time, so a refresh and the on-error retry never start two
        self._integrity_lock = asyncio.Lock()
        self.user_id: int
        self.device_id: str
        self.session_id: str
        self.access_token: str
        self.client_version: str

    def _hasattrs(self, *attrs: str) -> bool:
        return all(hasattr(self, attr) for attr in attrs)

    def _delattrs(self, *attrs: str) -> None:
        for attr in attrs:
            if hasattr(self, attr):
                delattr(self, attr)

    def invalidate(self, *, delete_cookies: bool = False) -> None:
        self._delattrs("access_token", "user_id")
        self._logged_in.clear()
        self._twitch.gui.help._invalidate_button.config(state="disabled")
        if delete_cookies:
            session = self._twitch._session
            if session is not None:
                jar = cast(aiohttp.CookieJar, session.cookie_jar)
                jar.clear()
                COOKIES_PATH.unlink(missing_ok=True)

    def clear(self) -> None:
        self._delattrs(
            "user_id",
            "device_id",
            "session_id",
            "access_token",
            "client_version",
        )
        self._logged_in.clear()
        self._twitch.gui.help._invalidate_button.config(state="disabled")

    async def _oauth_login(self) -> str:
        login_form: LoginForm = self._twitch.gui.login
        client_info: ClientInfo = self._twitch._client_type
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Accept-Language": "en-US",
            "Cache-Control": "no-cache",
            "Client-Id": client_info.CLIENT_ID,
            "Host": "id.twitch.tv",
            "Origin": str(client_info.CLIENT_URL),
            "Pragma": "no-cache",
            "Referer": str(client_info.CLIENT_URL),
            "User-Agent": client_info.USER_AGENT,
        }
        device_payload = {
            "client_id": client_info.CLIENT_ID,
            "scopes": "",  # no scopes needed
        }
        while True:
            # the code is valid for expires_in from its request, so it is requested only after the press
            if (token := await login_form.ask_login()) is not None:
                return token
            await self._read_device_id()
            headers["X-Device-Id"] = self.device_id
            try:
                now = datetime.now(timezone.utc)
                async with self._twitch.request(
                    "POST", "https://id.twitch.tv/oauth2/device", headers=headers, data=device_payload
                ) as response:
                    # Twitch sends a 40 character device_code, an 8 letter user_code, an interval
                    # of 5 seconds and an expires_in of 1800 seconds.
                    response_json: JsonType = read_json(await response.read())
                    if (message := device_code_error(response.status, response_json)) is not None:
                        logger.warning(f"Twitch sent no device code: {response.status} {redact(response_json)!r}")
                        self._twitch.print(_("login", "no_code").format(message=message))
                        continue
                    device_code: str = response_json["device_code"]
                    user_code: str = response_json["user_code"]
                    interval: int = response_json["interval"]
                    verification_uri: URL = URL(response_json["verification_uri"])
                    expires_at = now + timedelta(seconds=response_json["expires_in"])

                # Print the code to the user, open them the activate page so they can type it in
                await login_form.ask_enter_code(verification_uri, user_code)

                token_payload = {
                    "client_id": self._twitch._client_type.CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                }
                while True:
                    # sleep first, not like the user is gonna enter the code *that* fast
                    await asyncio.sleep(interval)
                    async with self._twitch.request(
                        "POST",
                        "https://id.twitch.tv/oauth2/token",
                        headers=headers,
                        data=token_payload,
                        invalidate_after=expires_at,
                    ) as response:
                        # 200 means success, 400 means the user haven't entered the code yet
                        if response.status != 200:
                            continue
                        response_json = await response.json()
                        # the response also has refresh_token, scope and token_type ("bearer")
                        self.access_token = cast(str, response_json["access_token"])
                        return self.access_token
            except RequestInvalid:
                # the device_code has expired, so the next press requests a new code
                continue

    def headers(self, *, user_agent: str = '', gql: bool = False) -> JsonType:
        client_info: ClientInfo = self._twitch._client_type
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip",
            "Accept-Language": "en-US",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "Client-Id": client_info.CLIENT_ID,
        }
        if user_agent:
            headers["User-Agent"] = user_agent
        if hasattr(self, "session_id"):
            headers["Client-Session-Id"] = self.session_id
        # if hasattr(self, "client_version"):
            # headers["Client-Version"] = self.client_version
        if hasattr(self, "device_id"):
            headers["X-Device-Id"] = self.device_id
        if gql:
            headers["Origin"] = str(client_info.CLIENT_URL)
            headers["Referer"] = str(client_info.CLIENT_URL)
            headers["Authorization"] = f"OAuth {self.access_token}"
            # one read of the record, so a refresh that replaces it cannot split the token from its device id
            if (integrity := self.integrity) is not None:
                headers["Client-Integrity"] = integrity.token
                headers["X-Device-Id"] = integrity.device_id
        return headers

    async def validate(self):
        async with self._lock:
            await self._validate()

    async def _validate(self):
        if not hasattr(self, "session_id"):
            self.session_id = create_nonce(CHARS_HEX_LOWER, 16)
        if not self._hasattrs("access_token", "user_id"):
            jar = cast(aiohttp.CookieJar, (await self._twitch.get_session()).cookie_jar)
            await self._log_in(jar)
            save_cookies(jar)
        # the device ID comes from the URL of the token's client, so it is read after the login
        await self._read_device_id()
        self._twitch.gui.help._invalidate_button.config(state="normal")
        self._logged_in.set()

    async def _read_device_id(self) -> None:
        """Set device_id, when it is not set, to the unique_id cookie that a GET of the client's URL sets."""
        if hasattr(self, "device_id"):
            return
        client_url = self._twitch._client_type.CLIENT_URL
        async with self._twitch.request("GET", client_url, headers=self.headers()) as response:
            page_html = await response.text("utf8")
            assert page_html is not None
        jar = cast(aiohttp.CookieJar, (await self._twitch.get_session()).cookie_jar)
        self.device_id = jar.filter_cookies(client_url)["unique_id"].value


class SessionMixin:
    """The methods of `Twitch` that return the HTTP session and the login state."""

    settings: Settings
    _client_type: ClientInfo
    _session: aiohttp.ClientSession | None
    _auth_state: _AuthState

    async def get_session(self) -> aiohttp.ClientSession:
        if (session := self._session) is not None:
            if session.closed:
                raise RuntimeError("Session is closed")
            return session
        # load in cookies
        cookie_jar = aiohttp.CookieJar()
        try:
            if COOKIES_PATH.exists():
                cookie_jar.load(COOKIES_PATH)
        except Exception as exc:
            # aiohttp reads a file that is not JSON as a pickle, so a broken file raises errors of many types,
            # and a load that fails halfway can leave some cookies in the jar
            logger.warning(f"Could not load cookies.jar, so the app logs in again ({type(exc).__name__}: {exc})")
            cookie_jar.clear()
        # create timeouts
        # connection quality mulitiplier determines the magnitude of timeouts
        connection_quality = self.settings.connection_quality
        if connection_quality < 1:
            connection_quality = self.settings.connection_quality = 1
        elif connection_quality > 6:
            connection_quality = self.settings.connection_quality = 6
        timeout = aiohttp.ClientTimeout(
            sock_connect=5*connection_quality,
            total=10*connection_quality,
        )
        # create session, limited to 50 connections at maximum
        connector = aiohttp.TCPConnector(limit=50)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            cookie_jar=cookie_jar,
            headers={"User-Agent": self._client_type.USER_AGENT},
        )
        return self._session

    def wait_until_login(self) -> abc.Coroutine[Any, Any, Literal[True]]:
        return self._auth_state._logged_in.wait()

    async def get_auth(self) -> _AuthState:
        await self._auth_state.validate()
        return self._auth_state
