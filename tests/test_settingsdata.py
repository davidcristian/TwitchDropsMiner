from settingsdata import drop_non_text_items


def test_drop_non_text_items_removes_a_number_from_a_set():
    settings = {"exclude": {2, "x"}}
    assert drop_non_text_items(settings) == [("exclude", 2)]
    assert settings == {"exclude": {"x"}}


def test_drop_non_text_items_keeps_the_order_of_the_strings_in_a_list():
    settings = {"priority": ["b", 3, "a", None, "c"]}
    assert drop_non_text_items(settings) == [("priority", 3), ("priority", None)]
    assert settings["priority"] == ["b", "a", "c"]


def test_drop_non_text_items_removes_a_nested_list_and_a_bool():
    settings = {"game_dirs": [["C:/Games"], "/games"], "detected_games": [True, "Detected"]}
    removed = drop_non_text_items(settings)
    assert removed == [("game_dirs", ["C:/Games"]), ("detected_games", True)]
    assert settings == {"game_dirs": ["/games"], "detected_games": ["Detected"]}


def test_drop_non_text_items_leaves_an_empty_value_of_the_same_type():
    settings = {"exclude": {1, 2}, "priority": [1.5]}
    removed = drop_non_text_items(settings)
    assert sorted(item for _, item in removed) == [1, 1.5, 2]
    assert settings == {"exclude": set(), "priority": []}
    assert type(settings["exclude"]) is set


def test_drop_non_text_items_does_not_change_the_list_it_replaces():
    shared = ["Game", 7]
    settings = {"priority": shared}
    drop_non_text_items(settings)
    assert shared == ["Game", 7]
    assert settings["priority"] == ["Game"]


def test_drop_non_text_items_leaves_values_that_are_not_lists_or_sets():
    settings = {"language": "English", "refresh_interval": 5, "dark_mode": False, "proxy": {"a": 1}}
    assert drop_non_text_items(settings) == []
    assert settings == {"language": "English", "refresh_interval": 5, "dark_mode": False, "proxy": {"a": 1}}


def test_drop_non_text_items_keeps_a_list_of_strings_as_the_same_object():
    priority = ["A", "B*"]
    settings = {"priority": priority, "exclude": set()}
    assert drop_non_text_items(settings) == []
    assert settings["priority"] is priority
    assert settings["exclude"] == set()


def test_drop_non_text_items_of_no_settings_removes_nothing():
    assert drop_non_text_items({}) == []
