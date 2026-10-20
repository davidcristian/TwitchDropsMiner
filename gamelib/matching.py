"""Normalizes game names and pairs installed games with the Twitch games that have campaigns."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from collections import abc, defaultdict

from .common import GameMatch, LocalGame, MatchKind


# Trailing words that describe a release variant rather than a different game, removed as a fallback.
# Not "collection", "remaster" or "remastered": the plain name of such a release is often a different game.
EDITION_WORDS: frozenset[str] = frozenset({
    "edition",
    "definitive",
    "deluxe",
    "ultimate",
    "complete",
    "enhanced",
    "goty",
    "anniversary",
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
# The roman numerals 2 to 39, each in its one correct form, so "iiii" and "xiix" stay words. l, c, d and m are left
# out, because "xl", "dc" and "mix" are words in titles. A lone i, v or x is in SINGLE_LETTER_NUMERALS instead.
ROMAN_NUMERALS: dict[str, str] = {
    "x" * (number // 10) + ("", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix")[number % 10]: str(number)
    for number in range(2, 40)
    if number not in (5, 10)
}
# Latin letters that have no accent to drop, written as the letters an English name would use.
LATIN_LETTERS = str.maketrans({
    "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ħ": "h", "ı": "i",
})
# A lone i, v or x is a number only when the numbers of two names are compared, so that "grand theft auto v"
# is not the original game. Exact and variant matches keep them as letters, as in "mega man x".
SINGLE_LETTER_NUMERALS: dict[str, str] = {"i": "1", "v": "5", "x": "10"}
# A fuzzy match needs to clear this ratio to be considered high confidence.
# This is deliberately strict: a wrong auto-added game silently wastes mining time,
# which is far worse than simply missing one that the user can still add by hand.
FUZZY_THRESHOLD: float = 0.92
# Below this many characters, a fuzzy match is too easy to hit by accident,
# so short names must match exactly (after normalization).
FUZZY_MIN_LENGTH: int = 8


def _is_accented_script(char: str) -> bool:
    """Whether a letter is Latin or Greek, whose combining marks are accents rather than parts of the letter."""
    return unicodedata.name(char, "").startswith(("LATIN", "GREEK"))


def _is_word_char(char: str) -> bool:
    """Whether a character is part of a word: a letter, a digit, or a mark such as a Devanagari vowel sign."""
    return char.isalnum() or unicodedata.category(char).startswith("M")


def normalize(name: str) -> str:
    """Returns the comparable form of a game name: case-folded words of letters and digits, in any script."""
    # NFKD writes ™ and ℠ as the letters TM and SM, which would join the word before them, so they become spaces
    text = re.sub(r"[\u2122\u2120]", " ", name)
    # drop apostrophes without leaving a gap, so "clancy's" becomes "clancys"
    text = re.sub(r"['\u2019\u02bc\u02bb\u00b4]", "", text)
    # Drop the accents of Latin and Greek letters only: the breve of the Cyrillic й and the dakuten of the kana ガ
    # make other letters, so they stay, and NFC joins them back to their letters.
    kept: list[str] = []
    accents = True
    for char in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(char):
            if accents:
                continue
        elif not unicodedata.category(char).startswith("M"):
            accents = not char.isalpha() or _is_accented_script(char)
        kept.append(char)
    text = unicodedata.normalize("NFC", "".join(kept)).casefold().translate(LATIN_LETTERS)
    text = text.replace("&", " and ")
    return " ".join("".join(char if _is_word_char(char) else " " for char in text).split())


def _variants(normalized: str) -> set[str]:
    """
    Build the alternative forms a name could reasonably be listed under.
    """
    variants: set[str] = {normalized}
    tokens: list[str] = normalized.split()
    # roman numerals written as digits, so 'iii' and '3' compare equal
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
    """The numbers in a name, in order: roman numeral words as digits, and every run of digits, even inside a word."""
    numerals = {**ROMAN_NUMERALS, **SINGLE_LETTER_NUMERALS}
    numbers: list[str] = []
    for token in normalized.split():
        if token in numerals:
            numbers.append(numerals[token])
        else:
            # "lineage2" and "三國志14" hold a number too; each digit is written in 0 to 9
            numbers.extend("".join(str(unicodedata.digit(char)) for char in run) for run in re.findall(r"\d+", token))
    return numbers


def match_games(
    local_games: abc.Iterable[LocalGame], game_names: abc.Iterable[str]
) -> list[GameMatch]:
    """
    Pairs installed games with the Twitch games that have campaigns, keeping only clear matches.
    Each Twitch name comes once, with its strongest match.
    """
    # build the lookup of Twitch names, keeping every name variant
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

    # Two installed copies of a game, as from Steam and Epic, match the same Twitch name.
    # MatchKind lists the strongest kind first, and a tie keeps the higher ratio, then the first copy.
    best: dict[str, GameMatch] = {}
    for local in local_games:
        local_normalized = normalize(local.name)
        if not local_normalized:
            continue
        match = _match_one(local, local_normalized, exact_lookup, variant_lookup, normalized_names)
        if match is None:
            continue
        kept = best.get(match.game_name)
        if kept is None or (match.kind.value, -match.ratio) < (kept.kind.value, -kept.ratio):
            best[match.game_name] = match
    return sorted(best.values(), key=lambda m: m.game_name.lower())


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
            return None  # ambiguous, so return no match instead of a guess
        return GameMatch(next(iter(candidates)), local, MatchKind.EXACT)
    # 2. match through an alternative form on either side
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
        # Sequels cause most false matches here: 'counter strike 2' and 'counter strike'
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
    # two Twitch games this close to the same local name cannot be told apart:
    # the sequel problem, where only a digit differs
    if runner_up >= FUZZY_THRESHOLD:
        return None
    return GameMatch(best_name, local, MatchKind.FUZZY, best_ratio)
