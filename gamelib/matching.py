"""Normalizes game names and pairs installed games with the Twitch games that have campaigns."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from collections import abc, defaultdict

from .common import GameMatch, LocalGame, MatchKind


# Trailing words that describe a release variant rather than a different game.
# Twitch lists games under their plain name far more often than the edition name,
# so these are stripped as a fallback when the full name doesn't match anything.
EDITION_WORDS: frozenset[str] = frozenset({
    "edition",
    "remastered",
    "remaster",
    "definitive",
    "deluxe",
    "ultimate",
    "complete",
    "enhanced",
    "goty",
    "anniversary",
    "collection",
    "bundle",
    "standard",
    "premium",
    "gold",
    "legacy",
    "classic",
    "director",
    "directors",
    "cut",
    "hd",
    "vr",
    "beta",
    "demo",
    "playtest",
    "of",
    "the",
    "year",
    "game",
})
ROMAN_NUMERALS: dict[str, str] = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "xi": "11",
    "xii": "12",
    "xiii": "13",
    "xiv": "14",
    "xv": "15",
}
# A fuzzy match needs to clear this ratio to be considered high confidence.
# This is deliberately strict - a wrong auto-added game silently wastes mining time,
# which is far worse than simply missing one that the user can still add by hand.
FUZZY_THRESHOLD: float = 0.92
# Below this many characters, a fuzzy match is too easy to hit by accident,
# so short names must match exactly (after normalization).
FUZZY_MIN_LENGTH: int = 8


def normalize(name: str) -> str:
    """
    Reduce a game name to a comparable form.

    Twitch and the launchers disagree constantly on capitalization, punctuation
    and trademark symbols - 'Tom Clancy's Rainbow Six: Siege' against
    'Tom Clancy's Rainbow Six Siege' should not be treated as two games.
    """
    # split accented characters apart and drop the accents
    text = unicodedata.normalize("NFKD", name)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = text.replace("&", " and ")
    # drop apostrophes without leaving a gap, so "clancy's" becomes "clancys"
    text = re.sub(r"['\u2019\u02bc]", "", text)
    # everything else that isn't alphanumeric becomes a separator
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _variants(normalized: str) -> set[str]:
    """
    Build the alternative spellings a name could reasonably be listed under.
    """
    variants: set[str] = {normalized}
    tokens: list[str] = normalized.split()
    # roman numerals spelled as digits, and the reverse
    arabic = [ROMAN_NUMERALS.get(token, token) for token in tokens]
    if arabic != tokens:
        variants.add(" ".join(arabic))
    # the name with trailing edition/variant words removed
    trimmed = list(tokens)
    while trimmed and trimmed[-1] in EDITION_WORDS:
        trimmed.pop()
    if trimmed and trimmed != tokens:
        variants.add(" ".join(trimmed))
        arabic_trimmed = [ROMAN_NUMERALS.get(token, token) for token in trimmed]
        if arabic_trimmed != trimmed:
            variants.add(" ".join(arabic_trimmed))
    variants.discard("")
    return variants


def _numbers(normalized: str) -> list[str]:
    """
    The numeric tokens in a name, with roman numerals folded into digits.
    """
    return [
        ROMAN_NUMERALS[token] if token in ROMAN_NUMERALS else token
        for token in normalized.split()
        if token.isdigit() or token in ROMAN_NUMERALS
    ]


def match_games(
    local_games: abc.Iterable[LocalGame], game_names: abc.Iterable[str]
) -> list[GameMatch]:
    """
    Pair installed games against the Twitch games that currently have campaigns.

    Only high-confidence pairings are returned - anything ambiguous is dropped,
    because a wrong match quietly redirects mining to a game the user never asked for.
    """
    # build the lookup of Twitch names, keeping every spelling variant
    exact_lookup: dict[str, set[str]] = defaultdict(set)
    variant_lookup: dict[str, set[str]] = defaultdict(set)
    normalized_names: dict[str, str] = {}
    for game_name in game_names:
        normalized = normalize(game_name)
        if not normalized:
            continue
        normalized_names[game_name] = normalized
        exact_lookup[normalized].add(game_name)
        for variant in _variants(normalized):
            variant_lookup[variant].add(game_name)

    matches: list[GameMatch] = []
    for local in local_games:
        local_normalized = normalize(local.name)
        if not local_normalized:
            continue
        match = _match_one(local, local_normalized, exact_lookup, variant_lookup, normalized_names)
        if match is not None:
            matches.append(match)
    matches.sort(key=lambda m: m.game_name.lower())
    return matches


def _match_one(
    local: LocalGame,
    local_normalized: str,
    exact_lookup: dict[str, set[str]],
    variant_lookup: dict[str, set[str]],
    normalized_names: dict[str, str],
) -> GameMatch | None:
    # 1. straight match on the normalized name
    candidates = exact_lookup.get(local_normalized)
    if candidates:
        if len(candidates) > 1:
            return None  # ambiguous, refuse to guess
        return GameMatch(next(iter(candidates)), local, MatchKind.EXACT)
    # 2. match through an alternative spelling on either side
    local_variants = _variants(local_normalized)
    variant_hits: set[str] = set()
    for variant in local_variants:
        variant_hits.update(variant_lookup.get(variant, ()))
    if variant_hits:
        if len(variant_hits) > 1:
            return None
        return GameMatch(next(iter(variant_hits)), local, MatchKind.VARIANT)
    # 3. fall back to character similarity, but only for names long enough
    #    that a near-miss can't be a coincidence
    if len(local_normalized) < FUZZY_MIN_LENGTH:
        return None
    local_numbers = _numbers(local_normalized)
    best_name: str | None = None
    best_ratio: float = 0.0
    runner_up: float = 0.0
    for game_name, normalized in normalized_names.items():
        if len(normalized) < FUZZY_MIN_LENGTH:
            continue
        # Sequels are the main trap here: 'counter strike 2' and 'counter strike'
        # sit well above any sane similarity threshold, but they're different games.
        # Requiring the numbers to agree rules that out.
        if _numbers(normalized) != local_numbers:
            continue
        ratio = SequenceMatcher(None, local_normalized, normalized).ratio()
        if ratio > best_ratio:
            runner_up = best_ratio
            best_ratio, best_name = ratio, game_name
        elif ratio > runner_up:
            runner_up = ratio
    if best_name is None or best_ratio < FUZZY_THRESHOLD:
        return None
    # two Twitch games this close to the same local name means we can't tell them
    # apart - the sequel problem, where only a digit differs
    if runner_up >= FUZZY_THRESHOLD:
        return None
    return GameMatch(best_name, local, MatchKind.FUZZY, best_ratio)
