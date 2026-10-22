from __future__ import annotations

import logging
import shlex
from pathlib import Path

import pytest

import constants
from constants import PriorityMode
from fakes import FakeTwitch
from settings import default_settings, setting_choices


def autostart_window(window, monkeypatch, home: Path, config: Path):
    """Return the window with HOME and XDG_CONFIG_HOME set to these folders."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    fake = FakeTwitch()
    fake.settings.logging_level = logging.ERROR
    return window(fake)


def exec_arguments(entry: Path) -> list[str]:
    """Return the arguments of the command that the Exec line of a desktop entry runs through `sh -c`."""
    exec_line = next(line for line in entry.read_text(encoding="utf8").splitlines() if line.startswith("Exec="))
    shell, option, command = shlex.split(exec_line.removeprefix("Exec="))
    assert (shell, option) == ("sh", "-c")
    return shlex.split(command)


@pytest.mark.parametrize(
    ("key", "names", "stored", "default"),
    [
        ("refresh_interval", "REFRESH_INTERVALS", 3, 2),
        ("restart_delay", "RESTART_DELAYS", 7, 30),
        ("priority_mode", "PRIORITY_MODES", "unknown mode", PriorityMode.LOW_AVBL_FIRST),
    ],
)
def test_the_settings_tab_replaces_a_value_outside_its_list_with_the_default_of_settings_py(
    window, monkeypatch, key, names, stored, default
):
    monkeypatch.setitem(default_settings, key, default)
    fake = FakeTwitch()
    setattr(fake.settings, key, stored)

    panel = window(fake).settings

    assert getattr(fake.settings, key) == default
    assert panel._vars[key].get() == getattr(panel, names)[default]


@pytest.mark.parametrize(
    ("key", "names", "choices"),
    [
        ("refresh_interval", "REFRESH_INTERVALS", (0, 3, 7)),
        ("restart_delay", "RESTART_DELAYS", (20, 0)),
        ("priority_mode", "PRIORITY_MODES", (PriorityMode.ENDING_SOONEST, PriorityMode.PRIORITY_ONLY)),
    ],
)
def test_the_settings_tab_offers_the_choices_of_settings_py_in_their_order(window, monkeypatch, key, names, choices):
    monkeypatch.setitem(setting_choices, key, choices)
    fake = FakeTwitch()
    setattr(fake.settings, key, choices[0])

    panel = window(fake).settings

    assert list(getattr(panel, names)) == list(choices)


def test_checking_autostart_creates_the_autostart_folder_with_an_entry_that_starts_the_source_with_python(
    window, monkeypatch, tmp_path
):
    gui = autostart_window(window, monkeypatch, tmp_path / "home", tmp_path / "config")
    gui.settings._vars["autostart"].set(1)
    gui.settings.update_autostart()

    entry = tmp_path / "config" / "autostart" / "TwitchDropsMiner.desktop"
    assert exec_arguments(entry) == [str(constants.SCRIPTS_PATH / "python"), str(constants.SELF_PATH.resolve())]
    assert gui.settings._query_autostart() is True
    assert not (tmp_path / "home").exists()


def test_unchecking_autostart_removes_the_entry(window, monkeypatch, tmp_path):
    gui = autostart_window(window, monkeypatch, tmp_path / "home", tmp_path / "config")
    gui.settings._vars["autostart"].set(1)
    gui.settings.update_autostart()
    gui.settings._vars["autostart"].set(0)
    gui.settings.update_autostart()

    assert list((tmp_path / "config" / "autostart").iterdir()) == []
    assert gui.settings._query_autostart() is False


def test_an_autostart_entry_that_cannot_be_written_is_reported_in_the_output_box_and_the_box_unchecked(
    window, monkeypatch, tmp_path
):
    # a file where the config folder would be, so that no folder can be created there
    blocker = tmp_path / "file"
    blocker.write_text("")
    gui = autostart_window(window, monkeypatch, tmp_path / "home", blocker / "config")
    gui.settings._vars["autostart"].set(1)
    gui.settings.update_autostart()

    last = gui.output._text.get("1.0", "end-1c").splitlines()[-1].partition(": ")[2]
    assert last.startswith("ERROR: Could not change the autostart entry: ")
    assert gui.settings._vars["autostart"].get() == 0
    assert not (tmp_path / "home").exists()
