from __future__ import annotations

import json
import logging
from argparse import Namespace

import pytest
from yarl import URL

import settings as settings_module
from constants import PriorityMode
from settings import Settings, default_settings, setting_choices
from utils import json_save

# the command line flags that main.py's ParsedArgs gives Settings
ARGS = Namespace(log=False, tray=True, dump=False, logging_level=logging.INFO, debug_ws=0, debug_gql=0)


@pytest.mark.parametrize("key", list(setting_choices))
def test_the_default_of_a_setting_with_a_drop_down_list_is_one_of_its_choices(key):
    assert default_settings[key] in setting_choices[key]


@pytest.fixture
def path(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", path)
    return path


def saved(path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def test_settings_without_a_file_have_the_defaults_and_write_nothing(path):
    settings = Settings(ARGS)
    settings.save()

    assert {key: getattr(settings, key) for key in default_settings} == default_settings
    assert list(path.parent.iterdir()) == []


def test_a_saved_file_loads_merged_with_the_defaults(path):
    json_save(path, {
        "refresh_interval": "five",
        "removed_setting": True,
        "exclude": {"Rust"},
        "proxy": URL("http://127.0.0.1:8888"),
        "priority_mode": PriorityMode.ENDING_SOONEST,
    })

    settings = Settings(ARGS)

    assert settings.refresh_interval == 5
    assert settings.exclude == {"Rust"} and isinstance(settings.exclude, set)
    assert settings.proxy == URL("http://127.0.0.1:8888")
    assert settings.priority_mode is PriorityMode.ENDING_SOONEST
    assert settings.restart_delay == default_settings["restart_delay"]
    with pytest.raises(AttributeError):
        settings.removed_setting


def test_items_that_are_not_text_are_removed_from_a_list_with_a_warning(path, caplog):
    json_save(path, {"priority": ["Rust", 5, "Dota 2"]})

    settings = Settings(ARGS)

    assert settings.priority == ["Rust", "Dota 2"]
    assert [record.getMessage() for record in caplog.records] == [
        "Removed 5 from priority in settings.json, because it is not text"
    ]


def test_a_flag_is_read_from_the_arguments_before_the_file(path):
    json_save(path, {"language": "Polski"})

    settings = Settings(Namespace(**vars(ARGS), language="Deutsch"))

    assert (settings.tray, settings.logging_level, settings.language) == (True, logging.INFO, "Deutsch")


def test_reading_a_name_that_is_neither_a_flag_nor_a_setting_raises_attribute_error(path):
    with pytest.raises(AttributeError):
        Settings(ARGS).unknown


def test_an_assigned_setting_is_saved_with_sorted_keys_and_loads_back(path):
    settings = Settings(ARGS)

    settings.dark_mode = True
    settings.save()

    assert saved(path)["dark_mode"] is True
    assert list(saved(path)) == sorted(default_settings)
    assert Settings(ARGS).dark_mode is True


def test_save_writes_only_after_a_change_unless_forced(path):
    settings = Settings(ARGS)
    settings.save()
    assert not path.exists()

    settings.save(force=True)

    assert saved(path)["refresh_interval"] == default_settings["refresh_interval"]


def test_alter_marks_a_list_changed_in_place_for_the_next_save(path):
    json_save(path, {"priority": []})
    settings = Settings(ARGS)
    settings.priority.append("Rust")
    settings.save()
    assert saved(path)["priority"] == []

    settings.alter()
    settings.save()

    assert saved(path)["priority"] == ["Rust"]


def test_a_failed_save_keeps_the_change_for_the_next_save(monkeypatch, tmp_path):
    folder = tmp_path / "missing"
    monkeypatch.setattr(settings_module, "SETTINGS_PATH", folder / "settings.json")
    settings = Settings(ARGS)
    settings.dark_mode = True

    with pytest.raises(OSError):
        settings.save()
    folder.mkdir()
    settings.save()

    assert saved(folder / "settings.json")["dark_mode"] is True


@pytest.mark.parametrize("name", ["tray", "unknown"])
def test_assigning_a_name_that_is_not_a_setting_raises_type_error(path, name):
    settings = Settings(ARGS)

    with pytest.raises(TypeError):
        setattr(settings, name, False)

    assert settings.tray is True


def test_deleting_a_setting_raises_runtime_error(path):
    settings = Settings(ARGS)

    with pytest.raises(RuntimeError):
        del settings.dark_mode

    assert settings.dark_mode is False
