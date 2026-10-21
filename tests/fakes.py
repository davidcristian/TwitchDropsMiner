"""A fake `Twitch` object and the GQL data it returns, for the tests of the modules that need Twitch."""
from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, Union

from yarl import URL

from constants import GQL_QUERIES, JsonType, State

GQLAnswer = Callable[[JsonType], Union[JsonType, Awaitable[JsonType]]]
HTTPAnswer = Callable[[str, URL], Union["FakeResponse", Awaitable["FakeResponse"]]]

QUERY_NAMES = {query["operationName"]: key for key, query in GQL_QUERIES.items()}
GAME = {"id": "1", "name": "Game", "boxArtURL": "https://example.invalid/1-285x380.jpg"}
START = "2020-01-01T00:00:00Z"
END = "2099-01-01T00:00:00Z"


class FakeResponse:
    """An HTTP response with a status and a text body."""

    def __init__(self, status: int = 200, body: str = "") -> None:
        self.status = status
        self.body = body

    async def text(self, encoding: str | None = None) -> str:
        return self.body


class FakeChannelList:
    """The channel list of the window, as the status text of each row by the channel's `iid`."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    def display(self, channel: Any, *, add: bool = False) -> None:
        if add or channel.iid in self.rows:
            if channel.online:
                self.rows[channel.iid] = "ONLINE"
            else:
                self.rows[channel.iid] = "PENDING" if channel.pending_online else "OFFLINE"

    def remove(self, channel: Any) -> None:
        del self.rows[channel.iid]


class FakeGUI:
    """The parts of `GUIManager` that channels and drops call, with the tray notifications recorded."""

    def __init__(self) -> None:
        self.channels = FakeChannelList()
        self.notified: list[str] = []
        self.tray = SimpleNamespace(notify=lambda text, title: self.notified.append(text))
        self.inv = SimpleNamespace(update_drop=lambda drop: None)

    def display_drop(self, drop: Any, *, countdown: bool = True, subone: bool = False) -> None:
        pass


class HeldAnswer:
    """A GQL answer that returns `response` only after the test sets `release`."""

    def __init__(self, response: JsonType) -> None:
        self.response = response
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, op: JsonType) -> JsonType:
        self.started.set()
        await self.release.wait()
        return self.response


async def settle() -> None:
    """Wait until every other task has ended."""
    others = asyncio.all_tasks() - {asyncio.current_task()}
    await asyncio.gather(*others, return_exceptions=True)


def no_gql(op: JsonType) -> JsonType:
    raise AssertionError(f"unexpected GQL request: {op['operationName']}")


def no_http(method: str, url: URL) -> FakeResponse:
    raise AssertionError(f"unexpected request: {method} {url}")


class FakeTwitch:
    """The attributes of `Twitch` that `Channel`, `Stream` and the drop classes use, with every call recorded.

    `gql` returns the response to one GQL operation, and `http` the response to one other request.
    """

    def __init__(self, gql: GQLAnswer = no_gql, http: HTTPAnswer = no_http) -> None:
        self._gql = gql
        self._http = http
        self.settings = SimpleNamespace(available_drops_check=False, enable_badges_emotes=False)
        self.gui = FakeGUI()
        self._campaigns: dict[str, Any] = {}
        self.gql_sent: list[str] = []
        self.http_sent: list[str] = []
        self.printed: list[str] = []
        self.states: list[State] = []
        self.updates: list[tuple[bool, bool]] = []

    async def gql_request(self, ops: JsonType | list[JsonType]) -> JsonType | list[JsonType]:
        if isinstance(ops, list):
            return [await self._answer(op) for op in ops]
        return await self._answer(ops)

    async def _answer(self, op: JsonType) -> JsonType:
        self.gql_sent.append(QUERY_NAMES[op["operationName"]])
        answer = self._gql(op)
        return await answer if inspect.isawaitable(answer) else answer

    @asynccontextmanager
    async def request(self, method: str, url: URL | str, **kwargs: Any) -> AsyncIterator[FakeResponse]:
        url = URL(str(url))
        self.http_sent.append(f"{method} {url.host}")
        response = self._http(method, url)
        yield await response if inspect.isawaitable(response) else response

    def on_channel_update(self, channel: Any, before: Any, after: Any) -> None:
        self.updates.append((before is not None, after is not None))
        channel.display()

    def print(self, message: str) -> None:
        self.printed.append(message)

    def change_state(self, state: State) -> None:
        self.states.append(state)


def stream_user(channel_id: int, *, online: bool) -> JsonType:
    """Return the `user` of a `GetStreamInfo` response for the channel with this ID."""
    return {
        "id": str(channel_id),
        "displayName": f"C{channel_id}",
        "stream": {"id": 100 + channel_id, "viewersCount": 5} if online else None,
        "broadcastSettings": {"game": {"id": GAME["id"], "name": GAME["name"]}, "title": "title"},
    }


def drop_data(drop_id: str, *, minutes: int = 120, watched: int = 0, claim_id: str | None = None) -> JsonType:
    """Return a drop of a `DropCampaignDetails` response, with its `self` data."""
    return {
        "id": drop_id,
        "name": drop_id,
        "benefitEdges": [{"benefit": {
            "id": f"b-{drop_id}", "name": f"Reward {drop_id}", "distributionType": "DIRECT_ENTITLEMENT",
            "imageAssetURL": "https://example.invalid/b.png",
        }}],
        "startAt": START,
        "endAt": END,
        "preconditionDrops": None,
        "requiredMinutesWatched": minutes,
        "self": {"dropInstanceID": claim_id, "isClaimed": False, "currentMinutesWatched": watched},
    }


def campaign_data(drops: list[JsonType]) -> JsonType:
    """Return an active campaign of a `DropCampaignDetails` response, with no ACL and a linked account."""
    return {
        "id": "c1",
        "name": "Campaign",
        "game": GAME,
        "self": {"isAccountConnected": True},
        "accountLinkURL": "https://example.invalid/link",
        "startAt": START,
        "endAt": END,
        "status": "ACTIVE",
        "allow": {"channels": None, "isEnabled": True},
        "timeBasedDrops": drops,
    }
