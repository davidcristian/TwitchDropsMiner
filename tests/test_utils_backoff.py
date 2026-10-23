from __future__ import annotations

from types import SimpleNamespace

import pytest

import utils.backoff
from utils import ExponentialBackoff


def delays(backoff: ExponentialBackoff, count: int) -> list[float]:
    return [next(backoff) for _ in range(count)]


def test_the_delays_double_from_one_second():
    assert delays(ExponentialBackoff(variance=0), 5) == [1, 2, 4, 8, 16]


def test_the_delays_grow_by_the_base():
    assert delays(ExponentialBackoff(base=3, variance=0), 3) == [1, 3, 9]


def test_shift_is_added_to_each_delay():
    assert delays(ExponentialBackoff(variance=0, shift=3), 3) == [4, 5, 7]


@pytest.mark.parametrize("base", [1, 0.5, 0])
def test_a_base_of_one_or_less_raises_value_error(base):
    with pytest.raises(ValueError):
        ExponentialBackoff(base=base)


def test_a_delay_over_the_maximum_is_the_maximum_and_the_steps_stop_growing():
    backoff = ExponentialBackoff(variance=0, maximum=5)

    assert delays(backoff, 6) == [1, 2, 4, 5, 5, 5]
    assert (backoff.steps, backoff.exp) == (3, 2)


def test_a_delay_equal_to_the_maximum_counts_as_a_step():
    backoff = ExponentialBackoff(variance=0, maximum=4)

    assert delays(backoff, 3) == [1, 2, 4]
    assert backoff.steps == 3


def test_reset_starts_the_delays_again_from_the_first():
    backoff = ExponentialBackoff(variance=0)
    delays(backoff, 4)

    backoff.reset()

    assert (backoff.steps, backoff.exp, delays(backoff, 2)) == (0, 0, [1, 2])


def test_the_backoff_is_its_own_iterator():
    backoff = ExponentialBackoff(variance=0)

    assert iter(backoff) is backoff
    assert [delay for delay, _ in zip(backoff, range(3))] == [1, 2, 4]


@pytest.mark.parametrize("end, factor", [(0, 0.9), (1, 1.1)])
def test_a_variance_of_a_tenth_changes_each_delay_by_up_to_ten_percent(monkeypatch, end, factor):
    # the random factor at either end of its range
    monkeypatch.setattr(utils.backoff, "random", SimpleNamespace(uniform=lambda low, high: (low, high)[end]))

    assert delays(ExponentialBackoff(), 4) == pytest.approx([factor * 2**step for step in range(4)])


@pytest.mark.parametrize("end, factor", [(0, 0.5), (1, 2.0)])
def test_a_variance_tuple_sets_the_ends_of_the_factor(monkeypatch, end, factor):
    monkeypatch.setattr(utils.backoff, "random", SimpleNamespace(uniform=lambda low, high: (low, high)[end]))

    assert delays(ExponentialBackoff(variance=(0.5, 2.0)), 3) == [factor * 2**step for step in range(3)]


def test_every_delay_of_a_varied_backoff_is_within_its_range():
    backoff = ExponentialBackoff(maximum=1000)

    for step, delay in enumerate(delays(backoff, 8)):
        assert 0.9 * 2**step <= delay <= 1.1 * 2**step
