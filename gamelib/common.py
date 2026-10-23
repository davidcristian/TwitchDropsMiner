"""The data types shared across gamelib, and the file reader both scanners use."""
from __future__ import annotations

import logging
from pathlib import Path
from enum import Enum, auto
from dataclasses import dataclass, field

logger = logging.getLogger("TwitchDrops")


class Platform(Enum):
    STEAM = auto()
    EPIC = auto()

    def __str__(self) -> str:
        return self.name.capitalize()


class MatchKind(Enum):
    """
    How a local game was matched against a Twitch game name, weakest last.
    """
    EXACT = auto()  # identical after normalization
    VARIANT = auto()  # identical after stripping edition words or converting roman numerals
    FUZZY = auto()  # close enough by character similarity

    def __str__(self) -> str:
        return self.name.capitalize()


@dataclass(frozen=True)
class LocalGame:
    """
    A game found installed on disk.
    """
    name: str
    platform: Platform
    path: Path | None = None
    app_id: str = ""

    def __str__(self) -> str:
        return f"{self.name} ({self.platform})"


@dataclass(frozen=True)
class GameMatch:
    """
    A local game successfully paired with a Twitch game name.
    """
    game_name: str  # the Twitch-side name, as it appears in campaigns
    local: LocalGame
    kind: MatchKind
    ratio: float = 1.0
    local_count: int = 1  # how many local games matched game_name; local is the strongest of them


class ScanErrorKind(Enum):
    """Why a folder gave no games: it is not a folder, holds no Steam or Epic install, or a check raised."""
    NOT_A_FOLDER = auto()
    NO_GAMES = auto()
    FAILED = auto()


@dataclass(frozen=True)
class ScanError:
    """A problem with one folder: its kind, the folder, and for `FAILED` the text of the error raised."""
    kind: ScanErrorKind
    path: str
    reason: str = ""


@dataclass
class ScanResult:
    games: list[LocalGame] = field(default_factory=list)
    # library paths discovered through a launcher's own index, for reporting
    libraries: list[Path] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.log(logging.DEBUG, f"Game library: cannot read {path}: {exc}")
        return None
