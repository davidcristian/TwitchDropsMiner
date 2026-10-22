from __future__ import annotations

import logging
import plistlib

import pytest

from autostart import (
    DesktopFile,
    LaunchAgent,
    RegistryValue,
    autostart_command,
    autostart_entry,
    source_python,
    xdg_autostart_folder,
)


@pytest.mark.parametrize(("platform", "name"), [("win32", "pythonw"), ("linux", "python"), ("darwin", "python")])
def test_source_python_is_pythonw_only_on_windows(tmp_path, platform, name):
    assert source_python(tmp_path / "env" / "bin", platform) == tmp_path / "env" / "bin" / name


def test_a_packaged_command_is_the_quoted_app_path(tmp_path):
    app = tmp_path / "My Apps" / "TwitchDropsMiner.AppImage"

    assert autostart_command(app, logging.ERROR, False, None) == f'"{app}"'


def test_a_source_command_starts_the_quoted_main_py_with_the_python_of_the_virtual_environment(tmp_path):
    python, main = tmp_path / "env" / "bin" / "python", tmp_path / "main.py"

    assert autostart_command(main, logging.ERROR, False, python) == f'"{python}" "{main}"'


@pytest.mark.parametrize(
    ("level", "tray", "flags"),
    [
        (logging.WARNING, False, " -v"),
        (logging.INFO, True, " -vv --tray"),
        (logging.DEBUG, False, " -vvvv"),
        (logging.ERROR, True, " --tray"),
        (logging.CRITICAL, False, ""),
    ],
)
def test_a_command_adds_a_v_for_each_step_of_the_logging_level_then_the_tray_flag(tmp_path, level, tray, flags):
    assert autostart_command(tmp_path, level, tray, None) == f'"{tmp_path}"{flags}'


def test_the_xdg_autostart_folder_is_in_xdg_config_home_also_before_it_exists(tmp_path):
    config = tmp_path / "config"

    assert xdg_autostart_folder({"XDG_CONFIG_HOME": str(config)}, tmp_path / "home") == config / "autostart"


@pytest.mark.parametrize("environ", [{}, {"XDG_CONFIG_HOME": ""}, {"XDG_CONFIG_HOME": "config"}])
def test_the_xdg_autostart_folder_is_in_the_home_folder_without_an_absolute_xdg_config_home(tmp_path, environ):
    assert xdg_autostart_folder(environ, tmp_path) == tmp_path / ".config" / "autostart"


def test_each_system_has_its_own_autostart_entry(tmp_path):
    environ = {"XDG_CONFIG_HOME": str(tmp_path / "config")}
    linux, macos = autostart_entry("linux", environ, tmp_path), autostart_entry("darwin", environ, tmp_path)

    assert isinstance(autostart_entry("win32", environ, tmp_path), RegistryValue)
    assert isinstance(linux, DesktopFile)
    assert linux.path == tmp_path / "config" / "autostart" / "TwitchDropsMiner.desktop"
    assert isinstance(macos, LaunchAgent)
    assert macos.path == tmp_path / "Library" / "LaunchAgents" / "com.devilxd.twitchdropsminer.plist"


def test_a_desktop_file_is_written_with_its_folders_and_found_by_the_app_path(tmp_path):
    main = tmp_path / "My Apps" / "main.py"
    entry = DesktopFile(tmp_path / "config" / "autostart" / "TwitchDropsMiner.desktop")
    entry.write(autostart_command(main, logging.ERROR, True, None))

    assert f"""Exec=sh -c '"{main}" --tray'""" in entry.path.read_text(encoding="utf8").splitlines()
    assert entry.contains(main)
    assert not entry.contains(tmp_path / "main.py")


def test_writing_a_desktop_file_replaces_the_command_of_an_older_entry(tmp_path):
    main = tmp_path / "main.py"
    entry = DesktopFile(tmp_path / "TwitchDropsMiner.desktop")
    entry.write(autostart_command(main, logging.ERROR, False, tmp_path / "pythonw"))
    entry.write(autostart_command(main, logging.ERROR, False, tmp_path / "python"))

    assert "pythonw" not in entry.path.read_text(encoding="utf8")


def test_a_removed_desktop_file_is_not_found_and_removing_it_again_does_nothing(tmp_path):
    entry = DesktopFile(tmp_path / "TwitchDropsMiner.desktop")
    entry.write(autostart_command(tmp_path / "main.py", logging.ERROR, False, None))
    entry.remove()
    entry.remove()

    assert not entry.path.exists()
    assert not entry.contains(tmp_path / "main.py")


def test_a_desktop_file_under_a_file_is_not_found_and_cannot_be_written(tmp_path):
    (tmp_path / "file").write_text("")
    entry = DesktopFile(tmp_path / "file" / "autostart" / "TwitchDropsMiner.desktop")

    assert not entry.contains(tmp_path / "main.py")
    with pytest.raises(OSError):
        entry.write(autostart_command(tmp_path / "main.py", logging.ERROR, False, None))


def test_a_launch_agent_runs_the_split_command_at_load_and_is_found_by_the_app_path(tmp_path):
    python, main = tmp_path / "env" / "bin" / "python", tmp_path / "My Apps" / "main.py"
    entry = LaunchAgent(tmp_path / "Library" / "LaunchAgents" / "com.devilxd.twitchdropsminer.plist")
    entry.write(autostart_command(main, logging.ERROR, True, python))

    with entry.path.open("rb") as file:
        assert plistlib.load(file) == {
            "Label": "com.devilxd.twitchdropsminer",
            "ProgramArguments": [str(python), str(main), "--tray"],
            "RunAtLoad": True,
        }
    assert entry.contains(main)
    entry.remove()
    assert not entry.contains(main)
