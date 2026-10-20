"""Run the saves of the app's files during a run, where a failed save must not end the run."""
from __future__ import annotations

from collections import abc


def save_each(saves: abc.Iterable[abc.Callable[[], None]], report: abc.Callable[[OSError], None]) -> None:
    """Call each save in turn and pass the OSError of a failed one to report, so the later saves still run."""
    for save in saves:
        try:
            save()
        except OSError as exc:
            report(exc)
