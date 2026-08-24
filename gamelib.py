from __future__ import annotations

import re
import json
import logging
import unicodedata
from pathlib import Path
from enum import Enum, auto
from collections import abc, defaultdict
from functools import lru_cache
from difflib import SequenceMatcher
from dataclasses import dataclass, field

logger = logging.getLogger("TwitchDrops")


# Steam entries that are tooling rather than games, and would only ever produce
# false matches. Filtering by AppID is exact, so it's preferred over name matching.
STEAM_TOOL_APPIDS: frozenset[int] = frozenset({
    228980,   # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime 1.0 (scout)
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    1493710,  # Proton Experimental
    2180100,  # Proton Hotfix
    2805730,  # Proton 9.0
})
# Anything whose name starts with one of these is a runtime or compatibility tool.
STEAM_TOOL_PREFIXES: tuple[str, ...] = (
    "proton",
    "steam linux runtime",
    "steamworks common",
)
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
    VARIANT = auto()  # identical after stripping edition words / numeral spelling
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


#################
# VDF / manifest parsing
#################

# Steam's KeyValues format is nested, but every field we need is a plain
# '"key"    "value"' pair, so a full parser would be overkill here.
_KV_PATTERN = re.compile(r'"([^"]+)"\s*"([^"]*)"')


def _parse_kv(text: str) -> dict[str, str]:
    """
    Pull the flat '"key" "value"' pairs out of a Steam KeyValues document.

    The first occurrence of a key wins: the fields we care about sit at the top of
    the file, while nested blocks further down can reuse the same key names.
    """
    result: dict[str, str] = {}
    for key, value in _KV_PATTERN.findall(text):
        result.setdefault(key, value.replace("\\\\", "\\"))
    return result


def _parse_kv_all(text: str, key: str) -> list[str]:
    """
    Return every value stored under the given key, in document order.
    """
    return [
        value.replace("\\\\", "\\")
        for found_key, value in _KV_PATTERN.findall(text)
        if found_key == key
    ]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.log(logging.DEBUG, f"Game library: cannot read {path}: {exc}")
        return None


#################
# Steam
#################

def _find_steamapps(directory: Path) -> Path | None:
    """
    Resolve a user-picked directory to a 'steamapps' folder.

    Accepts the Steam root, the steamapps folder itself, or the 'common' folder
    inside it, because all three are things a user could reasonably point at.
    """
    if directory.name.lower() == "common" and (directory.parent / "libraryfolders.vdf").exists():
        directory = directory.parent
    if any(directory.glob("appmanifest_*.acf")):
        return directory
    for candidate in (directory / "steamapps", directory / "SteamApps"):
        if candidate.is_dir():
            return candidate
    return None


def _steam_library_index(steamapps: Path) -> list[Path]:
    """
    Read Steam's own library index, so that libraries on other drives are picked
    up from a single added directory.
    """
    libraries: list[Path] = [steamapps]
    for index_path in (
        steamapps / "libraryfolders.vdf",
        steamapps.parent / "config" / "libraryfolders.vdf",  # older Steam layout
    ):
        if not index_path.is_file():
            continue
        text = _read_text(index_path)
        if text is None:
            continue
        for raw_path in _parse_kv_all(text, "path"):
            library = Path(raw_path) / "steamapps"
            if library.is_dir() and library not in libraries:
                libraries.append(library)
        break
    return libraries


def _scan_steam_library(steamapps: Path, result: ScanResult) -> None:
    for manifest_path in sorted(steamapps.glob("appmanifest_*.acf")):
        text = _read_text(manifest_path)
        if text is None:
            continue
        fields = _parse_kv(text)
        name: str = fields.get("name", "").strip()
        if not name:
            continue
        app_id: str = fields.get("appid", "")
        if app_id.isdigit() and int(app_id) in STEAM_TOOL_APPIDS:
            continue
        lowered = name.lower()
        if any(lowered.startswith(prefix) for prefix in STEAM_TOOL_PREFIXES):
            continue
        install_dir: str = fields.get("installdir", "")
        result.games.append(
            LocalGame(
                name=name,
                platform=Platform.STEAM,
                path=(steamapps / "common" / install_dir) if install_dir else None,
                app_id=app_id,
            )
        )


def scan_steam(directory: Path, result: ScanResult) -> bool:
    """
    Scan a Steam installation, following its library index to other drives.

    Returns whether the directory looked like a Steam install at all.
    """
    steamapps = _find_steamapps(directory)
    if steamapps is None:
        return False
    for library in _steam_library_index(steamapps):
        if library in result.libraries:
            continue
        result.libraries.append(library)
        _scan_steam_library(library, result)
    return True


#################
# Epic
#################

