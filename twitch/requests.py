"""The mixin of `Twitch` that sends its HTTP requests, and its GQL requests through the rate limiter."""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress, asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, overload, TYPE_CHECKING

import aiohttp
from yarl import URL

from translate import _
from redact import redact
from exceptions import ExitRequest, GQLException, RequestInvalid
from gqldata import get_field, clear_error_field
from utils import ExponentialBackoff

if TYPE_CHECKING:
    from collections import abc

    from gui import GUIManager
    from settings import Settings
    from ratelimit import RateLimiter
    from constants import JsonType
    from twitchapi import ClientInfo, GQLOperation

    from .session import _AuthState


logger = logging.getLogger("TwitchDrops")
gql_logger = logging.getLogger("TwitchDrops.gql")


class RequestsMixin:
    """The methods of `Twitch` that send its HTTP and GQL requests."""

    settings: Settings
    gui: GUIManager
    _qgl_limiter: RateLimiter
    _client_type: ClientInfo
    get_session: abc.Callable[[], abc.Coroutine[Any, Any, aiohttp.ClientSession]]
    get_auth: abc.Callable[[], abc.Coroutine[Any, Any, _AuthState]]
    print: abc.Callable[[str], None]

    @asynccontextmanager
    async def request(
        self, method: str, url: URL | str, *, invalidate_after: datetime | None = None, **kwargs
    ) -> abc.AsyncIterator[aiohttp.ClientResponse]:
        session = await self.get_session()
        method = method.upper()
        if self.settings.proxy and "proxy" not in kwargs:
            kwargs["proxy"] = self.settings.proxy
        logger.debug(f"Request: ({method=}, url={redact(url)!r}, kwargs={redact(kwargs)!r})")
        session_timeout = timedelta(seconds=session.timeout.total or 0)
        backoff = ExponentialBackoff(maximum=3*60)
        for delay in backoff:
            if self.gui.close_requested:
                raise ExitRequest()
            elif (
                invalidate_after is not None
                # account for an expiration that happens during the request
                and datetime.now(timezone.utc) >= (invalidate_after - session_timeout)
            ):
                raise RequestInvalid()
            try:
                response: aiohttp.ClientResponse | None = None
                response = await self.gui.coro_unless_closed(
                    session.request(method, url, **kwargs)
                )
                assert response is not None
                logger.debug(
                    f"Response: {response.status}: {response.method} {redact(response.url)} "
                    f"headers={redact(response.headers)!r}"
                )
                if response.status < 500:
                    # pre-read the response to avoid getting errors outside of the context manager
                    raw_response = await response.read()  # noqa
                    yield response
                    return
                self.print(_("error", "site_down").format(seconds=round(delay)))
            except aiohttp.ClientConnectorCertificateError:
                # for a case where SSL verification fails
                raise
            except aiohttp.ClientHttpProxyError as exc:
                # the text of this error shows the proxy URL with its password
                exc.request_info = redact(exc.request_info)
                raise
            except (
                aiohttp.ClientConnectionError, asyncio.TimeoutError, aiohttp.ClientPayloadError
            ):
                # connection problems, retry
                if backoff.steps > 1:
                    # just so that quick retries that sometimes happen, aren't shown
                    self.print(
                        _("error", "no_connection").format(seconds=round(delay), url=str(redact(url)))
                    )
            finally:
                if response is not None:
                    response.release()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.gui.wait_until_closed(), timeout=delay)

    @overload
    async def gql_request(self, ops: GQLOperation) -> JsonType:
        ...

    @overload
    async def gql_request(self, ops: list[GQLOperation]) -> list[JsonType]:
        ...

    async def gql_request(
        self, ops: GQLOperation | list[GQLOperation]
    ) -> JsonType | list[JsonType]:
        gql_logger.debug(f"GQL Request: {ops}")
        backoff = ExponentialBackoff(maximum=60)
        # Use a flag to retry the request a single time, if a specific set of errors is encountered
        single_retry: bool = True
        for delay in backoff:
            async with self._qgl_limiter:
                auth_state = await self.get_auth()
                async with self.request(
                    "POST",
                    "https://gql.twitch.tv/gql",
                    json=ops,
                    headers=auth_state.headers(user_agent=self._client_type.USER_AGENT, gql=True),
                ) as response:
                    response_json: JsonType | list[JsonType] = await response.json()
            gql_logger.debug(f"GQL Response: {response_json}")
            orig_response = response_json
            if isinstance(response_json, list):
                response_list = response_json
            else:
                response_list = [response_json]
            force_retry: bool = False
            for response_json in response_list:
                # GQL error handling
                if "errors" in response_json:
                    for error_dict in response_json["errors"]:
                        if "message" in error_dict:
                            if (
                                single_retry
                                and error_dict["message"] in (
                                    "service error",
                                    "PersistedQueryNotFound",
                                )
                            ):
                                logger.error(
                                    f"Retrying a {error_dict['message']} for "
                                    f"{response_json['extensions']['operationName']}"
                                )
                                single_retry = False
                                if delay < 5:
                                    # overwrite the delay if too short
                                    delay = 5
                                force_retry = True
                                break
                            elif error_dict["message"] == "server error":
                                if not clear_error_field(
                                    response_json.get("data"), error_dict.get("path", [])
                                ):
                                    logger.error(
                                        "Server error with no field to clear in "
                                        f"{get_field(response_json, 'extensions', 'operationName')}"
                                    )
                                break
                            elif (
                                error_dict["message"] in (
                                    "service timeout",
                                    "request cancelled",
                                    "service unavailable",
                                    "context deadline exceeded",
                                )
                            ):
                                force_retry = True
                                break
                    else:
                        raise GQLException(response_json['errors'])
                # Other error handling
                elif "error" in response_json:
                    raise GQLException(
                        f"{response_json['error']}: {response_json['message']}"
                    )
                if force_retry:
                    break
            else:
                return orig_response
            await asyncio.sleep(delay)
        raise RuntimeError("Retry loop was broken")
