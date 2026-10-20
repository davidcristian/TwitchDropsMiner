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


class UnsavedChanges:
    """Write a file only when it has a change that no successful write has saved yet."""

    def __init__(self, write: abc.Callable[[], None]) -> None:
        self._write = write
        self.pending: bool = False

    def mark(self) -> None:
        """Record a change, so that the next save writes the file."""
        self.pending = True

    def save(self, *, force: bool = False) -> None:
        """Call write when a change is pending or force is true. A write that raises leaves the change pending."""
        if self.pending or force:
            self._write()
            self.pending = False
