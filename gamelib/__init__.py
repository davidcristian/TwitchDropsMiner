"""Finds installed games, and matches game names against Twitch games and list entries."""
from __future__ import annotations

from .epic import scan_epic
from .scan import scan_directories
from .steam import STEAM_TOOL_APPIDS, STEAM_TOOL_PREFIXES, scan_steam
from .common import GameMatch, LocalGame, MatchKind, Platform, ScanResult
from .matching import (
    EDITION_WORDS,
    ROMAN_NUMERALS,
    FUZZY_THRESHOLD,
    FUZZY_MIN_LENGTH,
    normalize,
    match_games,
)
from .patterns import (
    matches,
    any_match,
    match_rank,
    has_wildcard,
    matching_names,
    compile_pattern,
    compile_patterns,
)

__all__ = [
    "EDITION_WORDS",
    "FUZZY_MIN_LENGTH",
    "FUZZY_THRESHOLD",
    "GameMatch",
    "LocalGame",
    "MatchKind",
    "Platform",
    "ROMAN_NUMERALS",
    "STEAM_TOOL_APPIDS",
    "STEAM_TOOL_PREFIXES",
    "ScanResult",
    "any_match",
    "compile_pattern",
    "compile_patterns",
    "has_wildcard",
    "match_games",
    "match_rank",
    "matches",
    "matching_names",
    "normalize",
    "scan_directories",
    "scan_epic",
    "scan_steam",
]
