"""Finds games installed through Steam, from its library index and app manifests."""
from __future__ import annotations

import re
from pathlib import Path

from .common import LocalGame, Platform, ScanResult, read_text


# Steam entries that are tooling rather than games, and would only ever produce
# false matches. Filtering by AppID is exact, so it's preferred over name matching.
STEAM_TOOL_APPIDS: frozenset[int] = frozenset({
    228980,   # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime 1.0 (scout)
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    1493710,  # Proton Experimental
    2180100,  # Proton Hotfix
    2805730,  # Proton 9.0
})
# Anything whose name starts with one of these is a runtime or compatibility tool.
STEAM_TOOL_PREFIXES: tuple[str, ...] = (
    "proton",
    "steam linux runtime",
    "steamworks common",
)


#################
# VDF / manifest parsing
#################

# Steam's KeyValues format is nested, but every field we need is a plain
# '"key"    "value"' pair, so a full parser is not needed.
_KV_PATTERN = re.compile(r'"([^"]+)"\s*"([^"]*)"')


def _parse_kv(text: str) -> dict[str, str]:
    """
    Returns the flat '"key" "value"' pairs of a Steam KeyValues document.
    The first value of a key is kept, because nested blocks below the top fields reuse key names.
    """
    result: dict[str, str] = {}
    for key, value in _KV_PATTERN.findall(text):
        result.setdefault(key, value.replace("\\\\", "\\"))
    return result


def _parse_kv_all(text: str, key: str) -> list[str]:
    """
    Return every value stored under the given key, in document order.
    """
    return [
        value.replace("\\\\", "\\")
        for found_key, value in _KV_PATTERN.findall(text)
        if found_key == key
    ]


#################
# Steam
#################

def _find_steamapps(directory: Path) -> Path | None:
    """
    Resolves a Steam root, a 'steamapps' folder or its 'common' folder to the 'steamapps' folder.
    """
    if directory.name.lower() == "common" and (directory.parent / "libraryfolders.vdf").exists():
        directory = directory.parent
    if any(directory.glob("appmanifest_*.acf")):
        return directory
    for candidate in (directory / "steamapps", directory / "SteamApps"):
        if candidate.is_dir():
            return candidate
    return None


def _steam_library_index(steamapps: Path) -> list[Path]:
    """
    Read Steam's own library index, so that libraries on other drives are picked
    up from a single added directory.
    """
    libraries: list[Path] = [steamapps]
    for index_path in (
        steamapps / "libraryfolders.vdf",
        steamapps.parent / "config" / "libraryfolders.vdf",  # older Steam layout
    ):
        if not index_path.is_file():
            continue
        text = read_text(index_path)
        if text is None:
            continue
        for raw_path in _parse_kv_all(text, "path"):
            library = Path(raw_path) / "steamapps"
            if library.is_dir() and library not in libraries:
                libraries.append(library)
        break
    return libraries


def _scan_steam_library(steamapps: Path, result: ScanResult) -> None:
    for manifest_path in sorted(steamapps.glob("appmanifest_*.acf")):
        text = read_text(manifest_path)
        if text is None:
            continue
        fields = _parse_kv(text)
        name: str = fields.get("name", "").strip()
        if not name:
            continue
        app_id: str = fields.get("appid", "")
        if app_id.isdigit() and int(app_id) in STEAM_TOOL_APPIDS:
            continue
        lowered = name.lower()
        if any(lowered.startswith(prefix) for prefix in STEAM_TOOL_PREFIXES):
            continue
        install_dir: str = fields.get("installdir", "")
        result.games.append(
            LocalGame(
                name=name,
                platform=Platform.STEAM,
                path=(steamapps / "common" / install_dir) if install_dir else None,
                app_id=app_id,
            )
        )


def scan_steam(directory: Path, result: ScanResult) -> bool:
    """
    Scan a Steam installation, following its library index to other drives.

    Returns whether the directory looked like a Steam install at all.
    """
    steamapps = _find_steamapps(directory)
    if steamapps is None:
        return False
    for library in _steam_library_index(steamapps):
        if library in result.libraries:
            continue
        result.libraries.append(library)
        _scan_steam_library(library, result)
    return True
