import errno
import logging
import os

import pytest

import gamelib
from gamelib import Platform
from gamelib.common import exists, is_file, is_folder, read_text

DOCUMENTED_NAMES = {
    "EDITION_WORDS", "FUZZY_MIN_LENGTH", "FUZZY_THRESHOLD", "GameMatch", "LauncherIndexes", "LocalGame", "MatchKind",
    "Platform", "ROMAN_NUMERALS", "STEAM_TOOL_APPIDS", "STEAM_TOOL_PREFIXES", "ScanError", "ScanErrorKind",
    "ScanResult", "any_match", "compile_pattern", "compile_patterns", "has_wildcard", "launcher_indexes",
    "match_games", "match_rank", "matches", "matching_names", "normalize", "scan_directories", "scan_epic",
    "scan_steam",
}

CHECKS = (exists, is_folder, is_file)


class FailingStat:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def stat(self) -> os.stat_result:
        raise self.error


def windows_error(winerror: int, number: int = errno.EINVAL) -> OSError:
    error = OSError(number, f"Windows error {winerror}")
    error.winerror = winerror
    return error


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


def test_the_path_checks_tell_a_folder_a_file_and_a_missing_path_apart(tmp_path):
    (tmp_path / "file.txt").write_text("text", encoding="utf-8")
    paths = [tmp_path, tmp_path / "file.txt", tmp_path / "missing", tmp_path / "file.txt" / "child"]
    assert [[check(path) for check in CHECKS] for path in paths] == [
        [True, True, False], [True, False, True], [False, False, False], [False, False, False]
    ]


@pytest.mark.parametrize("check", CHECKS)
def test_a_path_check_raises_the_error_of_a_path_inside_a_folder_the_user_may_not_open(tmp_path, unreadable, check):
    locked = tmp_path / "locked"
    locked.mkdir()
    unreadable(locked)
    with pytest.raises(PermissionError):
        check(locked / "child")


@pytest.mark.parametrize(
    "error",
    [ValueError("embedded null byte"), windows_error(21), windows_error(123), windows_error(1921)],
    ids=["a null character", "a drive that is not ready", "an invalid name", "a link to itself"],
)
@pytest.mark.parametrize("check", CHECKS)
def test_a_path_check_returns_false_for_an_error_that_older_pythons_take_as_a_missing_path(check, error):
    assert check(FailingStat(error)) is False


@pytest.mark.parametrize("check", CHECKS)
def test_a_path_check_raises_another_windows_error(check):
    error = windows_error(5, errno.EACCES)
    with pytest.raises(OSError) as raised:
        check(FailingStat(error))
    assert raised.value is error
