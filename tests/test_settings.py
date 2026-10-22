from __future__ import annotations

import pytest

from settings import default_settings, setting_choices


@pytest.mark.parametrize("key", list(setting_choices))
def test_the_default_of_a_setting_with_a_drop_down_list_is_one_of_its_choices(key):
    assert default_settings[key] in setting_choices[key]
