"""Hide the login token and other secrets in values that are about to be logged."""
from __future__ import annotations

from collections import abc
from typing import Any
from urllib.parse import quote, unquote_plus

from yarl import URL


HIDDEN = "<hidden>"
# Header names, form fields, JSON keys and URL query parameters whose value is a secret, compared lowercase.
# "token" is the revoke request's field and the usher URL's playback token, which identifies the user.
# "device_code" lets anyone finish a login in progress. "auth-token" is the cookie that holds the login token.
SECRET_KEYS = frozenset({
    "access_token",
    "auth-token",
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
    if isinstance(value, URL):
        return _redact_url(value)
    return value


def _is_request_info(value: Any) -> bool:
    """Whether value is aiohttp's `RequestInfo`, found by its name and fields so that no aiohttp import is needed."""
    return type(value).__name__ == "RequestInfo" and all(
        hasattr(value, field) for field in ("url", "method", "headers", "real_url")
    )


def _redact_url(url: URL) -> URL:
    """Return url with HIDDEN as its password and as the value of each query parameter named in SECRET_KEYS."""
    query = "&".join(_hide_query_value(parameter) for parameter in url.raw_query_string.split("&"))
    if query != url.raw_query_string:
        # built from the encoded text, because with_query encodes the other values again in another form
        url = URL.build(
            scheme=url.scheme,
            authority=url.raw_authority,
            path=url.raw_path,
            query_string=query,
            fragment=url.raw_fragment,
            encoded=True,
        )
    if url.password is not None:
        # a proxy URL can hold the proxy's password
        url = url.with_password(HIDDEN)
    return url


def _hide_query_value(parameter: str) -> str:
    """Return one `name=value` part of an encoded query, with HIDDEN as the value when the name is a secret key."""
    # split and decoded the way yarl reads a query, so the name matches the parameter that is sent
    name = parameter.partition("=")[0]
    if unquote_plus(name).lower() in SECRET_KEYS:
        return f"{name}={quote(HIDDEN)}"
    return parameter
