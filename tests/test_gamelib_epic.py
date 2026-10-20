import json
import logging
from pathlib import Path

import pytest

from gamelib import LauncherIndexes, LocalGame, Platform, ScanResult, launcher_indexes, scan_epic

pytestmark = pytest.mark.usefixtures("launcher_folders")

LEGENDARY_INDEXES = (
    "installed.json",
    ".config/legendary/installed.json",
    ".config/heroic/legendaryConfig/legendary/installed.json",
)
# Each environment value is a folder under the home folder
PLATFORM_INDEXES = (
    ("linux", {}, ".var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary/installed.json"),
    ("linux", {"XDG_CONFIG_HOME": "xdg"}, "xdg/legendary/installed.json"),
    ("linux", {"XDG_CONFIG_HOME": "xdg"}, "xdg/heroic/legendaryConfig/legendary/installed.json"),
    ("darwin", {"XDG_CONFIG_HOME": "xdg"}, "xdg/legendary/installed.json"),
    ("linux", {"LEGENDARY_CONFIG_PATH": "custom"}, "custom/installed.json"),
    ("darwin", {}, "Library/Application Support/heroic/legendaryConfig/legendary/installed.json"),
    ("win32", {"APPDATA": "AppData/Roaming"}, "AppData/Roaming/heroic/legendaryConfig/legendary/installed.json"),
)
ENVIRON = {"XDG_CONFIG_HOME": "xdg", "LEGENDARY_CONFIG_PATH": "custom", "APPDATA": "appdata", "PROGRAMDATA": "data"}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def scan(directory, indexes=None):
    result = ScanResult()
    return scan_epic(directory, result, indexes), result


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
    windows = launcher_indexes("win32", {"PROGRAMDATA": str(tmp_path / "ProgramData")}, launcher_folders.home)
    found, result = scan(tmp_path / "Epic Games", windows)
    assert found
    assert names(result) == ["Fortnite"]
    assert result.libraries == [launcher_folders.system]


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_scan_epic_reads_the_system_launcher_folder_only_on_windows(
    tmp_path, epic_manifest, launcher_folders, platform
):
    epic_manifest(launcher_folders.system, "Fortnite", "Fortnite")
    (tmp_path / "Epic Games").mkdir()
    indexes = launcher_indexes(platform, {"PROGRAMDATA": str(tmp_path / "ProgramData")}, launcher_folders.home)
    found, result = scan(tmp_path / "Epic Games", indexes)
    assert not found
    assert result == ScanResult()


def test_scan_epic_reads_the_launcher_folder_on_macos(tmp_path, epic_manifest, launcher_folders):
    support = launcher_folders.home / "Library" / "Application Support"
    epic_manifest(support / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests", "Fortnite", "Fortnite")
    (tmp_path / "Epic Games").mkdir()
    found, result = scan(tmp_path / "Epic Games", launcher_indexes("darwin", {}, launcher_folders.home))
    assert found
    assert names(result) == ["Fortnite"]
    assert result.libraries == [support / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"]


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


@pytest.mark.parametrize(("platform", "environ", "relative"), PLATFORM_INDEXES)
def test_scan_epic_reads_the_legendary_or_heroic_index_of_the_platform(
    tmp_path, launcher_folders, platform, environ, relative
):
    home = launcher_folders.home
    write_json(home / relative, {"Fortnite": {"title": "Fortnite", "install_path": "/games/Fortnite"}})
    (tmp_path / "Games").mkdir()
    indexes = launcher_indexes(platform, {name: str(home / value) for name, value in environ.items()}, home)
    found, result = scan(tmp_path / "Games", indexes)
    assert found
    assert result.games == [LocalGame("Fortnite", Platform.EPIC, Path("/games/Fortnite"), "Fortnite")]
    assert result.libraries == [(home / relative).parent]


def test_scan_epic_reads_an_index_once_when_xdg_config_home_is_the_default_folder(tmp_path, launcher_folders):
    home = launcher_folders.home
    write_json(home / ".config" / "legendary" / "installed.json", {"Fortnite": {"title": "Fortnite"}})
    (tmp_path / "Games").mkdir()
    indexes = launcher_indexes("linux", {"XDG_CONFIG_HOME": str(home / ".config")}, home)
    found, result = scan(tmp_path / "Games", indexes)
    assert names(result) == ["Fortnite"]


def test_scan_epic_reads_the_environment_of_the_app_by_default(tmp_path, launcher_folders, monkeypatch):
    write_json(tmp_path / "custom" / "installed.json", {"Fortnite": {"title": "Fortnite"}})
    monkeypatch.setenv("LEGENDARY_CONFIG_PATH", str(tmp_path / "custom"))
    (tmp_path / "Games").mkdir()
    found, result = scan(tmp_path / "Games")
    assert names(result) == ["Fortnite"]


@pytest.mark.parametrize(("platform", "manifests", "legendary"), [
    (
        "linux",
        [".config/Epic/EpicGamesLauncher/Data/Manifests"],
        [
            ".config/legendary",
            "xdg/legendary",
            "custom",
            ".config/heroic/legendaryConfig/legendary",
            "xdg/heroic/legendaryConfig/legendary",
            ".var/app/com.heroicgameslauncher.hgl/config/heroic/legendaryConfig/legendary",
        ],
    ),
    (
        "darwin",
        [
            ".config/Epic/EpicGamesLauncher/Data/Manifests",
            "Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests",
        ],
        [
            ".config/legendary",
            "xdg/legendary",
            "custom",
            ".config/heroic/legendaryConfig/legendary",
            "Library/Application Support/heroic/legendaryConfig/legendary",
        ],
    ),
    (
        "win32",
        ["data/Epic/EpicGamesLauncher/Data/Manifests", ".config/Epic/EpicGamesLauncher/Data/Manifests"],
        [
            ".config/legendary",
            "xdg/legendary",
            "custom",
            ".config/heroic/legendaryConfig/legendary",
            "appdata/heroic/legendaryConfig/legendary",
        ],
    ),
])
def test_launcher_indexes_lists_the_locations_of_each_platform_in_order(tmp_path, platform, manifests, legendary):
    environ = {name: str(tmp_path / value) for name, value in ENVIRON.items()}
    assert launcher_indexes(platform, environ, tmp_path) == LauncherIndexes(
        tuple(tmp_path / folder for folder in manifests),
        tuple(tmp_path / folder / "installed.json" for folder in legendary),
    )


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_launcher_indexes_ignores_an_empty_environment_variable(tmp_path, platform):
    empty = {name: "" for name in ENVIRON}
    assert launcher_indexes(platform, empty, tmp_path) == launcher_indexes(platform, {}, tmp_path)


def test_launcher_indexes_uses_the_default_programdata_folder_when_it_is_unset(tmp_path):
    manifests = launcher_indexes("win32", {}, tmp_path).manifests
    assert manifests[0] == Path("C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests")


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
