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
    Turn a priority/exclude list entry into a matcher for game names.

    The literal pieces go through the same normalization as the names they're
    compared against, so 'Pokemon' finds 'Pokémon' without any special syntax.
    '*' matches any run of characters and '?' matches a single one, so a single
    entry can cover a whole series of games.
    """
    parts: list[str] = []
    for segment in _WILDCARD_SPLIT.split(text):
        if segment == "*":
            parts.append(".*")
        elif segment == "?":
            parts.append(".")
        elif segment:
            parts.append(re.escape(normalize(segment)))
    return re.compile("".join(parts))


def compile_patterns(entries: abc.Iterable[str]) -> list[re.Pattern[str]]:
    return [compile_pattern(entry) for entry in entries]


def matches(pattern: re.Pattern[str], game_name: str) -> bool:
    """
    Whether a compiled entry covers the given game name.

    The match is anchored at both ends, so an entry without wildcards still only
    ever matches that one game: 'Rust' never matches 'Rust Console Edition'.
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
