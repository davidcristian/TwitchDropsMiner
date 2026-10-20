"""The wait before each reconnect of a PubSub websocket."""
from __future__ import annotations

from collections import abc
from typing import Protocol


class Backoff(Protocol):
    """An iterator of delays in seconds that `reset()` starts again from the first delay."""

    def __next__(self) -> float: ...

    def reset(self) -> None: ...


class ReconnectDelay:
    """Return the seconds a websocket waits before it connects again."""

    def __init__(self, backoff: Backoff, min_uptime: float, clock: abc.Callable[[], float]) -> None:
        self._backoff = backoff
        self._min_uptime = min_uptime
        self._clock = clock
        self._opened_at: float | None = None

    def opened(self) -> None:
        """Record that a connection opened now."""
        self._opened_at = self._clock()

    def next_delay(self) -> float:
        """Return the wait after a connection closed or failed to open.

        A connection open for at least `min_uptime` seconds resets the backoff and returns 0.
        """
        opened_at, self._opened_at = self._opened_at, None
        if opened_at is not None and self._clock() - opened_at >= self._min_uptime:
            self._backoff.reset()
            return 0.0
        return next(self._backoff)
