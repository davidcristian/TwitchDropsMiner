"""The growing delays between the retries of a request or a connection."""
from __future__ import annotations

import random
from collections import abc


class ExponentialBackoff:
    def __init__(
        self,
        *,
        base: float = 2,
        variance: float | tuple[float, float] = 0.1,
        shift: float = 0,
        maximum: float = 300,
    ):
        if base <= 1:
            raise ValueError("Base has to be greater than 1")
        self.steps: int = 0
        self.base: float = float(base)
        self.shift: float = float(shift)
        self.maximum: float = float(maximum)
        self.variance_min: float
        self.variance_max: float
        if isinstance(variance, tuple):
            self.variance_min, self.variance_max = variance
        else:
            self.variance_min = 1 - variance
            self.variance_max = 1 + variance

    @property
    def exp(self) -> int:
        return max(0, self.steps - 1)

    def __iter__(self) -> abc.Iterator[float]:
        return self

    def __next__(self) -> float:
        value: float = (
            pow(self.base, self.steps)
            * random.uniform(self.variance_min, self.variance_max)
            + self.shift
        )
        if value > self.maximum:
            return self.maximum
        # NOTE: variance can cause the returned value to be lower than the previous one already,
        # so this should be safe to move past the first return,
        # to prevent the exponent from getting very big after reaching max and many iterations
        self.steps += 1
        return value

    def reset(self) -> None:
        self.steps = 0
