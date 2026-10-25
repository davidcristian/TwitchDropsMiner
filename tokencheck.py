"""Read the response to the token check, `GET https://id.twitch.tv/oauth2/validate`, and find the token's client."""
from __future__ import annotations

from collections import abc
from enum import Enum
from typing import Any, NamedTuple

from twitchapi import ClientInfo, ClientType


# every entry of `ClientType`, in the order of its class body
CLIENT_TYPES: tuple[ClientInfo, ...] = tuple(
    value for value in vars(ClientType).values() if isinstance(value, ClientInfo)
)


class TokenResult(Enum):
    """What a token check says about the token."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    UNKNOWN_CLIENT = "unknown client"
    FAILED = "failed"


class TokenCheck(NamedTuple):
    """The result of a token check, with the client and the user ID of an accepted token."""

    result: TokenResult
    client: ClientInfo | None = None
    user_id: int = 0


def entered_token(text: str) -> str:
    """Return the text entered as a token without whitespace and control characters, which no token has."""
    # aiohttp raises ValueError for a header value with a control character, such as a newline
    return "".join(char for char in text if char.isprintable() and not char.isspace())


def client_of(client_id: Any, clients: abc.Iterable[ClientInfo] = CLIENT_TYPES) -> ClientInfo | None:
    """Return the client of clients whose `CLIENT_ID` is client_id, or None when none has it."""
    return next((client for client in clients if client.CLIENT_ID == client_id), None)


def check_token(status: int, body: Any, clients: abc.Iterable[ClientInfo] = CLIENT_TYPES) -> TokenCheck:
    """Return what the token check response with status and body says about the token.

    body is the JSON value of a 200 response, and None for another status.
    """
    if status == 401:
        return TokenCheck(TokenResult.REJECTED)
    if status != 200 or not isinstance(body, dict):
        return TokenCheck(TokenResult.FAILED)
    if (client := client_of(body.get("client_id"), clients)) is None:
        return TokenCheck(TokenResult.UNKNOWN_CLIENT)
    user_id = body.get("user_id")
    if isinstance(user_id, bool) or not isinstance(user_id, (str, int)) or not str(user_id).isdecimal():
        return TokenCheck(TokenResult.FAILED)
    return TokenCheck(TokenResult.ACCEPTED, client, int(user_id))
