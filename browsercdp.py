"""The real `BrowserConnection`: spawn a Chromium-based browser, drive it over the Chrome DevTools Protocol, and
report the page's requests. `browser.py` holds the decisions; this module is the IO, and runs the browser under
Xvfb on Linux. `launch` starts it, yields a `CdpConnection`, and stops it and removes the profile on exit.
"""
from __future__ import annotations

import os
import shutil
import socket
import signal
import asyncio
import logging
import tempfile
import itertools
import contextlib
from typing import Any, AsyncIterator

import aiohttp

from browser import NetworkEvent, LaunchOptions, launch_args


logger = logging.getLogger("TwitchDrops")

# how long to wait for the browser to open its debugging port, in 0.2 second steps
PORT_TRIES = 150
# the wrapper that runs the browser under a throwaway virtual display on Linux
XVFB_RUN = "xvfb-run"


def free_port() -> int:
    """Return a loopback port that is free when this is called."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CdpConnection:
    """One page of the browser: it sends CDP commands and turns the page's network events into `NetworkEvent`s."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws
        self._ids = itertools.count(1)
        self._waiting: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._events: asyncio.Queue[NetworkEvent] = asyncio.Queue()
        self._urls: dict[str, str] = {}
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for message in self._ws:
            if message.type is not aiohttp.WSMsgType.TEXT:
                continue
            data = message.json()
            if "id" in data:
                if (future := self._waiting.pop(data["id"], None)) is not None and not future.done():
                    future.set_result(data)
            else:
                self._handle(data.get("method", ""), data.get("params", {}))

    def _handle(self, method: str, params: dict[str, Any]) -> None:
        if method == "Network.requestWillBeSent":
            request = params.get("request", {})
            headers = {str(key): str(value) for key, value in request.get("headers", {}).items()}
            self._events.put_nowait(NetworkEvent("request", request.get("url", ""), params.get("requestId", ""), headers))
        elif method == "Network.responseReceived":
            self._urls[params.get("requestId", "")] = params.get("response", {}).get("url", "")
        elif method == "Network.loadingFinished":
            request_id = params.get("requestId", "")
            self._events.put_nowait(NetworkEvent("response", self._urls.pop(request_id, ""), request_id, {}))

    async def _call(self, method: str, **params: Any) -> dict[str, Any]:
        number = next(self._ids)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiting[number] = future
        await self._ws.send_json({"id": number, "method": method, "params": params})
        return (await asyncio.wait_for(future, 30)).get("result", {})

    async def enable(self) -> None:
        await self._call("Network.enable")

    async def set_cookie(self, name: str, value: str, domain: str, path: str, secure: bool) -> None:
        await self._call("Network.setCookie", name=name, value=value, domain=domain, path=path, secure=secure)

    async def navigate(self, url: str) -> None:
        await self._call("Page.navigate", url=url)

    async def next_event(self, timeout: float) -> NetworkEvent | None:
        try:
            return await asyncio.wait_for(self._events.get(), timeout)
        except asyncio.TimeoutError:
            return None

    async def response_body(self, request_id: str) -> str | None:
        try:
            result = await self._call("Network.getResponseBody", requestId=request_id)
        except Exception:
            # the body may be gone, for example when the page has navigated away from it
            return None
        body = result.get("body")
        return body if isinstance(body, str) else None

    async def cookies(self) -> dict[str, str]:
        result = await self._call("Network.getAllCookies")
        return {cookie["name"]: cookie["value"] for cookie in result.get("cookies", [])}

    def close(self) -> None:
        self._reader.cancel()


async def _wait_for_port(session: aiohttp.ClientSession, base: str) -> None:
    for _ in range(PORT_TRIES):
        with contextlib.suppress(aiohttp.ClientConnectionError):
            async with session.get(f"{base}/json/version") as response:
                if response.status == 200:
                    return
        await asyncio.sleep(0.2)
    raise RuntimeError("the browser did not open its debugging port")


async def _stop(process: asyncio.subprocess.Process, profile: str) -> None:
    """Stop the browser and every process it started, then remove the throwaway profile."""
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(process.wait(), 10)
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
    shutil.rmtree(profile, ignore_errors=True)


@contextlib.asynccontextmanager
async def launch(browser_path: str, options: LaunchOptions) -> AsyncIterator[CdpConnection]:
    """Start the browser, connect to its first page, and yield a connection; stop the browser on exit."""
    prefix: list[str] = []
    if options.xvfb:
        if (xvfb := shutil.which(XVFB_RUN)) is None:
            raise RuntimeError(f"{XVFB_RUN} is not installed; the Linux refresh needs the xvfb package")
        prefix = [xvfb, "-a"]
    port = free_port()
    profile = tempfile.mkdtemp(prefix="tdm-browser-")
    args = [*prefix, browser_path, *launch_args(port, profile, headless=options.headless, user_agent=options.user_agent)]
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        start_new_session=(os.name == "posix"),
    )
    connection: CdpConnection | None = None
    base = f"http://127.0.0.1:{port}"
    try:
        async with aiohttp.ClientSession() as session:
            await _wait_for_port(session, base)
            async with session.get(f"{base}/json/list") as response:
                pages = [tab for tab in await response.json(content_type=None) if tab.get("type") == "page"]
            if not pages:
                raise RuntimeError("the browser opened no page to connect to")
            async with session.ws_connect(pages[0]["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                connection = CdpConnection(ws)
                await connection.enable()
                yield connection
    finally:
        if connection is not None:
            connection.close()
        await _stop(process, profile)
