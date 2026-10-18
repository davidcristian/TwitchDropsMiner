import json
import sys

import pytest

from gamelib import Platform, ScanResult, scan_directories

pytestmark = pytest.mark.usefixtures("launcher_folders")


def write_legendary_index(path, titles):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({title: {"title": title} for title in titles}), encoding="utf-8")


def names(result):
    return [game.name for game in result.games]


def test_scan_directories_reports_a_path_that_is_not_a_folder(tmp_path):
    missing = tmp_path / "missing"
    file = tmp_path / "file.txt"
    file.write_text("text", encoding="utf-8")
    result = scan_directories([missing, file])
    assert result.errors == [f"Not a directory: {missing}", f"Not a directory: {file}"]
    assert result.games == []


def test_scan_directories_reports_a_folder_without_games(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = scan_directories([empty])
    assert result.errors == [f"No Steam or Epic games found in: {empty}"]


def test_scan_directories_reports_a_folder_it_cannot_check(tmp_path, unreadable):
    locked = tmp_path / "locked"
    locked.mkdir()
    unreadable(locked)
    result = scan_directories([locked / "Games"])
    assert len(result.errors) == 1
    assert str(locked / "Games") in result.errors[0]


def test_scan_directories_recognizes_every_folder_when_the_home_folder_has_a_legendary_index(
    tmp_path, launcher_folders
):
    write_legendary_index(launcher_folders.home / ".config" / "legendary" / "installed.json", ["Fortnite"])
    (tmp_path / "empty").mkdir()
    result = scan_directories([tmp_path / "empty"])
    assert result.errors == []
    assert names(result) == ["Fortnite"]


def test_scan_directories_expands_the_home_folder(launcher_folders, steam_manifest):
    steam_manifest(launcher_folders.home / "Steam" / "steamapps", 620, "Portal 2")
    result = scan_directories(["~/Steam"])
    assert names(result) == ["Portal 2"]
    assert result.errors == []


def test_scan_directories_reads_steam_and_epic_games_in_one_folder(tmp_path, steam_manifest, epic_manifest):
    steam_manifest(tmp_path / "Games" / "steamapps", 620, "Portal 2")
    epic_manifest(tmp_path / "Games" / "Manifests", "Fortnite", "Fortnite")
    result = scan_directories([tmp_path / "Games"])
    assert [(game.name, game.platform) for game in result.games] == [
        ("Fortnite", Platform.EPIC),
        ("Portal 2", Platform.STEAM),
    ]


def test_scan_directories_keeps_the_first_game_of_each_name_and_platform(tmp_path, steam_manifest, epic_manifest):
    steam_manifest(tmp_path / "a" / "steamapps", 620, "Portal 2", "Portal 2")
    epic_manifest(tmp_path / "a" / "Manifests", "Portal 2", "Portal2")
    steam_manifest(tmp_path / "b" / "steamapps", 620, "PORTAL 2", "Portal 2")
    result = scan_directories([tmp_path / "a", tmp_path / "b"])
    assert [(game.name, game.platform) for game in result.games] == [
        ("Portal 2", Platform.STEAM),
        ("Portal 2", Platform.EPIC),
    ]
    assert result.games[0].path == tmp_path / "a" / "steamapps" / "common" / "Portal 2"


def test_scan_directories_lists_a_legendary_game_once_for_many_folders(tmp_path, launcher_folders):
    write_legendary_index(launcher_folders.home / ".config" / "legendary" / "installed.json", ["Fortnite"])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    result = scan_directories([tmp_path / "a", tmp_path / "b"])
    assert names(result) == ["Fortnite"]


def test_scan_directories_sorts_games_by_name_ignoring_case(tmp_path, steam_manifest):
    steamapps = tmp_path / "steamapps"
    steam_manifest(steamapps, 230410, "Warframe")
    steam_manifest(steamapps, 1086940, "baldur's gate 3")
    steam_manifest(steamapps, 1172470, "Apex Legends")
    result = scan_directories([steamapps])
    assert names(result) == ["Apex Legends", "baldur's gate 3", "Warframe"]


def test_scan_directories_returns_an_empty_result_for_no_folders():
    assert scan_directories([]) == ScanResult()


@pytest.mark.xfail(
    strict=True,
    reason="scan_epic returns False when an earlier folder already read the system manifests, so the later folder "
    "gets the error line (docs/refinements/tasks/034-shared-epic-folder-reported-empty.md)",
)
def test_scan_directories_reports_no_error_for_folders_that_share_the_system_launcher_folder(
    tmp_path, launcher_folders, steam_manifest, epic_manifest
):
    steam_manifest(tmp_path / "Steam" / "steamapps", 620, "Portal 2")
    epic_manifest(launcher_folders.system, "Fortnite", "Fortnite")
    (tmp_path / "Epic Games").mkdir()
    result = scan_directories([tmp_path / "Steam", tmp_path / "Epic Games"])
    assert names(result) == ["Fortnite", "Portal 2"]
    assert result.errors == []


@pytest.mark.skipif(sys.platform == "win32", reason="Windows forms a home folder for any user name")
@pytest.mark.xfail(
    strict=True,
    reason="expanduser raises RuntimeError for an unknown user name, which ends the scan of every folder "
    "(docs/refinements/tasks/035-unknown-user-ends-the-game-scan.md)",
)
def test_scan_directories_reports_the_folder_of_an_unknown_user(tmp_path, steam_manifest):
    steam_manifest(tmp_path / "Steam" / "steamapps", 620, "Portal 2")
    result = scan_directories(["~tdm-no-such-user/Games", tmp_path / "Steam"])
    assert names(result) == ["Portal 2"]
    assert len(result.errors) == 1