def _epic_manifest_dirs(directory: Path) -> list[Path]:
    """
    Locate the folders holding Epic's '.item' manifests.

    The launcher keeps them in a fixed system location rather than next to the
    games, so a user pointing at their Epic games folder still needs us to go
    find the real index.
    """
    dirs: list[Path] = []
    if any(directory.glob("*.item")):
        dirs.append(directory)
    nested = directory / "Manifests"
    if nested.is_dir() and any(nested.glob("*.item")):
        dirs.append(nested)
    # the launcher's own index location, which is where installs are really tracked
    for well_known in (
        Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests"),
        Path.home() / ".config" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests",
    ):
        if well_known.is_dir() and any(well_known.glob("*.item")):
            dirs.append(well_known)
    return dirs


def _scan_epic_manifests(manifests: Path, result: ScanResult) -> None:
    for manifest_path in sorted(manifests.glob("*.item")):
        text = _read_text(manifest_path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            logger.log(logging.DEBUG, f"Game library: malformed manifest {manifest_path}")
            continue
        if not isinstance(data, dict):
            continue
        name: str = str(data.get("DisplayName", "")).strip()
        if not name:
            continue
        app_name: str = str(data.get("AppName", ""))
        main_app: str = str(data.get("MainGameAppName", ""))
        # DLC and add-ons point back at the game they belong to - skip them,
        # they'd only ever produce duplicate or bogus matches
        if main_app and app_name and main_app != app_name:
            continue
        if data.get("bIsIncompleteInstall"):
            continue
        install_location: str = str(data.get("InstallLocation", ""))
        result.games.append(
            LocalGame(
                name=name,
                platform=Platform.EPIC,
                path=Path(install_location) if install_location else None,
                app_id=app_name,
            )
        )


def _scan_legendary(directory: Path, result: ScanResult) -> bool:
    """
    Read the install index used by Legendary and Heroic, the usual way Epic games
    end up installed on Linux.
    """
    found = False
    candidates: list[Path] = [
        directory / "installed.json",
        Path.home() / ".config" / "legendary" / "installed.json",
        Path.home() / ".config" / "heroic" / "legendaryConfig" / "legendary" / "installed.json",
    ]
    for index_path in candidates:
        if not index_path.is_file():
            continue
        text = _read_text(index_path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        found = True
        if index_path.parent not in result.libraries:
            result.libraries.append(index_path.parent)
        for app_name, entry in data.items():
            if not isinstance(entry, dict):
                continue
            title: str = str(entry.get("title", "")).strip()
            if not title:
                continue
            install_path: str = str(entry.get("install_path", ""))
            result.games.append(
                LocalGame(
                    name=title,
                    platform=Platform.EPIC,
                    path=Path(install_path) if install_path else None,
                    app_id=str(app_name),
                )
            )
    return found


def scan_epic(directory: Path, result: ScanResult) -> bool:
    """
    Scan an Epic Games installation. Returns whether anything Epic-shaped was found.
    """
    found = False
    for manifests in _epic_manifest_dirs(directory):
        if manifests in result.libraries:
            continue
        result.libraries.append(manifests)
        _scan_epic_manifests(manifests, result)
        found = True
    if _scan_legendary(directory, result):
        found = True
    return found


#################
# Scanning entry point
#################

def scan_directories(directories: abc.Iterable[Path | str]) -> ScanResult:
    """
    Scan every given directory for installed games, de-duplicating the results.

    Each directory is probed as both a Steam and an Epic install, so the user
    never has to tell us which launcher they're pointing at.
    """
    result = ScanResult()
    for raw_directory in directories:
        directory = Path(raw_directory).expanduser()
        try:
            if not directory.is_dir():
                result.errors.append(f"Not a directory: {directory}")
                continue
        except OSError as exc:
            result.errors.append(f"{directory}: {exc}")
            continue
        recognized = scan_steam(directory, result)
        # NOTE: not an elif - a single folder can hold both, and probing is cheap
        if scan_epic(directory, result):
            recognized = True
        if not recognized:
            result.errors.append(f"No Steam or Epic games found in: {directory}")
    # de-duplicate, keeping the first occurrence of each name per platform
    seen: set[tuple[str, Platform]] = set()
    unique: list[LocalGame] = []
    for game in result.games:
        key = (game.name.lower(), game.platform)
        if key in seen:
            continue
        seen.add(key)
        unique.append(game)
    unique.sort(key=lambda g: g.name.lower())
    result.games = unique
    return result


#################
# Name matching
#################

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


#################
# Priority / exclude list patterns
#################

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
    '*' matches any run of characters and '?' matches a single one, which lets a
    single entry stand in for a whole series of games.
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
    ever matches that one game - 'Rust' never picks up 'Rust Console Edition'.
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
