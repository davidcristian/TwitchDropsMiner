import json
import logging
from pathlib import Path

import pytest

from gamelib import LocalGame, Platform, ScanResult, scan_epic

pytestmark = pytest.mark.usefixtures("launcher_folders")

LEGENDARY_INDEXES = (
    "installed.json",
    ".config/legendary/installed.json",
    ".config/heroic/legendaryConfig/legendary/installed.json",
)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def scan(directory):
    result = ScanResult()
    return scan_epic(directory, result), result


def names(result):
    return [game.name for game in result.games]


def test_scan_epic_reads_the_manifests_in_the_added_folder(tmp_path, epic_manifest):
    folder = tmp_path / "Manifests"
    epic_manifest(folder, "Fortnite", "Fortnite")
    found, result = scan(folder)
    assert found
    assert result.games == [LocalGame("Fortnite", Platform.EPIC, Path("D:/Epic Games/Fortnite"), "Fortnite")]
    assert result.libraries == [folder]


def test_scan_epic_reads_the_manifests_subfolder_of_the_added_folder(tmp_path, epic_manifest):
    epic_manifest(tmp_path / "Data" / "Manifests", "Fortnite", "Fortnite")
    found, result = scan(tmp_path / "Data")
    assert found
    assert names(result) == ["Fortnite"]
    assert result.libraries == [tmp_path / "Data" / "Manifests"]


def test_scan_epic_reads_the_system_launcher_folder_whatever_folder_was_added(
    tmp_path, epic_manifest, launcher_folders
):
    epic_manifest(launcher_folders.system, "Fortnite", "Fortnite")
    (tmp_path / "Epic Games").mkdir()
    found, result = scan(tmp_path / "Epic Games")
    assert found
    assert names(result) == ["Fortnite"]
    assert result.libraries == [launcher_folders.system]


def test_scan_epic_reads_the_launcher_folder_in_the_home_folder(tmp_path, epic_manifest, launcher_folders):
    epic_manifest(
        launcher_folders.home / ".config" / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests", "Fortnite", "Fortnite"
    )
    (tmp_path / "Epic Games").mkdir()
    found, result = scan(tmp_path / "Epic Games")
    assert found
    assert names(result) == ["Fortnite"]


def test_scan_epic_returns_false_for_a_folder_without_epic_files(tmp_path):
    (tmp_path / "Games" / "Fortnite").mkdir(parents=True)
    found, result = scan(tmp_path / "Games")
    assert not found
    assert result == ScanResult()


def test_scan_epic_skips_a_manifest_that_is_not_valid_json(tmp_path, epic_manifest, caplog):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    (tmp_path / "broken.item").write_text('{"DisplayName": "Rocket', encoding="utf-8")
    with caplog.at_level(logging.DEBUG, logger="TwitchDrops"):
        found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]
    assert any("broken.item" in record.getMessage() for record in caplog.records)


def test_scan_epic_skips_a_manifest_that_is_not_an_object(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    (tmp_path / "list.item").write_text('["Rocket League"]', encoding="utf-8")
    found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]


def test_scan_epic_skips_a_manifest_with_an_empty_display_name(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "", "Empty")
    epic_manifest(tmp_path, "   ", "Blank")
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]


def test_scan_epic_skips_an_add_on_and_keeps_its_game(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    epic_manifest(tmp_path, "Fortnite Save the World", "FortniteSTW", MainGameAppName="Fortnite")
    found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]


def test_scan_epic_skips_an_incomplete_install(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    epic_manifest(tmp_path, "Rocket League", "Sugar", bIsIncompleteInstall=True)
    found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]


def test_scan_epic_keeps_a_game_without_an_install_location(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Fortnite", "Fortnite", InstallLocation="")
    found, result = scan(tmp_path)
    assert result.games == [LocalGame("Fortnite", Platform.EPIC, None, "Fortnite")]


def test_scan_epic_skips_a_manifest_that_cannot_be_read(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    # a folder with a manifest's name is found by the scan, and reading it fails
    (tmp_path / "Sugar.item").mkdir()
    found, result = scan(tmp_path)
    assert names(result) == ["Fortnite"]


def test_scan_epic_does_not_read_a_manifests_folder_again_for_the_same_result(tmp_path, epic_manifest):
    epic_manifest(tmp_path / "Data" / "Manifests", "Fortnite", "Fortnite")
    result = ScanResult()
    scan_epic(tmp_path / "Data", result)
    scan_epic(tmp_path / "Data", result)
    assert names(result) == ["Fortnite"]


@pytest.mark.parametrize("relative", LEGENDARY_INDEXES)
def test_scan_epic_reads_a_legendary_or_heroic_index(tmp_path, launcher_folders, relative):
    folder = tmp_path / "Games"
    folder.mkdir()
    index = (folder if relative == "installed.json" else launcher_folders.home) / relative
    write_json(index, {"Fortnite": {"title": "Fortnite", "install_path": "/games/Fortnite"}})
    found, result = scan(folder)
    assert found
    assert result.games == [LocalGame("Fortnite", Platform.EPIC, Path("/games/Fortnite"), "Fortnite")]
    assert result.libraries == [index.parent]


def test_scan_epic_skips_legendary_entries_without_a_title(tmp_path):
    write_json(tmp_path / "installed.json", {
        "Empty": {"title": "", "install_path": "/games/Empty"},
        "Text": "not an entry",
        "Fortnite": {"title": "Fortnite"},
    })
    found, result = scan(tmp_path)
    assert result.games == [LocalGame("Fortnite", Platform.EPIC, None, "Fortnite")]


@pytest.mark.parametrize("text", ['{"Fortnite": {"title"', '["Fortnite"]'])
def test_scan_epic_ignores_a_legendary_index_that_is_not_a_json_object(tmp_path, text):
    (tmp_path / "installed.json").write_text(text, encoding="utf-8")
    found, result = scan(tmp_path)
    assert not found
    assert result == ScanResult()


def test_scan_epic_ignores_a_legendary_index_that_cannot_be_read(tmp_path, unreadable):
    write_json(tmp_path / "installed.json", {"Fortnite": {"title": "Fortnite"}})
    unreadable(tmp_path / "installed.json")
    found, result = scan(tmp_path)
    assert not found
    assert result == ScanResult()
