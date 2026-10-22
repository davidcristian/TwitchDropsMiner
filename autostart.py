"""The entry that starts the app at login: its command, and where each system keeps it."""
from __future__ import annotations

import sys
import shlex
import plistlib
from pathlib import Path
from collections import abc
from typing import Protocol

from constants import LOGGING_LEVELS

if sys.platform == "win32":
    from registry import RegistryKey, ValueType, ValueNotFound


AUTOSTART_NAME = "TwitchDropsMiner"
AUTOSTART_KEY = "HKCU/Software/Microsoft/Windows/CurrentVersion/Run"
LAUNCH_AGENT_LABEL = f"com.devilxd.{AUTOSTART_NAME.lower()}"
DESKTOP_ENTRY = """
[Desktop Entry]
Type=Application
Name=Twitch Drops Miner
Description=Mine timed drops on Twitch
Exec=sh -c '{command}'
"""


class AutostartEntry(Protocol):
    def contains(self, self_path: Path) -> bool:
        """Return True when the entry exists and starts the app at self_path."""

    def write(self, command: str) -> None:
        """Create or replace the entry, so that it runs command."""

    def remove(self) -> None:
        """Remove the entry, when it exists."""


def source_python(scripts_path: Path, platform: str) -> Path:
    """Return the Python in the scripts folder of the virtual environment that starts a run from source."""
    # pythonw starts the app without a console window, and a virtual environment has it only on Windows
    return scripts_path / ("pythonw" if platform == "win32" else "python")


def autostart_command(self_path: Path, logging_level: int, tray: bool, python: Path | None) -> str:
    """Return the command that starts the app at self_path with the current `-v` flags, run by python if set."""
    # the double quotes keep a path with spaces as one argument
    parts = [f'"{self_path}"']
    if python is not None:
        parts.insert(0, f'"{python}"')
    verbosity = next((index for index, level in LOGGING_LEVELS.items() if level == logging_level), 0)
    if verbosity > 0:
        parts.append(f"-{'v' * verbosity}")
    if tray:
        parts.append("--tray")
    return " ".join(parts)


def xdg_autostart_folder(environ: abc.Mapping[str, str], home: Path) -> Path:
    """Return the folder that the XDG Autostart specification gives for the entries of the user."""
    config_home = Path(environ.get("XDG_CONFIG_HOME", ""))
    # the XDG Base Directory specification ignores an unset, empty or relative XDG_CONFIG_HOME
    if not config_home.is_absolute():
        config_home = home / ".config"
    return config_home / "autostart"


def autostart_entry(platform: str, environ: abc.Mapping[str, str], home: Path) -> AutostartEntry:
    """Return the autostart entry of the app on the system that platform names, as `sys.platform` does."""
    if platform == "win32":
        return RegistryValue()
    if platform == "darwin":
        return LaunchAgent(home / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist")
    return DesktopFile(xdg_autostart_folder(environ, home) / f"{AUTOSTART_NAME}.desktop")


class DesktopFile:
    """A desktop entry file in an XDG autostart folder."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def contains(self, self_path: Path) -> bool:
        return self.path.exists() and f'"{self_path}"' in self.path.read_text(encoding="utf8")

    def write(self, command: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(DESKTOP_ENTRY.format(command=command), encoding="utf8")

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


class LaunchAgent:
    """A launchd property list in the LaunchAgents folder of the user on macOS."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def contains(self, self_path: Path) -> bool:
        return self.path.exists() and str(self_path) in self.path.read_text(encoding="utf8")

    def write(self, command: str) -> None:
        data = {"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": shlex.split(command), "RunAtLoad": True}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("wb") as file:
            plistlib.dump(data, file)

    def remove(self) -> None:
        self.path.unlink(missing_ok=True)


class RegistryValue:
    """The value `AUTOSTART_NAME` under the `Run` key of the current user in the Windows registry."""

    def contains(self, self_path: Path) -> bool:
        with RegistryKey(AUTOSTART_KEY, read_only=True) as key:
            try:
                value_type, value = key.get(AUTOSTART_NAME)
            except ValueNotFound:
                return False
        return value_type is ValueType.REG_SZ and f'"{self_path}"' in value

    def write(self, command: str) -> None:
        with RegistryKey(AUTOSTART_KEY) as key:
            key.set(AUTOSTART_NAME, ValueType.REG_SZ, command)

    def remove(self) -> None:
        with RegistryKey(AUTOSTART_KEY) as key:
            key.delete(AUTOSTART_NAME, silent=True)
