"""A real `Twitch` with a fake window and session, and an event loop whose timers fire without a wait."""
from __future__ import annotations

import asyncio
import json
import selectors
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from functools import cached_property
from pathlib import Path
from typing import Any, TypeVar

import aiohttp
import pytest
from yarl import URL

import twitch as twitch_module
from constants import JsonType
from fakes import FakeResponse, FakeTwitch
from twitch import Twitch

T = TypeVar("T")
SERVER_CLOSE = aiohttp.WSMessage(aiohttp.WSMsgType.CLOSE, 1000, None)


class FakePubSub:
    """A PubSub connection that returns the frames a test gives it, then waits until it is closed.

    A frame is the text of a message, or `SERVER_CLOSE`. Each message the app sends is added to `sent`.
    """

    def __init__(self, *frames: str | aiohttp.WSMessage) -> None:
        self._frames = list(frames)
        self._closed = asyncio.Event()
        self.sent: list[JsonType] = []
        self.close_code = 1000

    async def receive(self, timeout: float | None = None) -> aiohttp.WSMessage:
        # a read from the network lets the other tasks run
        await asyncio.sleep(0)
        if self._frames:
            frame = self._frames.pop(0)
            if isinstance(frame, str):
                return aiohttp.WSMessage(aiohttp.WSMsgType.TEXT, frame, None)
            return frame
        await asyncio.wait_for(self._closed.wait(), timeout)
        return aiohttp.WSMessage(aiohttp.WSMsgType.CLOSED, None, None)

    async def send_json(self, data: JsonType, *, dumps: Callable[[Any], str] = json.dumps) -> None:
        self.sent.append(data)

    async def close(self) -> bool:
        self._closed.set()
        return True


def refuse_pubsub() -> FakePubSub:
    """Fail a PubSub connect, as a server that cannot be reached does."""
    raise aiohttp.ClientConnectionError("connection refused")


class FakeSession:
    """An `aiohttp.ClientSession` that passes each request to a `FakeTwitch` and each websocket connect to pubsub."""

    def __init__(self, fake: FakeTwitch, pubsub: Callable[[], FakePubSub] = refuse_pubsub) -> None:
        self._fake = fake
        self._pubsub = pubsub
        self.closed = False
        self.timeout = aiohttp.ClientTimeout(sock_connect=5, total=10)

    @cached_property
    def cookie_jar(self) -> aiohttp.CookieJar:
        # aiohttp creates a cookie jar only in a running event loop
        return aiohttp.CookieJar()

    async def request(self, method: str, url: URL | str, **kwargs: Any) -> FakeResponse:
        url = URL(str(url))
        if url.host == "gql.twitch.tv":
            response = FakeResponse(body=json.dumps(await self._fake.gql_request(kwargs["json"])))
        else:
            response = await self._fake.answer_http(method, url)
        response.method, response.url = method, url
        return response

    @asynccontextmanager
    async def ws_connect(self, url: str, **kwargs: Any) -> AsyncIterator[FakePubSub]:
        self._fake.http_sent.append(f"WS {URL(url).host}")
        connection = self._pubsub()
        try:
            yield connection
        finally:
            await connection.close()

    async def close(self) -> None:
        self.closed = True


def build_twitch(
    monkeypatch: pytest.MonkeyPatch, cookies: Path, fake: FakeTwitch, pubsub: Callable[[], FakePubSub] = refuse_pubsub
) -> Twitch:
    """Return a real `Twitch` logged in as user 1, with the window and settings of fake and a `FakeSession`.

    cookies is the path at which it reads and saves cookies.jar, and pubsub opens each PubSub connection.
    """
    monkeypatch.setattr(twitch_module, "COOKIES_PATH", cookies)
    # Twitch.__init__ creates the window, which needs a display
    monkeypatch.setattr(twitch_module, "GUIManager", lambda client: fake.gui)
    client = Twitch(fake.settings)
    client._session = FakeSession(fake, pubsub)
    auth = client._auth_state
    auth.user_id, auth.device_id, auth.session_id, auth.access_token = 1, "device", "session", "token"
    return client


class _SkippingSelector(selectors.DefaultSelector):
    """A selector that returns at once when no file is ready, and adds the time it would have waited to `skipped`."""

    skipped = 0.0

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None or timeout <= 0:
            return super().select(timeout)
        ready = super().select(0)
        if not ready:
            self.skipped += timeout
        return ready


class FastClockLoop(asyncio.SelectorEventLoop):
    """An event loop whose clock moves on to the next timer when no task can run, so a timed wait takes no time."""

    def __init__(self) -> None:
        self._skipping = _SkippingSelector()
        super().__init__(self._skipping)

    def time(self) -> float:
        return super().time() + self._skipping.skipped


def run_with_fast_clock(main: Coroutine[Any, Any, T]) -> T:
    """Run main as `asyncio.run` does, on a `FastClockLoop`."""
    loop = FastClockLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(main)
    finally:
        try:
            tasks = asyncio.all_tasks(loop)
            for task in tasks:
                task.cancel()
            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
