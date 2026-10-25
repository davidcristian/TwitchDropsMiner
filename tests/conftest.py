from __future__ import annotations

import gc
import json
import os
import sys
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from gitrepo import isolate_git
from threadcheck import pytest_sessionfinish, pytest_unconfigure  # noqa: F401

if TYPE_CHECKING:
    import tkinter

# pystray picks its tray backend when ui/tray.py imports it. The others need GTK or a display, which CI does not have.
os.environ["PYSTRAY_BACKEND"] = "dummy"
REPO = Path(__file__).resolve().parent.parent


def start_tcl_without_standard_channels() -> None:
    """Make Tcl in this thread look up its standard channels while the process has no standard handles."""
    import ctypes
    import tkinter
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetStdHandle.argtypes = (wintypes.DWORD,)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.SetStdHandle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
    # STD_INPUT_HANDLE, STD_OUTPUT_HANDLE and STD_ERROR_HANDLE
    names = (-10, -11, -12)
    handles = [kernel32.GetStdHandle(name) for name in names]
    for name in names:
        kernel32.SetStdHandle(name, None)
    try:
        # listing the channels makes Tcl create its standard channels, which it does once per thread
        tkinter.Tcl().call("file", "channels")
    finally:
        for name, handle in zip(names, handles):
            kernel32.SetStdHandle(name, handle)


# Tcl keeps the standard handles it finds first, and on Windows finds an open file by its handle. pytest's capture
# closes those handles between test phases, so a later Tk can get one for init.tcl and fail to read it.
if sys.platform == "win32":
    start_tcl_without_standard_channels()


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


@pytest.fixture(scope="session")
def display():
    """Skip the test when Tk can open no window, and fail it in CI, where the tests of the window must run."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("CI"):
            pytest.fail(f"Tk cannot open a window: {exc}")
        pytest.skip(f"Tk cannot open a window ({exc}). On Linux, `just check` runs the tests under xvfb-run")
    destroy_tk(root)


def destroy_tk(root: tkinter.Tk) -> None:
    """Destroy `root` after it handles its idle events."""
    # Tk 9 on macOS crashes in the next Tk's update_idletasks when a Tk is destroyed before it handles an event
    root.update_idletasks()
    root.destroy()


@pytest.fixture
def root(display):
    """Return a new Tk root window, and destroy it after the test."""
    import tkinter as tk

    root = tk.Tk()
    yield root
    destroy_tk(root)


@pytest.fixture
def window(display, monkeypatch, tmp_path):
    """Return a function that builds the real window around a `FakeTwitch`, and close each window it built."""
    import cache
    import constants
    import ui.settingstab
    from autostart import autostart_entry
    from gui import GUIManager

    # the window reads its icons from the app's folder and keeps the image cache in it
    monkeypatch.setattr(constants, "WORKING_DIR", REPO)
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cache")
    monkeypatch.setattr(cache, "CACHE_DB", tmp_path / "cache" / "mapping.json")
    # the Settings tab reads and writes its autostart entry as a desktop file in tmp_path on every system
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        ui.settingstab, "autostart_entry", lambda platform, environ, home: autostart_entry("linux", environ, home)
    )
    windows: list[GUIManager] = []

    def build(fake):
        windows.append(GUIManager(fake))
        return windows[-1]

    yield build
    for manager in windows:
        manager.close_window()
    # A closed window's Tk variables are cyclic garbage. A collection in another thread, such as a tray icon's,
    # runs their __del__ there, which waits one second for each before it raises "main thread is not in main loop".
    windows.clear()
    gc.collect()


@pytest.fixture
def other_language(monkeypatch, tmp_path):
    """Return a function that loads a language file with the given strings into a new `Translator`."""
    import translate.translator

    folder = tmp_path / "lang"
    folder.mkdir()
    monkeypatch.setattr(translate.translator, "LANG_PATH", folder)

    def load(strings: dict) -> translate.Translator:
        (folder / "Test.json").write_text(json.dumps(strings), encoding="utf-8")
        translator = translate.Translator()
        translator.set_language("Test")
        return translator

    return load


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

