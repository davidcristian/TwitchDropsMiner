"""The mixin of `Websocket` that receives, reads and sends the messages of its connection."""
from __future__ import annotations

import json
import asyncio
import logging
from contextlib import suppress
from typing import TYPE_CHECKING

import aiohttp

from redact import redact
from exceptions import WebsocketClosed
from utils import (
    CHARS_ASCII,
    start_task,
    create_nonce,
    json_minify,
    format_traceback,
)

if TYPE_CHECKING:
    from collections import abc

    from utils import AwaitableValue
    from constants import JsonType, WebsocketTopic


WSMsgType = aiohttp.WSMsgType
ws_logger = logging.getLogger("TwitchDrops.websocket")


class MessagesMixin:
    """The methods of `Websocket` that receive, read and send its messages."""

    _idx: int
    _ws: AwaitableValue[aiohttp.ClientWebSocketResponse]
    _next_ping: float
    _max_pong: float
    topics: dict[str, WebsocketTopic]
    request_reconnect: abc.Callable[[], None]

    async def _gather_recv(self, messages: list[JsonType], timeout: float = 0.5):
        """
        Gather incoming messages over the timeout specified.
        Note that there's no return value - this modifies `messages` in-place.
        """
        ws = self._ws.get_with_default(None)
        assert ws is not None
        while True:
            try:
                raw_message: aiohttp.WSMessage = await ws.receive(timeout=timeout)
            except aiohttp.ClientConnectionError:
                raise WebsocketClosed(received=False)
            if raw_message.type is WSMsgType.TEXT:
                try:
                    message: JsonType = json.loads(raw_message.data)
                except ValueError as exc:
                    ws_logger.warning(f"Websocket[{self._idx}] skipped a message that is not JSON: {exc}")
                    continue
                # logged once parsed, because redact reads the keys of a dict, not of JSON text
                ws_logger.debug(f"Websocket[{self._idx}] received: {redact(message)}")
                messages.append(message)
                continue
            ws_logger.debug(f"Websocket[{self._idx}] received: {raw_message}")
            if raw_message.type is WSMsgType.CLOSE:
                raise WebsocketClosed(received=True)
            elif raw_message.type is WSMsgType.CLOSED:
                raise WebsocketClosed(received=False)
            elif raw_message.type is WSMsgType.CLOSING:
                pass  # skip these
            elif raw_message.type is WSMsgType.ERROR:
                ws_logger.error(
                    f"Websocket[{self._idx}] error: {format_traceback(raw_message.data)}"
                )
                raise WebsocketClosed()
            else:
                ws_logger.error(f"Websocket[{self._idx}] error: Unknown message: {raw_message}")

    def _handle_message(self, message):
        # request the assigned topic to process the response
        topic = self.topics.get(message["data"]["topic"])
        if topic is not None:
            # use a task to not block the websocket
            start_task(topic(json.loads(message["data"]["message"])))

    async def _handle_recv(self):
        """
        Handle receiving messages from the websocket.
        """
        # listen over 0.5s for incoming messages
        messages: list[JsonType] = []
        with suppress(asyncio.TimeoutError):
            await self._gather_recv(messages, timeout=0.5)
        # process them
        for message in messages:
            try:
                msg_type = message["type"]
                if msg_type == "MESSAGE":
                    self._handle_message(message)
                elif msg_type == "PONG":
                    # move the timestamp to something much later
                    self._max_pong = self._next_ping
                elif msg_type == "RESPONSE":
                    # no special handling for these (for now)
                    pass
                elif msg_type == "RECONNECT":
                    # We've received a reconnect request
                    ws_logger.warning(f"Websocket[{self._idx}] requested reconnect.")
                    self.request_reconnect()
                else:
                    ws_logger.warning(f"Websocket[{self._idx}] received unknown payload: {redact(message)}")
            except (KeyError, TypeError, ValueError) as exc:
                ws_logger.warning(
                    f"Websocket[{self._idx}] skipped a malformed message ({exc!r}): {redact(message)}"
                )

    async def send(self, message: JsonType):
        ws = self._ws.get_with_default(None)
        assert ws is not None
        if message["type"] != "PING":
            message["nonce"] = create_nonce(CHARS_ASCII, 30)
        try:
            await ws.send_json(message, dumps=json_minify)
        except aiohttp.ClientConnectionError:
            raise WebsocketClosed(received=False)
        ws_logger.debug(f"Websocket[{self._idx}] sent: {redact(message)}")
