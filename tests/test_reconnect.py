import pytest

from reconnect import ReconnectDelay

MIN_UPTIME = 60.0
MAXIMUM = 180.0


class DoublingBackoff:
    def __init__(self) -> None:
        self.steps = 0

    def __next__(self) -> float:
        delay = min(2.0**self.steps, MAXIMUM)
        self.steps += 1
        return delay

    def reset(self) -> None:
        self.steps = 0


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def delays(clock):
    return ReconnectDelay(DoublingBackoff(), MIN_UPTIME, clock)


def connect_times(delays, clock, span, uptime):
    times = []
    # The count limit ends the loop when every wait is 0
    while clock.now < span and len(times) < 1000:
        times.append(clock.now)
        delays.opened()
        clock.now += uptime
        clock.now += delays.next_delay()
    return times


def test_connections_that_close_at_once_are_spaced_by_the_backoff(delays, clock):
    times = connect_times(delays, clock, span=600, uptime=0)
    assert times == [0, 1, 3, 7, 15, 31, 63, 127, 255, 435]


def test_connections_that_close_at_once_connect_once_per_maximum_delay(delays, clock):
    times = connect_times(delays, clock, span=3600, uptime=0)
    assert len(times) == 27
    assert {later - earlier for earlier, later in zip(times[8:], times[9:])} == {MAXIMUM}


def test_connections_shorter_than_the_minimum_wait_the_backoff(delays, clock):
    times = connect_times(delays, clock, span=600, uptime=10)
    assert times == [0, 11, 23, 37, 55, 81, 123, 197, 335, 525]


def test_connections_open_for_the_minimum_reconnect_at_once(delays, clock):
    times = connect_times(delays, clock, span=600, uptime=MIN_UPTIME)
    assert times == [0, 60, 120, 180, 240, 300, 360, 420, 480, 540]


@pytest.mark.parametrize(("uptime", "expected"), [(59.9, 1.0), (60.0, 0.0), (3600.0, 0.0)])
def test_next_delay_compares_the_uptime_with_the_minimum(delays, clock, uptime, expected):
    delays.opened()
    clock.now += uptime
    assert delays.next_delay() == expected


def test_a_long_connection_starts_the_backoff_again(delays, clock):
    for _ in range(3):
        delays.opened()
        delays.next_delay()
    delays.opened()
    clock.now += MIN_UPTIME
    assert delays.next_delay() == 0.0
    delays.opened()
    assert delays.next_delay() == 1.0


def test_failed_connects_wait_the_next_delay_each_time(delays):
    assert [delays.next_delay() for _ in range(9)] == [1, 2, 4, 8, 16, 32, 64, 128, MAXIMUM]


def test_a_failed_connect_after_a_long_connection_waits(delays, clock):
    delays.opened()
    clock.now += 2 * MIN_UPTIME
    assert delays.next_delay() == 0.0
    assert delays.next_delay() == 1.0
