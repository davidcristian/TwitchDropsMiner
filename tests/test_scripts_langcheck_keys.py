from __future__ import annotations

import pytest

import langcheck
from gitrepo import make_repo
from sources import Problem

ENGLISH = {"status": {"idle": "Idle", "watching": "Watching: {channel}"}, "name": "English"}
TRANSLATE = f"default_translation: Translation = {ENGLISH!r}\n"


def test_unread_keys_yields_nothing_for_the_english_keys_and_fewer():
    assert list(langcheck.unread_keys({"status": {"idle": "Bezczynny"}, "name": "Polski"}, ENGLISH)) == []


def test_unread_keys_yields_an_unknown_key_at_any_depth_once_without_its_children():
    data = {"gone": {"a": "x", "b": "y"}, "status": {"idle": "x", "old": "y"}}
    assert list(langcheck.unread_keys(data, ENGLISH)) == [
        (("gone",), "is a key that the app does not read"),
        (("status", "old"), "is a key that the app does not read"),
    ]


@pytest.mark.parametrize(
    ("value", "found"),
    [
        ({"idle": "x"}, "an object"),
        (["x"], "a list"),
        (3, "a number"),
        (1.5, "a number"),
        (True, "true or false"),
        (None, "null"),
    ],
)
def test_unread_keys_yields_a_value_of_another_type_than_the_english_string(value, found):
    assert list(langcheck.unread_keys({"name": value}, ENGLISH)) == [
        (("name",), f"is {found} where English has a string, so the app does not read it")
    ]


def test_unread_keys_yields_a_string_where_english_has_an_object():
    assert list(langcheck.unread_keys({"status": "Idle"}, ENGLISH)) == [
        (("status",), "is a string where English has an object, so the app does not read it")
    ]


@pytest.mark.parametrize(
    ("data", "count"),
    [
        ({"status": {"idle": "x", "watching": "{channel}"}, "name": "Polski"}, 0),
        ({"status": {"idle": "x"}, "name": "Polski", "extra": "y"}, 1),
        ({}, 3),
        ({"status": "x", "name": "Polski"}, 2),
        ({"status": {"idle": 1, "watching": None}, "name": ["x"]}, 3),
    ],
)
def test_missing_strings_counts_each_english_string_that_is_not_a_string_at_its_keys(data, count):
    assert langcheck.missing_strings(data, ENGLISH) == count


def test_lang_problems_sorts_the_key_and_field_problems_by_line():
    text = '{\n  "status": {\n    "watching": "{kanal}",\n    "old": "x"\n  },\n  "gone": "y"\n}\n'
    assert langcheck.lang_problems("lang/x.json", text, ENGLISH) == [
        Problem("lang/x.json", 3, "status.watching has the field {kanal}, which the English string lacks"),
        Problem("lang/x.json", 4, "status.old is a key that the app does not read"),
        Problem("lang/x.json", 6, "gone is a key that the app does not read"),
    ]


def test_lang_problems_checks_only_the_json_without_the_english_strings():
    assert langcheck.lang_problems("lang/x.json", '{"gone": "{x}"}', None) == []
    assert langcheck.lang_problems("lang/x.json", "[]", None) == [Problem("lang/x.json", 1, "is not a JSON object")]


def test_parse_language_returns_the_data_or_the_problem():
    assert langcheck.parse_language("lang/x.json", '{"a": "b"}') == {"a": "b"}
    assert langcheck.parse_language("lang/x.json", '"a"') == Problem("lang/x.json", 1, "is not a JSON object")


def test_check_fails_on_a_key_the_app_does_not_read_and_counts_the_missing_strings(tmp_path):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE,
        "lang/Polski.json": '{\n  "gui": {\n    "invalidate": "x"\n  },\n  "name": "Polski"\n}\n',
        "lang/Dansk.json": '{"status": {"idle": "x", "watching": "{channel}"}, "name": "Dansk"}',
        "lang/Bad.json": "{",
    })
    assert langcheck.check(root) == (
        3,
        [
            Problem("lang/Bad.json", 1, "is not valid JSON: Expecting property name enclosed in double quotes"),
            Problem("lang/Polski.json", 2, "gui is a key that the app does not read"),
        ],
        {"lang/Dansk.json": 0, "lang/Polski.json": 2},
    )
