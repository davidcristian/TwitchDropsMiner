from __future__ import annotations

import asyncio

import aiohttp
import pytest

import browsercdp
from browser import LaunchOptions


class FakeMessage:
    def __init__(self, data: dict) -> None:
        self.type = aiohttp.WSMsgType.TEXT
        self._data = data

    def json(self) -> dict:
        return self._data


class FakeWebSocket:
    """A stand-in websocket: a sent command gets a canned result back, and seeded events arrive with no id."""

    def __init__(self, results: dict | None = None, events: list[dict] | None = None) -> None:
        self._results = results or {}
        self._queue: asyncio.Queue[FakeMessage] = asyncio.Queue()
        for event in events or []:
            self._queue.put_nowait(FakeMessage(event))
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)
        result = self._results.get(payload.get("method", ""), {})
        await self._queue.put(FakeMessage({"id": payload["id"], "result": result}))

    def __aiter__(self) -> "FakeWebSocket":
        return self

    async def __anext__(self) -> FakeMessage:
        return await self._queue.get()


def request_event(request_id: str, url: str, device: str) -> dict:
    return {"method": "Network.requestWillBeSent",
            "params": {"requestId": request_id, "request": {"url": url, "headers": {"X-Device-Id": device}}}}


def response_events(request_id: str, url: str) -> list[dict]:
    return [{"method": "Network.responseReceived", "params": {"requestId": request_id, "response": {"url": url}}},
            {"method": "Network.loadingFinished", "params": {"requestId": request_id}}]


def test_events_become_request_and_response_in_order():
    async def go():
        ws = FakeWebSocket(events=[request_event("1", "https://x/integrity", "D"), *response_events("1", "https://x/integrity")])
        conn = browsercdp.CdpConnection(ws)
        first = await conn.next_event(1.0)
        second = await conn.next_event(1.0)
        conn.close()
        return first, second
    request, response = asyncio.run(go())
    assert request.kind == "request" and request.url == "https://x/integrity" and request.headers["X-Device-Id"] == "D"
    assert response.kind == "response" and response.url == "https://x/integrity" and response.request_id == "1"


def test_next_event_times_out_to_none():
    async def go():
        conn = browsercdp.CdpConnection(FakeWebSocket())
        event = await conn.next_event(0.01)
        conn.close()
        return event
    assert asyncio.run(go()) is None


def test_response_body_returns_the_body_string():
    async def go():
        conn = browsercdp.CdpConnection(FakeWebSocket(results={"Network.getResponseBody": {"body": "payload"}}))
        body = await conn.response_body("1")
        conn.close()
        return body
    assert asyncio.run(go()) == "payload"


def test_cookies_map_names_to_values():
    async def go():
        ws = FakeWebSocket(results={"Network.getAllCookies": {"cookies": [{"name": "auth-token", "value": "AT"}]}})
        conn = browsercdp.CdpConnection(ws)
        cookies = await conn.cookies()
        conn.close()
        return cookies, ws.sent
    cookies, sent = asyncio.run(go())
    assert cookies == {"auth-token": "AT"}
    assert sent[0]["method"] == "Network.getAllCookies"


def test_set_cookie_and_navigate_send_their_commands():
    async def go():
        ws = FakeWebSocket()
        conn = browsercdp.CdpConnection(ws)
        await conn.set_cookie("auth-token", "AT", ".twitch.tv", "/", True)
        await conn.navigate("https://www.twitch.tv/drops/inventory")
        conn.close()
        return ws.sent
    sent = asyncio.run(go())
    assert sent[0]["method"] == "Network.setCookie" and sent[0]["params"]["name"] == "auth-token"
    assert sent[1]["method"] == "Page.navigate" and sent[1]["params"]["url"].endswith("/drops/inventory")


def test_launch_without_xvfb_installed_raises(monkeypatch):
    monkeypatch.setattr(browsercdp.shutil, "which", lambda name: None)

    async def go():
        async with browsercdp.launch("/bin/chrome", LaunchOptions(headless=False, user_agent="", xvfb=True)):
            pass

    with pytest.raises(RuntimeError, match="xvfb"):
        asyncio.run(go())
