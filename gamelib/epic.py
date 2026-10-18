"""Finds games installed through the Epic Games Launcher, Legendary or Heroic."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .common import LocalGame, Platform, ScanResult, read_text

logger = logging.getLogger("TwitchDrops")


def _epic_manifest_dirs(directory: Path) -> list[Path]:
    """
    Locate the folders holding Epic's '.item' manifests.

    The launcher keeps them in a fixed system location rather than next to the
    games, so a user pointing at their Epic games folder still needs us to go
    find the real index.
    """
    dirs: list[Path] = []
    if any(directory.glob("*.item")):
        dirs.append(directory)
    nested = directory / "Manifests"
    if nested.is_dir() and any(nested.glob("*.item")):
        dirs.append(nested)
    # the launcher's own index location, which is where installs are really tracked
    for well_known in (
        Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests"),
        Path.home() / ".config" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests",
    ):
        if well_known.is_dir() and any(well_known.glob("*.item")):
            dirs.append(well_known)
    return dirs


def _scan_epic_manifests(manifests: Path, result: ScanResult) -> None:
    for manifest_path in sorted(manifests.glob("*.item")):
        text = read_text(manifest_path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            logger.log(logging.DEBUG, f"Game library: malformed manifest {manifest_path}")
            continue
        if not isinstance(data, dict):
            continue
        name: str = str(data.get("DisplayName", "")).strip()
        if not name:
            continue
        app_name: str = str(data.get("AppName", ""))
        main_app: str = str(data.get("MainGameAppName", ""))
        # DLC and add-ons point back at the game they belong to. Skip them, because
        # they would only ever produce duplicate or bogus matches
        if main_app and app_name and main_app != app_name:
            continue
        if data.get("bIsIncompleteInstall"):
            continue
        install_location: str = str(data.get("InstallLocation", ""))
        result.games.append(
            LocalGame(
                name=name,
                platform=Platform.EPIC,
                path=Path(install_location) if install_location else None,
                app_id=app_name,
            )
        )


def _scan_legendary(directory: Path, result: ScanResult) -> bool:
    """
    Read the install index used by Legendary and Heroic, the usual way Epic games
    end up installed on Linux.
    """
    found = False
    candidates: list[Path] = [
        directory / "installed.json",
        Path.home() / ".config" / "legendary" / "installed.json",
        Path.home() / ".config" / "heroic" / "legendaryConfig" / "legendary" / "installed.json",
    ]
    for index_path in candidates:
        if not index_path.is_file():
            continue
        text = read_text(index_path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        found = True
        if index_path.parent not in result.libraries:
            result.libraries.append(index_path.parent)
        for app_name, entry in data.items():
            if not isinstance(entry, dict):
                continue
            title: str = str(entry.get("title", "")).strip()
            if not title:
                continue
            install_path: str = str(entry.get("install_path", ""))
            result.games.append(
                LocalGame(
                    name=title,
                    platform=Platform.EPIC,
                    path=Path(install_path) if install_path else None,
                    app_id=str(app_name),
                )
            )
    return found


def scan_epic(directory: Path, result: ScanResult) -> bool:
    """
    Scan an Epic Games installation. Returns whether anything Epic-shaped was found.
    """
    found = False
    for manifests in _epic_manifest_dirs(directory):
        if manifests in result.libraries:
            continue
        result.libraries.append(manifests)
        _scan_epic_manifests(manifests, result)
        found = True
    if _scan_legendary(directory, result):
        found = True
    return found
