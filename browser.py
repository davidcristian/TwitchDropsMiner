"""The browser engine logic: find a browser, build its launch arguments, parse the integrity response, and
capture a login or an integrity token. It drives a `BrowserConnection` (`browsercdp.py`, over the Chrome DevTools
Protocol) and holds every decision, so a fake connection tests it without a real browser or Twitch.
"""
from __future__ import annotations

import sys
import json
import shutil
from pathlib import Path
from typing import Any, NamedTuple, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from collections import abc


# the drops inventory page, whose own requests include the integrity token the app needs
INVENTORY_URL = "https://www.twitch.tv/drops/inventory"
# the path of the request whose response holds the integrity token and its expiration
INTEGRITY_SUFFIX = "/integrity"
# the cookie the browser sets once the user has logged in
AUTH_COOKIE = "auth-token"
# the names a Chromium-based browser is installed under, in the order the engine tries them
BROWSER_NAMES = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "brave",
)


class IntegrityToken(NamedTuple):
    """An integrity token with the device ID it is bound to and the epoch milliseconds it expires at."""

    token: str
    device_id: str
    expires_at: int


class LoginResult(NamedTuple):
    """The token a login captured, with the integrity token of the same browser session when it was seen."""

    access_token: str
    integrity: IntegrityToken | None


class NetworkEvent(NamedTuple):
    """A request or response the browser reported, normalized to what the engine reads."""

    kind: str  # "request" or "response"
    url: str
    request_id: str
    headers: dict[str, str]


class LaunchOptions(NamedTuple):
    """How to start the browser: headless with user_agent, or a visible or virtual-display window with its own."""

    headless: bool
    user_agent: str
    xvfb: bool


def login_options() -> LaunchOptions:
    """Return the options for the login window: a visible browser on the user's display with its own user agent."""
    return LaunchOptions(headless=False, user_agent="", xvfb=False)


def refresh_options(user_agent: str) -> LaunchOptions:
    """Return the launch options for an invisible refresh: headful under Xvfb on Linux, else headless with user_agent."""
    if sys.platform.startswith("linux"):
        return LaunchOptions(headless=False, user_agent="", xvfb=True)
    return LaunchOptions(headless=True, user_agent=user_agent, xvfb=False)


class BrowserConnection(Protocol):
    """One browser the engine drives: it sets a cookie, opens a page, and reports the page's own requests."""

    async def set_cookie(self, name: str, value: str, domain: str, path: str, secure: bool) -> None: ...

    async def navigate(self, url: str) -> None: ...

    async def next_event(self, timeout: float) -> NetworkEvent | None:
        """Return the next request or response the page made, or None when timeout seconds pass with none."""
        ...

    async def response_body(self, request_id: str) -> str | None:
        """Return the body of the response with request_id, or None when it cannot be read."""
        ...

    async def cookies(self) -> dict[str, str]:
        """Return the browser's current cookies as a name to value mapping."""
        ...


def find_browser(configured: str = "", names: abc.Iterable[str] = BROWSER_NAMES) -> str | None:
    """Return the browser to run: the configured path when it is a file, else the first of names on the PATH."""
    if configured:
        return configured if Path(configured).is_file() else None
    return next((found for name in names if (found := shutil.which(name))), None)


def launch_args(port: int, profile: str, *, headless: bool, user_agent: str = "") -> list[str]:
    """Return the browser arguments for a debugging port and a throwaway profile; headless and user_agent optional."""
    args = [
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    if user_agent:
        args.append(f"--user-agent={user_agent}")
    args.append(INVENTORY_URL)
    return args


def device_of(event: NetworkEvent) -> str:
    """Return the X-Device-Id header of a request event, compared without case, or an empty string."""
    return next((value for key, value in event.headers.items() if key.lower() == "x-device-id"), "")


def parse_integrity(body: str, device_id: str) -> IntegrityToken | None:
    """Return the integrity token of an /integrity response body bound to device_id, or None when it has none."""
    try:
        data: Any = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    expiration = data.get("expiration")
    if not isinstance(token, str) or not token or isinstance(expiration, bool):
        return None
    if not isinstance(expiration, (int, float)):
        return None
    return IntegrityToken(token, device_id, int(expiration))


async def capture_integrity(
    connection: BrowserConnection, access_token: str, timeout: float
) -> IntegrityToken | None:
    """Open the inventory page with access_token and return the integrity token of the page's own request."""
    await connection.set_cookie(AUTH_COOKIE, access_token, ".twitch.tv", "/", True)
    await connection.navigate(INVENTORY_URL)
    return await _await_integrity(connection, timeout)


async def _await_integrity(connection: BrowserConnection, timeout: float) -> IntegrityToken | None:
    """Return the integrity token from the page's /integrity response, or None when none arrives in time."""
    device_id = ""
    integrity_id = ""
    while True:
        event = await connection.next_event(timeout)
        if event is None:
            return None
        if event.kind == "request" and (device := device_of(event)):
            device_id = device
        if event.kind == "response" and event.url.endswith(INTEGRITY_SUFFIX):
            integrity_id = event.request_id
        if integrity_id and device_id:
            body = await connection.response_body(integrity_id)
            if body is not None and (token := parse_integrity(body, device_id)) is not None:
                return token
            integrity_id = ""


async def capture_login(connection: BrowserConnection, timeout: float, poll: float = 1.0) -> LoginResult | None:
    """Wait for the auth-token cookie the user's login sets on the inventory page, and return it with the integrity
    token the page requests next, or None when no login arrives within timeout seconds."""
    await connection.navigate(INVENTORY_URL)
    waited = 0.0
    while waited < timeout:
        cookies = await connection.cookies()
        if token := cookies.get(AUTH_COOKIE):
            integrity = await _await_integrity(connection, poll)
            return LoginResult(token, integrity)
        event = await connection.next_event(poll)
        if event is None:
            waited += poll
    return None
