"""Running coroutines as tasks, and a value that coroutines can wait for."""
from __future__ import annotations

import asyncio
import logging
from functools import wraps
from collections import abc
from typing import Any, Generic, TypeVar, ParamSpec

from exceptions import ExitRequest, ReloadRequest


_T = TypeVar("_T")  # type
_D = TypeVar("_D")  # default
_P = ParamSpec("_P")  # params
logger = logging.getLogger("TwitchDrops")


def task_wrapper(
    afunc: abc.Callable[_P, abc.Coroutine[Any, Any, _T]] | None = None, *, critical: bool = False
):
    def decorator(
        afunc: abc.Callable[_P, abc.Coroutine[Any, Any, _T]]
    ) -> abc.Callable[_P, abc.Coroutine[Any, Any, _T]]:
        @wraps(afunc)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs):
            try:
                await afunc(*args, **kwargs)
            except (ExitRequest, ReloadRequest):
                pass
            except Exception as exc:
                logger.exception(f"Exception in {afunc.__name__} task")
                if critical:
                    # The run cannot go on without a critical task, so Twitch.task_failed has _run raise the error as
                    # a fatal error. The task ends without it, which Websocket.stop would raise again as it awaits it.
                    from twitch import Twitch  # cyclic import
                    probe = args and args[0] or None  # extract from 'self' arg
                    if not isinstance(probe, Twitch):
                        probe = getattr(probe, "_twitch", None)  # extract from '_twitch' attr
                    if isinstance(probe, Twitch):
                        probe.task_failed(exc)
                        return
                raise  # raise up to the wrapping task
        return wrapper
    if afunc is None:
        return decorator
    return decorator(afunc)


# The event loop keeps only a weak reference to a task, so a task that nothing else references
# can be collected before it ends.
_running_tasks: set[asyncio.Task[Any]] = set()


def start_task(coro: abc.Coroutine[Any, Any, _T]) -> asyncio.Task[_T]:
    """Start a task that runs coro, and keep a reference to it until it ends."""
    task = asyncio.create_task(coro)
    _running_tasks.add(task)
    task.add_done_callback(_running_tasks.discard)
    return task


class AwaitableValue(Generic[_T]):
    def __init__(self):
        self._value: _T
        self._event = asyncio.Event()

    def has_value(self) -> bool:
        return self._event.is_set()

    def get_with_default(self, default: _D) -> _T | _D:
        if self._event.is_set():
            return self._value
        return default

    async def get(self) -> _T:
        await self._event.wait()
        return self._value

    def set(self, value: _T) -> None:
        self._value = value
        self._event.set()

    def clear(self) -> None:
        self._event.clear()
