from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitrepo import isolate_git

# The Epic launcher's system folder as gamelib/epic.py names it
EPIC_SYSTEM_MANIFESTS = "C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests"


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch, tmp_path_factory):
    # A git hook runs the suite with GIT_DIR and GIT_INDEX_FILE set to the repo being committed, which would
    # receive a test's git commands. A user's global ignore file would hide a test repo's files from git.
    isolate_git(monkeypatch, tmp_path_factory.mktemp("home"))


@pytest.fixture
def launcher_folders(tmp_path, monkeypatch):
    import gamelib.epic

    home = tmp_path / "home"
    home.mkdir()
    # Path.home() and expanduser read HOME on Linux and USERPROFILE on Windows
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    system = tmp_path / "ProgramData"
    real_path = gamelib.epic.Path

    def path(*parts):
        # epic.py writes the system folder as a literal, so only that lookup is sent to tmp_path
        if parts == (EPIC_SYSTEM_MANIFESTS,):
            return system
        return real_path(*parts)

    path.home = real_path.home
    monkeypatch.setattr(gamelib.epic, "Path", path)
    return SimpleNamespace(home=home, system=system)


@pytest.fixture
def steam_manifest():
    def write(steamapps: Path, app_id: int | str, name: str, installdir: str | None = None) -> Path:
        lines = ['"AppState"', "{", f'\t"appid"\t\t"{app_id}"', f'\t"name"\t\t"{name}"']
        if installdir is not None:
            lines.append(f'\t"installdir"\t\t"{installdir}"')
        lines += ['\t"UserConfig"', "\t{", '\t\t"language"\t\t"english"', "\t}", "}", ""]
        steamapps.mkdir(parents=True, exist_ok=True)
        manifest = steamapps / f"appmanifest_{app_id}.acf"
        manifest.write_text("\n".join(lines), encoding="utf-8")
        return manifest

    return write


@pytest.fixture
def epic_manifest():
    def write(folder: Path, name: str, app_name: str, **fields) -> Path:
        data = {
            "DisplayName": name,
            "AppName": app_name,
            "MainGameAppName": app_name,
            "InstallLocation": f"D:/Epic Games/{app_name}",
            **fields,
        }
        folder.mkdir(parents=True, exist_ok=True)
        manifest = folder / f"{app_name}.item"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return manifest

    return write


@pytest.fixture
def unreadable():
    if sys.platform == "win32" or os.geteuid() == 0:
        pytest.skip("needs file modes that the current user cannot bypass")
    changed: list[Path] = []

    def make(path: Path) -> Path:
        path.chmod(0)
        changed.append(path)
        return path

    yield make
    for path in changed:
        path.chmod(0o700)


@pytest.fixture
def unopenable(unreadable):
    def make(folder: Path) -> Path:
        unreadable(folder)
        try:
            (folder / "child").is_dir()
        except PermissionError:
            return folder
        # Python 3.14 returns False there, so the scan has no error to report
        pytest.skip("Path.is_dir raises no error for a path inside a folder the user may not open")

    return make
