import pytest

from restartdelay import RestartDelay


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def delays(clock):
    return RestartDelay(clock)


def waits(delays, clock, settings, run_for=10.0):
    """Return the wait after each of a series of runs that last run_for seconds, one run for each setting."""
    result = []
    for minutes in settings:
        delays.started()
        clock.now += run_for
        result.append(delays.next_minutes(minutes))
        clock.now += minutes * 60
    return result


@pytest.mark.parametrize("minutes, expected", [
    (1, [1, 2, 4, 8, 16, 32, 60, 60]),
    (5, [5, 10, 20, 40, 60, 60]),
    (10, [10, 20, 40, 60, 60]),
    (60, [60, 60, 60]),
])
def test_runs_that_end_within_an_hour_double_the_wait_up_to_60_minutes(delays, clock, minutes, expected):
    assert waits(delays, clock, [minutes] * len(expected)) == expected


@pytest.mark.parametrize("run_for", [0.0, 1.0, 7200.0])
def test_the_first_error_waits_the_setting_after_a_run_of_any_length(delays, clock, run_for):
    assert waits(delays, clock, [5], run_for=run_for) == [5]


@pytest.mark.parametrize("run_for, expected", [(3600.0, 1), (7200.0, 1), (3599.0, 8)])
def test_a_run_of_an_hour_or_more_sets_the_wait_back_to_the_setting(delays, clock, run_for, expected):
    assert waits(delays, clock, [1, 1, 1]) == [1, 2, 4]

    assert waits(delays, clock, [1], run_for=run_for) == [expected]
    assert waits(delays, clock, [1]) == [2 * expected]


def test_a_changed_setting_never_makes_the_wait_shorter_than_the_setting_or_the_doubled_wait(delays, clock):
    assert waits(delays, clock, [1, 30, 1, 5]) == [1, 30, 60, 60]


def test_a_setting_above_60_minutes_is_kept(delays, clock):
    assert waits(delays, clock, [90, 90]) == [90, 90]


def test_an_error_before_the_first_recorded_start_waits_the_setting(delays, clock):
    clock.now = 10.0

    assert delays.next_minutes(15) == 15
    assert delays.next_minutes(15) == 15


def test_it_reads_no_time_until_a_run_starts(clock):
    delays = RestartDelay(clock)

    assert clock.reads == 0
    delays.started()
    assert clock.reads == 1


def test_a_reset_sets_the_next_wait_back_to_the_setting(delays, clock):
    assert waits(delays, clock, [1, 1, 1]) == [1, 2, 4]

    delays.reset()

    assert waits(delays, clock, [1, 1]) == [1, 2]


def test_a_reset_before_the_first_error_reads_no_time_and_keeps_the_setting(clock):
    delays = RestartDelay(clock)

    delays.reset()

    assert clock.reads == 0
    assert waits(delays, clock, [5]) == [5]
