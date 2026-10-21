"""Run the saves of the app's files during a run, where a failed save must not end the run."""
from __future__ import annotations

import os
from collections import abc
from pathlib import Path


def save_each(saves: abc.Iterable[abc.Callable[[], None]], report: abc.Callable[[OSError], None]) -> None:
    """Call each save in turn and pass the OSError of a failed one to report, so the later saves still run."""
    for save in saves:
        try:
            save()
        except OSError as exc:
            report(exc)


def replace_file(path: Path, write: abc.Callable[[Path], None]) -> None:
    """Call write with a second path in the same folder, then replace path with the file written there."""
    new_path = path.with_name(f"{path.name}.new")
    try:
        write(new_path)
        os.replace(new_path, path)
    finally:
        new_path.unlink(missing_ok=True)


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
