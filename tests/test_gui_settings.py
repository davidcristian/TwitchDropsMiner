from __future__ import annotations

import pytest

from constants import PriorityMode
from fakes import FakeTwitch
from settings import default_settings, setting_choices


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
