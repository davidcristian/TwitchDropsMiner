"""Finds games installed through the Epic Games Launcher, Legendary or Heroic."""
from __future__ import annotations

import os
import sys
import json
import logging
from pathlib import Path
from collections import abc
from dataclasses import dataclass

from .common import LocalGame, Platform, ScanResult, read_text

logger = logging.getLogger("TwitchDrops")

_EPIC_MANIFESTS = Path("Epic", "EpicGamesLauncher", "Data", "Manifests")
_HEROIC_LEGENDARY = Path("heroic", "legendaryConfig", "legendary")


@dataclass(frozen=True)
class LauncherIndexes:
    """The launcher indexes that the Epic scan reads for every added folder."""
    manifests: tuple[Path, ...]  # folders of Epic Games Launcher '.item' manifests
    legendary: tuple[Path, ...]  # the 'installed.json' files of Legendary and Heroic


def launcher_indexes(platform: str, environ: abc.Mapping[str, str], home: Path) -> LauncherIndexes:
    """
    Returns where the launchers keep their indexes on a platform, named as `sys.platform` names it.
    """
    config = home / ".config"
    xdg_config = environ.get("XDG_CONFIG_HOME")
    manifests = [config / _EPIC_MANIFESTS]
    # Legendary reads LEGENDARY_CONFIG_PATH, else XDG_CONFIG_HOME/legendary, else ~/.config/legendary
    legendary = [config / "legendary"]
    if xdg_config:
        legendary.append(Path(xdg_config) / "legendary")
    if environ.get("LEGENDARY_CONFIG_PATH"):
        legendary.append(Path(environ["LEGENDARY_CONFIG_PATH"]))
    # Heroic keeps its own Legendary folder in Electron's appData folder
    app_data = [config]
    if platform == "win32":
        manifests.insert(0, Path(environ.get("PROGRAMDATA") or "C:/ProgramData") / _EPIC_MANIFESTS)
        if environ.get("APPDATA"):
            app_data.append(Path(environ["APPDATA"]))
    elif platform == "darwin":
        support = home / "Library" / "Application Support"
        manifests.append(support / _EPIC_MANIFESTS)
        app_data.append(support)
    else:
        if xdg_config:
            app_data.append(Path(xdg_config))
        app_data.append(home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config")
    legendary.extend(folder / _HEROIC_LEGENDARY for folder in app_data)
    # XDG_CONFIG_HOME is often ~/.config, and an index listed twice would add its games twice
    indexes = dict.fromkeys(folder / "installed.json" for folder in legendary)
    return LauncherIndexes(tuple(manifests), tuple(indexes))


def _text(entry: abc.Mapping[str, object], key: str) -> str:
    """Returns the value of a JSON field when it is a string, and an empty string when it is missing or not one."""
    value = entry.get(key)
    return value if isinstance(value, str) else ""


def _epic_manifest_dirs(directory: Path, launcher_folders: tuple[Path, ...]) -> list[Path]:
    """
    Returns the folders holding Epic's '.item' manifests, including the launcher's own folders.
    """
    dirs: list[Path] = []
    if any(directory.glob("*.item")):
        dirs.append(directory)
    nested = directory / "Manifests"
    if nested.is_dir() and any(nested.glob("*.item")):
        dirs.append(nested)
    # the launcher's own index location, which is where installs are really tracked
    for well_known in launcher_folders:
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
        name: str = _text(data, "DisplayName").strip()
        if not name:
            continue
        app_name: str = _text(data, "AppName")
        main_app: str = _text(data, "MainGameAppName")
        # DLC and add-ons point back at the game they belong to. Skip them, because
        # they would only ever produce duplicate or bogus matches
        if main_app and app_name and main_app != app_name:
            continue
        if data.get("bIsIncompleteInstall"):
            continue
        install_location: str = _text(data, "InstallLocation")
        result.games.append(
            LocalGame(
                name=name,
                platform=Platform.EPIC,
                path=Path(install_location) if install_location else None,
                app_id=app_name,
            )
        )


def _scan_legendary(directory: Path, result: ScanResult, indexes: tuple[Path, ...]) -> bool:
    """
    Read the install index used by Legendary and Heroic, the usual way Epic games
    end up installed on Linux.
    """
    found = False
    for index_path in (directory / "installed.json", *indexes):
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
            title: str = _text(entry, "title").strip()
            if not title:
                continue
            install_path: str = _text(entry, "install_path")
            result.games.append(
                LocalGame(
                    name=title,
                    platform=Platform.EPIC,
                    path=Path(install_path) if install_path else None,
                    app_id=str(app_name),
                )
            )
    return found


def scan_epic(directory: Path, result: ScanResult, indexes: LauncherIndexes | None = None) -> bool:
    """
    Scan an Epic Games installation. Returns whether anything Epic-shaped was found.
    `indexes` defaults to the launcher indexes of the running platform.
    """
    if indexes is None:
        indexes = launcher_indexes(sys.platform, os.environ, Path.home())
    found = False
    for manifests in _epic_manifest_dirs(directory, indexes.manifests):
        found = True
        # _epic_manifest_dirs returns the launcher's own folders for every added folder; each is read once.
        if manifests in result.libraries:
            continue
        result.libraries.append(manifests)
        _scan_epic_manifests(manifests, result)
    if _scan_legendary(directory, result, indexes.legendary):
        found = True
    return found
