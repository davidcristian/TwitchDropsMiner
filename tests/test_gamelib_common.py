import logging

import gamelib
from gamelib import Platform
from gamelib.common import read_text

DOCUMENTED_NAMES = {
    "EDITION_WORDS", "FUZZY_MIN_LENGTH", "FUZZY_THRESHOLD", "GameMatch", "LauncherIndexes", "LocalGame", "MatchKind",
    "Platform", "ROMAN_NUMERALS", "STEAM_TOOL_APPIDS", "STEAM_TOOL_PREFIXES", "ScanError", "ScanErrorKind",
    "ScanResult", "any_match", "compile_pattern", "compile_patterns", "has_wildcard", "launcher_indexes",
    "match_games", "match_rank", "matches", "matching_names", "normalize", "scan_directories", "scan_epic",
    "scan_steam",
}


def test_gamelib_exports_each_documented_name():
    assert set(gamelib.__all__) == DOCUMENTED_NAMES
    assert all(hasattr(gamelib, name) for name in gamelib.__all__)


def test_platform_text_is_the_launcher_name():
    assert [str(platform) for platform in Platform] == ["Steam", "Epic"]


def test_read_text_returns_the_text_of_a_file(tmp_path):
    path = tmp_path / "appmanifest_620.acf"
    path.write_text('"name"\t"Pokémon"', encoding="utf-8")
    assert read_text(path) == '"name"\t"Pokémon"'


def test_read_text_replaces_bytes_that_are_not_utf8(tmp_path):
    path = tmp_path / "appmanifest_620.acf"
    path.write_bytes(b'"name"\t"Pok\xe9mon"')
    assert read_text(path) == '"name"\t"Pok�mon"'


def test_read_text_returns_none_for_a_missing_file_and_logs_it(tmp_path, caplog):
    path = tmp_path / "missing.acf"
    with caplog.at_level(logging.DEBUG, logger="TwitchDrops"):
        assert read_text(path) is None
    assert [record.levelno for record in caplog.records] == [logging.DEBUG]
    assert str(path) in caplog.records[0].getMessage()
