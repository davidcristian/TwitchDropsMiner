"""Scans the game folders the user added, with both the Steam and the Epic scanner."""
from __future__ import annotations

from pathlib import Path
from collections import abc

from .epic import scan_epic
from .steam import scan_steam
from .common import LocalGame, Platform, ScanResult


def scan_directories(directories: abc.Iterable[Path | str]) -> ScanResult:
    """
    Scan every given directory for installed games, de-duplicating the results.

    Each directory is probed as both a Steam and an Epic install, so the user
    never has to tell us which launcher they're pointing at.
    """
    result = ScanResult()
    for raw_directory in directories:
        directory = Path(raw_directory).expanduser()
        try:
            if not directory.is_dir():
                result.errors.append(f"Not a directory: {directory}")
                continue
        except OSError as exc:
            result.errors.append(f"{directory}: {exc}")
            continue
        recognized = scan_steam(directory, result)
        # NOTE: not an elif - a single folder can hold both, and probing is cheap
        if scan_epic(directory, result):
            recognized = True
        if not recognized:
            result.errors.append(f"No Steam or Epic games found in: {directory}")
    # de-duplicate, keeping the first occurrence of each name per platform
    seen: set[tuple[str, Platform]] = set()
    unique: list[LocalGame] = []
    for game in result.games:
        key = (game.name.lower(), game.platform)
        if key in seen:
            continue
        seen.add(key)
        unique.append(game)
    unique.sort(key=lambda g: g.name.lower())
    result.games = unique
    return result
