"""Small helpers for lists, tracebacks, Twitch times and random IDs."""
from __future__ import annotations

import random
import string
import traceback
from datetime import datetime, timezone
from collections import abc
from typing import Any, TypeVar


_T = TypeVar("_T")  # type


def chunk(to_chunk: abc.Iterable[_T], chunk_length: int) -> abc.Generator[list[_T], None, None]:
    list_to_chunk = list(to_chunk)
    for i in range(0, len(list_to_chunk), chunk_length):
        yield list_to_chunk[i:i + chunk_length]


def format_traceback(exc: BaseException, **kwargs: Any) -> str:
    """
    Like `traceback.print_exc` but returns a string. Uses the passed-in exception.
    Any additional `**kwargs` are passed to the underlaying `traceback.format_exception`.
    """
    return ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__, **kwargs))


def timestamp(string: str) -> datetime:
    try:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.strptime(string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def isonow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", 'Z')


CHARS_ASCII = string.ascii_letters + string.digits
CHARS_HEX_LOWER = string.digits + "abcdef"


def create_nonce(chars: str, length: int) -> str:
    return ''.join(random.choices(chars, k=length))
