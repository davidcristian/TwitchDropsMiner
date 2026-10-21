from __future__ import annotations

import json
import os
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import pytest

from gitrepo import isolate_git

# pystray picks its tray backend when gui.py imports it. The others need GTK or a display, which CI does not have.
os.environ["PYSTRAY_BACKEND"] = "dummy"


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch, tmp_path_factory):
    # A git hook runs the suite with GIT_DIR and GIT_INDEX_FILE set to the repo being committed, which would
    # receive a test's git commands. A user's global ignore file would hide a test repo's files from git.
    isolate_git(monkeypatch, tmp_path_factory.mktemp("home"))


@pytest.fixture
def live_twitch(monkeypatch, tmp_path):
    """Return a function that builds a real `Twitch` around a `FakeTwitch`, with cookies.jar in tmp_path."""
    # imported here, because importing gui.py reads PYSTRAY_BACKEND, which this file sets after its imports
    from livetwitch import build_twitch

    return partial(build_twitch, monkeypatch, tmp_path / "cookies.jar")


@pytest.fixture
def launcher_folders(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    # Path.home() and expanduser read HOME on Linux and USERPROFILE on Windows
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # launcher_indexes in gamelib/epic.py also reads these
    for name in ("XDG_CONFIG_HOME", "LEGENDARY_CONFIG_PATH", "APPDATA"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    return SimpleNamespace(
        home=home,
        manifests=home / ".config" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests",
        system=tmp_path / "ProgramData" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests",
    )


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
