"""The limit on how many requests start in a span of time and how many are open at once."""
from __future__ import annotations

import asyncio
from collections import abc, deque
from time import monotonic
from types import TracebackType


class RateLimiter:
    """Let at most `capacity` entries start in any `window` seconds, and at most `capacity` be inside at once.

    `clock` returns the current time in seconds on the clock of the running event loop.
    """

    def __init__(self, *, capacity: int, window: float, clock: abc.Callable[[], float] = monotonic) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1, not {capacity}")
        self._capacity = capacity
        self._window = window
        self._clock = clock
        self._starts: deque[float] = deque(maxlen=capacity)
        self._open = 0
        # The waiters check the limits one at a time, in the order they arrived
        self._turn = asyncio.Lock()
        self._exited = asyncio.Event()

    def _wait_time(self) -> float:
        """Return the seconds until the oldest of the last `capacity` starts is `window` seconds old."""
        if len(self._starts) < self._capacity:
            return 0.0
        return self._starts[0] + self._window - self._clock()

    async def __aenter__(self) -> None:
        async with self._turn:
            while self._open >= self._capacity:
                self._exited.clear()
                await self._exited.wait()
            while (delay := self._wait_time()) > 0:
                await asyncio.sleep(delay)
            self._starts.append(self._clock())
            self._open += 1

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._open -= 1
        self._exited.set()
