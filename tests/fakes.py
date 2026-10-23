"""A fake `Twitch` object and window, and the GQL data they return, for the tests of the modules that need Twitch."""
from __future__ import annotations

import asyncio
import copy
import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from types import SimpleNamespace
from typing import Any, Union

from yarl import URL

from constants import JsonType, State
from twitchapi import GQL_QUERIES
from settings import default_settings

GQLAnswer = Callable[[JsonType], Union[JsonType, Awaitable[JsonType]]]
HTTPAnswer = Callable[[str, URL], Union["FakeResponse", Awaitable["FakeResponse"]]]

QUERY_NAMES = {query["operationName"]: key for key, query in GQL_QUERIES.items()}
GAME = {"id": "1", "name": "Game", "boxArtURL": "https://example.invalid/1-285x380.jpg"}
START = "2020-01-01T00:00:00Z"
END = "2099-01-01T00:00:00Z"
NO_CAMPAIGNS = {"data": {"currentUser": {"dropCampaigns": []}}}
CLAIMED = {"data": {"claimDropRewards": {"status": "ELIGIBLE_FOR_ALL"}}}
TOKEN = {"data": {"streamPlaybackAccessToken": {"value": "value", "signature": "signature"}}}
PLAYLIST = "https://video-weaver.example.invalid/v1/playlist/1.m3u8"
USHER_LIST = f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n{PLAYLIST}\n"


class FakeResponse:
    """An HTTP response with a status and a text body."""

    def __init__(self, status: int = 200, body: str = "") -> None:
        self.status = status
        self.body = body
        self.method = "GET"
        self.url = URL()
        self.headers: dict[str, str] = {}

    async def text(self, encoding: str | None = None) -> str:
        return self.body

    async def json(self) -> Any:
        return json.loads(self.body)

    async def read(self) -> bytes:
        return self.body.encode()

    def release(self) -> None:
        pass


