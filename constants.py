from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from enum import Enum, auto
from datetime import timedelta
from typing import Any, Dict, NewType

from version import __version__


def _runs_from_appimage() -> bool:
    """Return True when this module is inside the mounted AppImage that `APPIMAGE` names."""
    appimage = os.environ.get("APPIMAGE")
    appdir = os.environ.get("APPDIR")
    if not appimage or not appdir or not os.path.exists(appimage):
        return False
    # A program started from another AppImage inherits both variables, so the module's own path decides.
    return Path(__file__).resolve().is_relative_to(Path(appdir).resolve())


# True if we're running from a built EXE (or a Linux AppImage), False inside a dev build
IS_APPIMAGE = _runs_from_appimage()
IS_PACKAGED = hasattr(sys, "_MEIPASS") or IS_APPIMAGE
# logging special levels
CALL: int = logging.INFO - 1
logging.addLevelName(CALL, "CALL")
# scripts venv path changes depending on the system platform
if sys.platform == "win32":
    SYS_SCRIPTS = "Scripts"
else:
    SYS_SCRIPTS = "bin"


def _resource_path(relative_path: Path | str) -> Path:
    """
    Get an absolute path to a bundled resource.

    Works for dev and for PyInstaller.
    """
    if IS_APPIMAGE:
        base_path = Path(sys.argv[0]).resolve().parent
    elif IS_PACKAGED:
        # PyInstaller's folder where the one-file app is unpacked
        meipass: str = getattr(sys, "_MEIPASS")
        base_path = Path(meipass)
    else:
        base_path = WORKING_DIR
    return base_path.joinpath(relative_path)


# Base Paths
if IS_APPIMAGE:
    SELF_PATH = Path(os.environ["APPIMAGE"]).resolve()
else:
    # NOTE: pyinstaller will set sys.argv[0] to its own executable when building
    # NOTE: sys.argv[0] will point to gui.py when running the gui.py directly for GUI debug
    # detect these and use __file__ and main.py redirection instead
    SELF_PATH = Path(sys.argv[0]).resolve()
    if SELF_PATH.stem == "pyinstaller" or SELF_PATH.name == "gui.py":
        SELF_PATH = Path(__file__).with_name("main.py").resolve()
WORKING_DIR = SELF_PATH.parent
# Development paths
VENV_PATH = Path(WORKING_DIR, "env")
SCRIPTS_PATH = Path(VENV_PATH, SYS_SCRIPTS)
# Translations path
# NOTE: These don't have to be available to the end-user, so the path points to the internal dir
LANG_PATH = _resource_path("lang")
# Other Paths
LOG_PATH = Path(WORKING_DIR, "log.txt")
DUMP_PATH = Path(WORKING_DIR, "dump.dat")
LOCK_PATH = Path(WORKING_DIR, "lock.file")
CACHE_PATH = Path(WORKING_DIR, "cache")
CACHE_DB = Path(CACHE_PATH, "mapping.json")
COOKIES_PATH = Path(WORKING_DIR, "cookies.jar")
SETTINGS_PATH = Path(WORKING_DIR, "settings.json")
# Typing
JsonType = Dict[str, Any]
URLType = NewType("URLType", str)
# Values
MAX_INT = sys.maxsize
MAX_EXTRA_MINUTES = 15
BASE_TOPICS = 2
MAX_WEBSOCKETS = 8
WS_TOPICS_LIMIT = 50
TOPICS_PER_CHANNEL = 2
MAX_TOPICS = (MAX_WEBSOCKETS * WS_TOPICS_LIMIT) - BASE_TOPICS
MAX_CHANNELS = MAX_TOPICS // TOPICS_PER_CHANNEL
# Misc
DEFAULT_LANG = "English"
# Intervals and Delays
PING_INTERVAL = timedelta(minutes=3)
PING_TIMEOUT = timedelta(seconds=10)
WS_MIN_UPTIME = timedelta(seconds=60)
ONLINE_DELAY = timedelta(seconds=120)
ONLINE_TRIES = 3
WATCH_INTERVAL = timedelta(seconds=20)
# How long the browser login waits for the user to log in, and the integrity refresh for the page's request.
BROWSER_LOGIN_TIMEOUT = timedelta(minutes=5)
INTEGRITY_CAPTURE_TIMEOUT = timedelta(seconds=60)
# Random amount of time added on top of the channel refresh interval,
# so that the requests don't end up sent on a perfectly fixed schedule.
REFRESH_JITTER = timedelta(seconds=60)
# Random amount of time added on top of the automatic restart delay. A Twitch-side
# outage takes every miner down at once, so this keeps them from all coming back
# at the exact same moment once it's over.
RESTART_JITTER = timedelta(seconds=60)
# Strings
WINDOW_TITLE = f"Twitch Drops Miner v{__version__}"
# Logging
LOGGING_LEVELS = {
    0: logging.ERROR,
    1: logging.WARNING,
    2: logging.INFO,
    3: CALL,
    4: logging.DEBUG,
}
FILE_FORMATTER = logging.Formatter(
    "{asctime}.{msecs:03.0f}:\t{levelname:>7}:\t{message}",
    style='{',
    datefmt="%Y-%m-%d %H:%M:%S",
)
OUTPUT_FORMATTER = logging.Formatter("{levelname}: {message}", style='{', datefmt="%H:%M:%S")


class State(Enum):
    IDLE = auto()
    INVENTORY_FETCH = auto()
    GAMES_UPDATE = auto()
    CHANNELS_FETCH = auto()
    CHANNELS_CLEANUP = auto()
    CHANNEL_SWITCH = auto()
    RESTART = auto()
    EXIT = auto()


class PriorityMode(Enum):
    PRIORITY_ONLY = 0
    ENDING_SOONEST = 1
    LOW_AVBL_FIRST = 2
