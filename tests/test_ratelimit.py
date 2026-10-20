from __future__ import annotations

import asyncio
import bisect
import selectors

import pytest

from ratelimit import RateLimiter

CAPACITY = 5
WINDOW = 1.0
# A float sum of start times can fall short of a whole window by a rounding error
ROUNDING = 1e-9


class JumpSelector(selectors.DefaultSelector):
    def __init__(self, loop: VirtualTimeLoop) -> None:
        super().__init__()
        self._loop = loop

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            raise RuntimeError("every task waits, and no timer can wake one")
        self._loop.now += timeout
        return []


class VirtualTimeLoop(asyncio.SelectorEventLoop):
    # When every task waits, the selector moves the clock to the next timer instead of blocking,
    # so the tests take no real time
    def __init__(self) -> None:
        self.now = 0.0
        super().__init__(JumpSelector(self))

    def time(self) -> float:
        return self.now


class Requests:
    def __init__(self, loop: VirtualTimeLoop) -> None:
        self.limiter = RateLimiter(capacity=CAPACITY, window=WINDOW, clock=loop.time)
        self.starts: list[float] = []
        self.open = 0
        self.most_open = 0

    async def send(self, latency: float, cancel: list[asyncio.Task[None]] | None = None) -> None:
        async with self.limiter:
            self.starts.append(asyncio.get_running_loop().time())
            self.open += 1
            self.most_open = max(self.most_open, self.open)
            try:
                await asyncio.sleep(latency)
            finally:
                self.open -= 1
        for task in cancel or []:
            task.cancel()


@pytest.fixture
def loop():
    loop = VirtualTimeLoop()
    yield loop
    loop.close()


def most_starts_in_one_window(starts: list[float]) -> int:
    ordered = sorted(starts)
    return max(bisect.bisect_left(ordered, start + WINDOW - ROUNDING) - index for index, start in enumerate(ordered))


def test_a_burst_after_one_request_starts_at_most_capacity_in_any_window(loop):
    requests = Requests(loop)

    async def scenario():
        first = asyncio.ensure_future(requests.send(0.3))
        await asyncio.sleep(0.95)
        await asyncio.gather(first, *(requests.send(0.3) for _ in range(20)))

    loop.run_until_complete(scenario())
    assert most_starts_in_one_window(requests.starts) == CAPACITY
    expected = [0.0] + [0.95] * 4 + [1.0] + [1.95] * 4 + [2.0] + [2.95] * 4 + [3.0] + [3.95] * 4 + [4.0]
    assert requests.starts == pytest.approx(expected)


@pytest.mark.parametrize("latency", [0.0, 0.3, 0.99])
def test_a_long_burst_starts_capacity_requests_in_each_window(loop, latency):
    requests = Requests(loop)

    async def scenario():
        await asyncio.gather(*(requests.send(latency) for _ in range(100)))

    loop.run_until_complete(scenario())
    assert requests.starts == pytest.approx([float(index // CAPACITY) for index in range(100)])
    assert most_starts_in_one_window(requests.starts) == CAPACITY


@pytest.mark.parametrize(
    ("count", "latency", "expected"),
    [(7, 2.5, [0.0] * 5 + [2.5] * 2), (12, 1.5, [0.0] * 5 + [1.5] * 5 + [3.0] * 2)],
)
def test_requests_longer_than_the_window_start_when_open_ones_end(loop, count, latency, expected):
    requests = Requests(loop)

    async def scenario():
        await asyncio.gather(*(requests.send(latency) for _ in range(count)))

    loop.run_until_complete(scenario())
    assert requests.starts == pytest.approx(expected)
    assert requests.most_open == CAPACITY


def test_a_request_that_raises_leaves_its_slot(loop):
    requests = Requests(loop)

    async def failing() -> None:
        async with requests.limiter:
            raise ConnectionError

    async def scenario():
        for _ in range(CAPACITY):
            with pytest.raises(ConnectionError):
                await failing()
        await requests.send(0.0)

    loop.run_until_complete(scenario())
    assert requests.starts == pytest.approx([WINDOW])


def test_waiters_cancelled_during_the_wait_for_the_window_do_not_start(loop):
    requests = Requests(loop)

    async def scenario():
        await asyncio.gather(*(requests.send(0.0) for _ in range(CAPACITY)))
        cancelled = [asyncio.ensure_future(requests.send(0.0)) for _ in range(3)]
        last = asyncio.ensure_future(requests.send(0.0))
        await asyncio.sleep(0.5)
        for task in cancelled:
            task.cancel()
        await asyncio.gather(*cancelled, last, return_exceptions=True)
        assert [task.cancelled() for task in cancelled] == [True] * 3

    loop.run_until_complete(scenario())
    assert requests.starts == pytest.approx([0.0] * CAPACITY + [WINDOW])


def test_waiters_cancelled_as_a_slot_opens_do_not_hold_up_the_next_request(loop):
    requests = Requests(loop)

    async def scenario():
        cancelled: list[asyncio.Task[None]] = []
        # `ending` cancels the waiters as it leaves, after its exit woke the first one and before that one runs
        ending = asyncio.ensure_future(requests.send(1.5, cancel=cancelled))
        held = [asyncio.ensure_future(requests.send(60.0)) for _ in range(CAPACITY - 1)]
        await asyncio.sleep(0)
        cancelled.extend(asyncio.ensure_future(requests.send(0.0)) for _ in range(CAPACITY))
        last = asyncio.ensure_future(requests.send(0.0))
        await asyncio.gather(ending, last)
        for task in held:
            task.cancel()
        await asyncio.gather(*held, *cancelled, return_exceptions=True)

    loop.run_until_complete(scenario())
    assert requests.starts == pytest.approx([0.0] * CAPACITY + [1.5])


@pytest.mark.parametrize("capacity", [0, -1])
def test_a_capacity_below_one_raises(capacity):
    with pytest.raises(ValueError, match="at least 1"):
        RateLimiter(capacity=capacity, window=WINDOW)
