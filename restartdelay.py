"""The wait before the run starts again after a fatal error."""
from __future__ import annotations

from collections import abc

# The longest choice of the restart_delay setting. Restarts this far apart reload no more often than the hourly
# reload of a run that works.
LONGEST = 60
# A restart after a run this long follows an hour of running, so it adds at most one reload an hour
RESET_AFTER = 3600.0


class RestartDelay:
    """Return the minutes before each restart, doubled after each run that ended within an hour of its start.

    `clock` returns the current time in seconds. It is read only in `started` and `next_minutes`.
    """

    def __init__(self, clock: abc.Callable[[], float]) -> None:
        self._clock = clock
        self._started_at: float | None = None
        # the last wait in minutes, 0 before the first
        self._wait = 0

    def started(self) -> None:
        """Record that a run started now."""
        self._started_at = self._clock()

    def next_minutes(self, minutes: int) -> int:
        """Return the wait after a run ended on a fatal error, where minutes is the `restart_delay` setting."""
        started_at = self._started_at
        if started_at is not None and self._clock() - started_at < RESET_AFTER:
            self._wait = max(minutes, min(2 * self._wait, LONGEST))
        else:
            self._wait = minutes
        return self._wait
