"""Scans the game folders the user added, with both the Steam and the Epic scanner."""
from __future__ import annotations

from pathlib import Path
from collections import abc

from .epic import scan_epic
from .steam import scan_steam
from .common import LocalGame, Platform, ScanError, ScanErrorKind, ScanResult, is_folder


def scan_directories(directories: abc.Iterable[Path | str]) -> ScanResult:
    """
    Scans every given directory as both a Steam and an Epic install, removing duplicate games.
    """
    result = ScanResult()
    for raw_directory in directories:
        try:
            directory = Path(raw_directory).expanduser()
        except RuntimeError as exc:
            # expanduser raises it for ~name when no user has that name
            result.errors.append(ScanError(ScanErrorKind.FAILED, str(raw_directory), str(exc)))
            continue
        try:
            if not is_folder(directory):
                result.errors.append(ScanError(ScanErrorKind.NOT_A_FOLDER, str(directory)))
                continue
        except OSError as exc:
            result.errors.append(ScanError(ScanErrorKind.FAILED, str(directory), str(exc)))
            continue
        try:
            recognized = scan_steam(directory, result)
            # NOTE: not an elif, because a single folder can hold both, and probing is cheap
            if scan_epic(directory, result):
                recognized = True
        except OSError as exc:
            # is_folder and is_file raise it for a path inside a folder the user may not open
            result.errors.append(ScanError(ScanErrorKind.FAILED, str(directory), str(exc)))
            continue
        if not recognized:
            result.errors.append(ScanError(ScanErrorKind.NO_GAMES, str(directory)))
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
