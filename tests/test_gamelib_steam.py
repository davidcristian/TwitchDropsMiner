import pytest

from gamelib import LocalGame, Platform, ScanResult, scan_steam

DOCUMENTED_TOOL_APPIDS = (228980, 1070560, 1391110, 1628350, 1493710, 2180100, 2805730)


def write_library_index(index, libraries):
    entries = []
    for number, library in enumerate(libraries):
        # Steam writes each backslash of a path twice
        escaped = str(library).replace("\\", "\\\\")
        entries += [f'\t"{number}"', "\t{", f'\t\t"path"\t\t"{escaped}"', '\t\t"label"\t\t""', "\t}"]
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text("\n".join(['"libraryfolders"', "{", *entries, "}", ""]), encoding="utf-8")


def scan(directory):
    result = ScanResult()
    return scan_steam(directory, result), result


def names(result):
    return [game.name for game in result.games]


def test_scan_steam_reads_the_games_of_a_steam_root(tmp_path, steam_manifest):
    steamapps = tmp_path / "Steam" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2", "Portal 2")
    found, result = scan(tmp_path / "Steam")
    assert found
    assert result.games == [LocalGame("Portal 2", Platform.STEAM, steamapps / "common" / "Portal 2", "620")]
    assert result.libraries == [steamapps]


def test_scan_steam_reads_a_steamapps_folder_itself(tmp_path, steam_manifest):
    steamapps = tmp_path / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2")
    found, result = scan(steamapps)
    assert found
    assert names(result) == ["Portal 2"]
    assert result.libraries == [steamapps]


def test_scan_steam_finds_a_steamapps_folder_written_with_capitals(tmp_path, steam_manifest):
    steam_manifest(tmp_path / "Steam" / "SteamApps", 620, "Portal 2")
    found, result = scan(tmp_path / "Steam")
    assert found
    assert names(result) == ["Portal 2"]


def test_scan_steam_reads_the_library_above_a_common_folder(tmp_path, steam_manifest):
    steamapps = tmp_path / "Steam" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2", "Portal 2")
    write_library_index(steamapps / "libraryfolders.vdf", [tmp_path / "Steam"])
    (steamapps / "common" / "Portal 2").mkdir(parents=True)
    found, result = scan(steamapps / "common")
    assert found
    assert names(result) == ["Portal 2"]


def test_scan_steam_does_not_read_a_common_folder_without_a_library_index(tmp_path, steam_manifest):
    steamapps = tmp_path / "Steam" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2", "Portal 2")
    (steamapps / "common" / "Portal 2").mkdir(parents=True)
    found, result = scan(steamapps / "common")
    assert not found
    assert result == ScanResult()


def test_scan_steam_returns_false_for_a_folder_without_steam_files(tmp_path):
    (tmp_path / "Games" / "Rust").mkdir(parents=True)
    found, result = scan(tmp_path / "Games")
    assert not found
    assert result == ScanResult()


def test_scan_steam_follows_the_library_index_to_other_drives(tmp_path, steam_manifest):
    steamapps = tmp_path / "Steam" / "steamapps"
    other = tmp_path / "drive2" / "SteamLibrary" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2")
    steam_manifest(other, 570, "Dota 2")
    missing = tmp_path / "drive3" / "SteamLibrary"
    write_library_index(steamapps / "libraryfolders.vdf", [tmp_path / "Steam", other.parent, missing])
    found, result = scan(tmp_path / "Steam")
    assert found
    assert names(result) == ["Portal 2", "Dota 2"]
    assert result.libraries == [steamapps, other]


def test_scan_steam_reads_the_library_index_of_the_older_layout(tmp_path, steam_manifest):
    other = tmp_path / "drive2" / "steamapps"
    steam_manifest(tmp_path / "Steam" / "steamapps", 620, "Portal 2")
    steam_manifest(other, 570, "Dota 2")
    write_library_index(tmp_path / "Steam" / "config" / "libraryfolders.vdf", [other.parent])
    found, result = scan(tmp_path / "Steam")
    assert names(result) == ["Portal 2", "Dota 2"]


def test_scan_steam_reads_escaped_backslashes_in_library_paths(tmp_path, steam_manifest):
    # One folder with a backslash in its name on Linux, two folders on Windows
    other = tmp_path / "games\\drive2"
    steam_manifest(tmp_path / "Steam" / "steamapps", 620, "Portal 2")
    steam_manifest(other / "steamapps", 570, "Dota 2")
    write_library_index(tmp_path / "Steam" / "steamapps" / "libraryfolders.vdf", [other])
    found, result = scan(tmp_path / "Steam")
    assert names(result) == ["Portal 2", "Dota 2"]