class FakeChannelList:
    """The channel list of the window, as the status text of each row by the channel's `iid`."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}
        self.watching: Any = None

    def display(self, channel: Any, *, add: bool = False) -> None:
        if add or channel.iid in self.rows:
            if channel.online:
                self.rows[channel.iid] = "ONLINE"
            else:
                self.rows[channel.iid] = "PENDING" if channel.pending_online else "OFFLINE"

    def remove(self, channel: Any) -> None:
        del self.rows[channel.iid]

    def clear(self) -> None:
        self.rows.clear()

    def get_iids(self) -> set[str]:
        return set(self.rows)

    def get_selection(self) -> None:
        return None

    def set_watching(self, channel: Any) -> None:
        self.watching = channel

    def clear_watching(self) -> None:
        self.watching = None


class FakeGUI:
    """The parts of `GUIManager` that `Twitch`, channels and drops call, with the Output box and tray recorded.

    The window is never closed, and `progress` reports that no drop progress came for a minute.
    """

    def __init__(self) -> None:
        self.channels = FakeChannelList()
        self.printed: list[str] = []
        self.notified: list[str] = []
        self.close_requested = False
        self._closed = asyncio.Event()
        self.tray = SimpleNamespace(notify=lambda text, title: self.notified.append(text), change_icon=ignore)
        self.inv = SimpleNamespace(update_drop=ignore, clear=ignore, add_campaign=self._add_campaign)
        self.status = SimpleNamespace(update=ignore)
        self.progress = SimpleNamespace(stop_timer=ignore, minute_almost_done=lambda: True)
        self.settings = SimpleNamespace(set_wanted_games=ignore, set_scanning=ignore, set_detected=ignore)
        self.help = SimpleNamespace(_invalidate_button=SimpleNamespace(config=ignore))
        self.websockets = SimpleNamespace(update=ignore, remove=ignore)

    async def _add_campaign(self, campaign: Any) -> None:
        pass

    def start(self) -> None:
        pass

    def set_games(self, games: set[Any]) -> None:
        pass

    def save(self, *, force: bool = False) -> None:
        pass

    def print(self, message: str) -> None:
        self.printed.append(message)

    def display_drop(self, drop: Any, *, countdown: bool = True, subone: bool = False) -> None:
        pass

    def clear_drop(self) -> None:
        pass

    async def coro_unless_closed(self, coro: Awaitable[Any]) -> Any:
        return await coro

    async def wait_until_closed(self) -> None:
        await self._closed.wait()


def ignore(*args: Any, **kwargs: Any) -> None:
    """Do nothing, in place of a window method whose effect no test reads."""


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


def gql_answers(**answers: JsonType | GQLAnswer) -> GQLAnswer:
    """Return a GQL answer that answers an operation with the value of its key in `GQL_QUERIES`, or calls it."""

    def answer(op: JsonType) -> JsonType | Awaitable[JsonType]:
        key = QUERY_NAMES[op["operationName"]]
        if key not in answers:
            raise AssertionError(f"unexpected GQL request: {key}")
        found = answers[key]
        return found(op) if callable(found) else found

    return answer


class FakeTwitch:
    """The attributes of `Twitch` that channels, drops and the window use, with every call recorded.

    `gql` returns the response to one GQL operation, and `http` the response to one other request.
    """

    def __init__(self, gql: GQLAnswer = no_gql, http: HTTPAnswer = no_http) -> None:
        self._gql = gql
        self._http = http
        self.settings = SimpleNamespace(
            **copy.deepcopy(default_settings), dump=False, tray=False, save=ignore, alter=ignore
        )
        self.gui = FakeGUI()
        self._campaigns: dict[str, Any] = {}
        self.gql_sent: list[str] = []
        self.http_sent: list[str] = []
        self.states: list[State] = []
        self.updates: list[tuple[bool, bool]] = []

    @property
    def printed(self) -> list[str]:
        return self.gui.printed

    async def gql_request(self, ops: JsonType | list[JsonType]) -> JsonType | list[JsonType]:
        if isinstance(ops, list):
            return [await self._answer(op) for op in ops]
        return await self._answer(ops)

    async def _answer(self, op: JsonType) -> JsonType:
        self.gql_sent.append(QUERY_NAMES[op["operationName"]])
        answer = self._gql(op)
        return await answer if inspect.isawaitable(answer) else answer

    async def answer_http(self, method: str, url: URL) -> FakeResponse:
        """Record a request that is not GQL and return the response that `http` gives to it."""
        self.http_sent.append(f"{method} {url.host}")
        response = self._http(method, url)
        return await response if inspect.isawaitable(response) else response

    @asynccontextmanager
    async def request(self, method: str, url: URL | str, **kwargs: Any) -> AsyncIterator[FakeResponse]:
        yield await self.answer_http(method, URL(str(url)))

    def on_channel_update(self, channel: Any, before: Any, after: Any) -> None:
        self.updates.append((before is not None, after is not None))
        channel.display()

    def print(self, message: str) -> None:
        self.gui.print(message)

    def change_state(self, state: State) -> None:
        self.states.append(state)

    def state_change(self, state: State) -> Callable[[], None]:
        return partial(self.change_state, state)


def stream_user(channel_id: int, *, online: bool) -> JsonType:
    """Return the `user` of a `GetStreamInfo` response for the channel with this ID."""
    return {
        "id": str(channel_id),
        "displayName": f"C{channel_id}",
        "stream": {"id": 100 + channel_id, "viewersCount": 5} if online else None,
        "broadcastSettings": {"game": {"id": GAME["id"], "name": GAME["name"]}, "title": "title"},
    }


def directory(*channels: tuple[int, int], game: JsonType = GAME) -> JsonType:
    """Return a `GameDirectory` response that lists each channel, given as its ID and viewers, streaming game."""
    return {"data": {"game": {"streams": {"edges": [
        {"node": {
            "id": str(100 + channel_id),
            "broadcaster": {"id": str(channel_id), "login": f"c{channel_id}", "displayName": f"C{channel_id}"},
            "game": {"id": game["id"], "name": game["name"]},
            "viewersCount": viewers,
            "title": "title",
        }}
        for channel_id, viewers in channels
    ]}}}}


def inventory(campaigns: list[JsonType]) -> JsonType:
    """Return an `Inventory` response with these campaigns in progress and no claimed drop."""
    return {"data": {"currentUser": {"inventory": {"dropCampaignsInProgress": campaigns, "gameEventDrops": []}}}}


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


def campaign_data(drops: list[JsonType], *, game: JsonType = GAME) -> JsonType:
    """Return an active campaign of a `DropCampaignDetails` response, with no ACL and a linked account."""
    return {
        "id": "c1",
        "name": "Campaign",
        "game": game,
        "self": {"isAccountConnected": True},
        "accountLinkURL": "https://example.invalid/link",
        "startAt": START,
        "endAt": END,
        "status": "ACTIVE",
        "allow": {"channels": None, "isEnabled": True},
        "timeBasedDrops": drops,
    }
