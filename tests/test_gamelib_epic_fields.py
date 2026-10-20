import json

import pytest

from gamelib import LauncherIndexes, LocalGame, Platform, ScanResult, scan_epic

NO_LAUNCHER_INDEXES = LauncherIndexes((), ())


def scan(directory):
    result = ScanResult()
    scan_epic(directory, result, NO_LAUNCHER_INDEXES)
    return result


@pytest.mark.parametrize("value", [None, 7, ["Rocket League"]], ids=["null", "number", "list"])
def test_scan_epic_skips_a_manifest_whose_display_name_is_not_text(tmp_path, epic_manifest, value):
    epic_manifest(tmp_path, "Fortnite", "Fortnite")
    epic_manifest(tmp_path, "Rocket League", "Sugar", DisplayName=value)
    assert [game.name for game in scan(tmp_path).games] == ["Fortnite"]


def test_scan_epic_keeps_a_game_whose_main_game_app_name_is_null(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Rocket League", "Sugar", MainGameAppName=None, InstallLocation=None)
    assert scan(tmp_path).games == [LocalGame("Rocket League", Platform.EPIC, None, "Sugar")]


def test_scan_epic_reads_a_null_app_name_as_missing(tmp_path, epic_manifest):
    epic_manifest(tmp_path, "Rocket League", "Sugar", AppName=None, MainGameAppName="Sugar")
    assert [(game.name, game.app_id) for game in scan(tmp_path).games] == [("Rocket League", "")]


def test_scan_epic_reads_null_legendary_fields_as_missing(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({
        "Sugar": {"title": None, "install_path": "/games/Sugar"},
        "Fortnite": {"title": "Fortnite", "install_path": None},
    }), encoding="utf-8")
    assert scan(tmp_path).games == [LocalGame("Fortnite", Platform.EPIC, None, "Fortnite")]


def test_scan_epic_skips_a_legendary_dlc_and_keeps_its_game(tmp_path):
    (tmp_path / "installed.json").write_text(json.dumps({
        "Fortnite": {"title": "Fortnite", "is_dlc": False},
        "FortniteSTW": {"title": "Fortnite Save the World", "is_dlc": True},
        "Sugar": {"title": "Rocket League"},
    }), encoding="utf-8")
    assert [game.name for game in scan(tmp_path).games] == ["Fortnite", "Rocket League"]
