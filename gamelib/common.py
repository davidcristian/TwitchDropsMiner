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


@dataclass
class ScanResult:
    games: list[LocalGame] = field(default_factory=list)
    # library paths discovered through a launcher's own index, for reporting
    libraries: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.log(logging.DEBUG, f"Game library: cannot read {path}: {exc}")
        return None
