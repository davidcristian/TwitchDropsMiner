from __future__ import annotations

import asyncio
import logging
import shlex
import time
from pathlib import Path
from tkinter import Misc, ttk

import pytest

import constants
import ui.generalsettings as ui_generalsettings
from constants import PriorityMode
from fakedialog import FakeDialogs
from fakes import FakeTwitch
from folderpicker import FolderPicker
from gui import GUIManager
from settings import default_settings, setting_choices
from translate import default_translation


ENGLISH_LABEL = default_translation["gui"]["settings"]["general"]["language"]


class ScanningTwitch(FakeTwitch):
    """A fake `Twitch` that counts the game scans and the close requests of the window."""

    def __init__(self) -> None:
        super().__init__()
        self.scans = 0
        self.close_requests = 0

    async def detect_games(self) -> None:
        self.scans += 1

    def close(self) -> None:
        self.close_requests += 1


async def until(condition) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.01)


def folder_dialog_run(window, answer: str | None) -> tuple[ScanningTwitch, GUIManager, FakeDialogs, dict]:
    """Press the button that adds a game folder twice, run other tasks, then give the dialog an answer.

    With `answer` None, the window is closed while the dialog is open.
    """
    twitch = ScanningTwitch()
    gui = window(twitch)
    button = gui.settings._game_dir_add_button
    dialogs = FakeDialogs()
    gui.settings._folder_picker = FolderPicker(dialogs)
    seen: dict = {}

    async def scenario() -> None:
        ticks = 0

        async def tick() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.01)

        ticker = asyncio.create_task(tick())
        button.invoke()
        button.invoke()
        await until(lambda: ticks >= 20)
        seen["disabled while open"] = button.instate(["disabled"])
        seen["dialogs opened"] = len(dialogs.opened)
        if answer is None:
            gui.close()
        else:
            dialogs.opened[0].folder = answer
        await until(lambda: not button.instate(["disabled"]))
        # the scan task that a new folder starts runs on a later turn of the event loop
        await asyncio.sleep(0.05)
        ticker.cancel()

    asyncio.run(scenario())
    return twitch, gui, dialogs, seen


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


def label_texts(widget: Misc) -> list[str]:
    """Return the text of every label inside widget."""
    texts = []
    for child in widget.winfo_children():
        if isinstance(child, ttk.Label):
            texts.append(str(child.cget("text")))
        texts.extend(label_texts(child))
    return texts


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


def test_a_translated_language_label_starts_with_the_english_word(window, monkeypatch, other_language):
    strings = {"gui": {"settings": {"general": {"language": "Sprache (Neustart erforderlich): "}}}}
    monkeypatch.setattr(ui_generalsettings, "_", other_language(strings))

    gui = window(FakeTwitch())

    assert "Language / Sprache (Neustart erforderlich): " in label_texts(gui._root)


@pytest.mark.parametrize("strings", [None, {}])
def test_an_english_or_untranslated_language_label_shows_the_english_text_once(
    window, monkeypatch, other_language, strings
):
    if strings is not None:
        monkeypatch.setattr(ui_generalsettings, "_", other_language(strings))

    gui = window(FakeTwitch())

    labels = label_texts(gui._root)
    assert ENGLISH_LABEL in labels
    assert not any(text.startswith("Language / ") for text in labels)


def test_other_tasks_run_while_the_folder_dialog_is_open_and_the_chosen_folder_is_added(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, "/games/Steam")

    folder = str(Path("/games/Steam"))
    assert seen == {"disabled while open": True, "dialogs opened": 1}
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == [folder]
    assert gui.settings._game_dirs_list.get(0, "end") == (folder,)
    assert twitch.scans == 1


def test_a_cancelled_folder_dialog_adds_no_folder(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, "")

    assert seen == {"disabled while open": True, "dialogs opened": 1}
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == []
    assert gui.settings._game_dirs_list.get(0, "end") == ()
    assert twitch.scans == 0


def test_closing_the_window_closes_an_open_folder_dialog(window):
    twitch, gui, dialogs, seen = folder_dialog_run(window, None)

    assert twitch.close_requests == 1
    assert dialogs.opened[0].closed
    assert twitch.settings.game_dirs == []
    assert twitch.scans == 0
