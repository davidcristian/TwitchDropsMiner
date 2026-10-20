"""Matches game names against the priority and exclude list entries, with '*' and '?' wildcards."""
from __future__ import annotations

import re
from collections import abc
from functools import lru_cache

from .matching import normalize


# '*' and '?' are the only special characters, so the split keeps them as their own pieces
_WILDCARD_SPLIT = re.compile(r"([*?])")


def has_wildcard(text: str) -> bool:
    return "*" in text or "?" in text


@lru_cache(maxsize=256)
def compile_pattern(text: str) -> re.Pattern[str]:
    """
    Compiles a priority or exclude list entry into a regular expression for normalized names.
    '*' matches any run of characters and '?' matches one character.
    """
    segments = [segment for segment in _WILDCARD_SPLIT.split(text) if segment]
    parts: list[str] = []
    wildcards = ""
    for index, segment in enumerate(segments):
        if segment in ("*", "?"):
            wildcards += segment
            continue
        literal = _literal(segment, after_wildcard=index > 0, before_wildcard=index < len(segments) - 1)
        if literal:
            parts.append(_wildcard_run(wildcards))
            parts.append(re.escape(literal))
            wildcards = ""
    parts.append(_wildcard_run(wildcards))
    return re.compile("".join(parts))


def _wildcard_run(wildcards: str) -> str:
    """Writes wildcards with no text between them as one '.' per '?' followed by at most one '.*'."""
    # '.*.*' matches the same names as '.*', but a failed match tests every split of the name between them,
    # which takes minutes for ten '*' in a row
    return "." * wildcards.count("?") + (".*" if "*" in wildcards else "")


def _literal(segment: str, after_wildcard: bool, before_wildcard: bool) -> str:
    """Normalizes the text between wildcards, keeping spaces and punctuation next to a wildcard as one space."""
    # normalize trims its result, so a letter added at each end keeps the space there, as in a game name
    literal = normalize(f"a{segment}a")[1:-1]
    if not after_wildcard:
        literal = literal.lstrip(" ")
    if not before_wildcard:
        literal = literal.rstrip(" ")
    return literal


def compile_patterns(entries: abc.Iterable[str]) -> list[re.Pattern[str]]:
    return [compile_pattern(entry) for entry in entries]


def matches(pattern: re.Pattern[str], game_name: str) -> bool:
    """
    Returns whether a compiled entry matches the whole normalized game name.
    """
    return pattern.fullmatch(normalize(game_name)) is not None


def match_rank(patterns: abc.Sequence[re.Pattern[str]], game_name: str) -> int | None:
    """
    The position of the first entry covering this game, or None if none do.
    """
    for index, pattern in enumerate(patterns):
        if matches(pattern, game_name):
            return index
    return None


def any_match(patterns: abc.Iterable[re.Pattern[str]], game_name: str) -> bool:
    normalized = normalize(game_name)
    return any(pattern.fullmatch(normalized) is not None for pattern in patterns)


def matching_names(
    pattern: re.Pattern[str], game_names: abc.Iterable[str]
) -> list[str]:
    """
    Every known game name covered by an entry, for showing the user what it caught.
    """
    return sorted(game_name for game_name in game_names if matches(pattern, game_name))
