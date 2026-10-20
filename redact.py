"""Hide the login token and other secrets in values that are about to be logged."""
from __future__ import annotations

from collections import abc
from typing import Any

from yarl import URL


HIDDEN = "<hidden>"
# Header names, form fields and JSON keys whose value gives access to the account, compared lowercase.
# "token" is the revoke request's field, "device_code" lets anyone finish a login in progress.
SECRET_KEYS = frozenset({
    "access_token",
    "auth_token",
    "authorization",
    "cookie",
    "device_code",
    "password",
    "proxy-authorization",
    "refresh_token",
    "set-cookie",
    "token",
})


def redact(value: Any) -> Any:
    """Return a copy of value with every secret replaced by HIDDEN, at any depth."""
    if isinstance(value, abc.Mapping):
        return {
            key: HIDDEN if str(key).lower() in SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if _is_request_info(value):
        # checked before tuple, because RequestInfo is a NamedTuple in aiohttp 3.14
        return type(value)(
            redact(value.url), value.method, redact(value.headers), redact(value.real_url)
        )
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, URL) and value.password is not None:
        # a proxy URL can hold the proxy's password
        return value.with_password(HIDDEN)
    return value


def _is_request_info(value: Any) -> bool:
    """Whether value is aiohttp's `RequestInfo`, found by its name and fields so that no aiohttp import is needed."""
    return type(value).__name__ == "RequestInfo" and all(
        hasattr(value, field) for field in ("url", "method", "headers", "real_url")
    )
