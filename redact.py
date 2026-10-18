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
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, URL) and value.password is not None:
        # a proxy URL can hold the proxy's password
        return value.with_password(HIDDEN)
    return value