def test_scan_steam_reads_a_library_listed_twice_once(tmp_path, steam_manifest):
    steamapps = tmp_path / "Steam" / "steamapps"
    other = tmp_path / "drive2" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2")
    steam_manifest(other, 570, "Dota 2")
    write_library_index(steamapps / "libraryfolders.vdf", [tmp_path / "Steam", other.parent, other.parent])
    found, result = scan(tmp_path / "Steam")
    assert names(result) == ["Portal 2", "Dota 2"]
    assert result.libraries == [steamapps, other]


def test_scan_steam_does_not_read_a_library_again_for_the_same_result(tmp_path, steam_manifest):
    steam_manifest(tmp_path / "Steam" / "steamapps", 620, "Portal 2")
    result = ScanResult()
    assert scan_steam(tmp_path / "Steam", result)
    assert scan_steam(tmp_path / "Steam" / "steamapps", result)
    assert names(result) == ["Portal 2"]


def test_scan_steam_keeps_the_first_value_of_a_repeated_key(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_620.acf").write_text(
        '"AppState"\n{\n\t"appid"\t"620"\n\t"name"\t"Portal 2"\n'
        '\t"Extra"\n\t{\n\t\t"appid"\t"1"\n\t\t"name"\t"Other"\n\t}\n}\n',
        encoding="utf-8",
    )
    found, result = scan(steamapps)
    assert [(game.name, game.app_id) for game in result.games] == [("Portal 2", "620")]


@pytest.mark.parametrize("app_id", DOCUMENTED_TOOL_APPIDS)
def test_scan_steam_skips_each_tool_app_id(tmp_path, steam_manifest, app_id):
    steam_manifest(tmp_path / "steamapps", app_id, "Runtime Tool")
    found, result = scan(tmp_path / "steamapps")
    assert found
    assert result.games == []


@pytest.mark.parametrize(
    "name",
    ["Proton 8.0", "PROTON EXPERIMENTAL", "Steam Linux Runtime 3.0 (sniper)", "Steamworks Common Redistributables"],
)
def test_scan_steam_skips_tools_by_the_start_of_their_name(tmp_path, steam_manifest, name):
    steam_manifest(tmp_path / "steamapps", 1, name)
    found, result = scan(tmp_path / "steamapps")
    assert result.games == []


def test_scan_steam_skips_a_manifest_without_a_name(tmp_path, steam_manifest):
    steamapps = tmp_path / "steamapps"
    steam_manifest(steamapps, 1, "")
    steam_manifest(steamapps, 2, "   ")
    (steamapps / "appmanifest_3.acf").write_text('"AppState"\n{\n\t"appid"\t"3"\n}\n', encoding="utf-8")
    steam_manifest(steamapps, 620, "Portal 2")
    found, result = scan(steamapps)
    assert names(result) == ["Portal 2"]


def test_scan_steam_keeps_a_game_without_an_install_folder(tmp_path, steam_manifest):
    steam_manifest(tmp_path / "steamapps", 620, "Portal 2")
    found, result = scan(tmp_path / "steamapps")
    assert result.games == [LocalGame("Portal 2", Platform.STEAM, None, "620")]


def test_scan_steam_keeps_a_game_without_an_app_id(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "appmanifest_620.acf").write_text('"AppState"\n{\n\t"name"\t"Portal 2"\n}\n', encoding="utf-8")
    found, result = scan(steamapps)
    assert result.games == [LocalGame("Portal 2", Platform.STEAM, None, "")]


def test_scan_steam_skips_a_manifest_that_cannot_be_read(tmp_path, steam_manifest):
    steamapps = tmp_path / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2")
    # a folder with a manifest's name is found by the scan, and reading it fails
    (steamapps / "appmanifest_570.acf").mkdir()
    found, result = scan(steamapps)
    assert names(result) == ["Portal 2"]


def test_scan_steam_reads_the_added_library_when_its_index_cannot_be_read(tmp_path, steam_manifest, unreadable):
    steamapps = tmp_path / "Steam" / "steamapps"
    steam_manifest(steamapps, 620, "Portal 2")
    write_library_index(steamapps / "libraryfolders.vdf", [tmp_path / "Steam"])
    unreadable(steamapps / "libraryfolders.vdf")
    found, result = scan(tmp_path / "Steam")
    assert found
    assert names(result) == ["Portal 2"]
    assert result.libraries == [steamapps]
