"""Every path of a GQL response, and the response with a server error that sets the value at one path to null."""
from __future__ import annotations

import copy
from collections.abc import Iterator
from typing import Any

from constants import JsonType

NullPath = tuple[str | int, ...]


def _paths(value: Any, prefix: NullPath) -> Iterator[NullPath]:
    if isinstance(value, dict):
        items: Iterator[tuple[str | int, Any]] = iter(value.items())
    elif isinstance(value, list):
        items = enumerate(value)
    else:
        return
    for key, item in items:
        yield (*prefix, key)
        yield from _paths(item, (*prefix, key))


def null_paths(response: JsonType) -> list[NullPath]:
    """Return the path of each dict value and list item of the response's `data`, at every depth, `data` included."""
    return [("data",), *_paths(response["data"], ("data",))]


def with_null(response: JsonType, path: NullPath) -> JsonType:
    """Return the response with a server error at path, which `Twitch.gql_request` sets to null.

    A server error cannot name `data`, so for that path the response has a null `data` and an error without a path.
    """
    if path == ("data",):
        return {"data": None, "errors": [{"message": "server error", "path": []}]}
    return {**copy.deepcopy(response), "errors": [{"message": "server error", "path": list(path[1:])}]}


def path_id(path: NullPath) -> str:
    """Return the test ID of a path: its keys joined by dots."""
    return ".".join(map(str, path))
