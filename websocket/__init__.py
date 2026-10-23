"""The websocket connections to Twitch PubSub and the pool that spreads the topics over them."""
from __future__ import annotations

from .pool import WebsocketPool
from .connection import Websocket

__all__ = ["Websocket", "WebsocketPool"]
