from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from yarl import URL

from constants import PriorityMode
from utils import json_load, json_save, merge_json


def test_saved_values_of_each_stored_type_load_back_equal(tmp_path):
    path = tmp_path / "data.json"
    contents = {
        "when": datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc),
        "names": {"Rust"},
        "mode": PriorityMode.ENDING_SOONEST,
        "proxy": URL("http://127.0.0.1:8888"),
        "plain": [1, "two", None, True],
    }

    json_save(path, contents)

    assert json_load(path, {}, merge=False) == contents


def test_a_naive_datetime_is_saved_as_utc(tmp_path):
    path = tmp_path / "data.json"

    json_save(path, {"when": datetime(2026, 10, 23, 12, 0)})

    assert json_load(path, {}, merge=False) == {"when": datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)}


def test_json_save_writes_an_indent_of_4_and_leaves_no_new_file(tmp_path):
    path = tmp_path / "data.json"

    json_save(path, {"b": 1, "a": [2]})

    assert path.read_text(encoding="utf8") == '{\n    "b": 1,\n    "a": [\n        2\n    ]\n}'
    assert [file.name for file in tmp_path.iterdir()] == ["data.json"]


def test_json_save_sorts_the_keys_on_request(tmp_path):
    path = tmp_path / "data.json"

    json_save(path, {"b": 1, "a": 2}, sort=True)

    assert list(json.loads(path.read_text(encoding="utf8"))) == ["a", "b"]


def test_json_save_of_a_type_json_cannot_hold_raises_type_error_and_keeps_the_old_file(tmp_path):
    path = tmp_path / "data.json"
    json_save(path, {"count": 1})

    with pytest.raises(TypeError):
        json_save(path, {"count": object()})

    assert json.loads(path.read_text(encoding="utf8")) == {"count": 1}


def test_json_load_without_a_file_returns_a_copy_of_the_defaults_and_writes_nothing(tmp_path):
    defaults = {"count": 5}

    loaded = json_load(tmp_path / "data.json", defaults)

    assert loaded == defaults and loaded is not defaults
    assert list(tmp_path.iterdir()) == []


def test_json_load_reads_the_new_file_in_place_of_the_old_one(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"count": 1}', encoding="utf8")
    (tmp_path / "data.json.new").write_text('{"count": 2}', encoding="utf8")

    assert json_load(path, {"count": 0}) == {"count": 2}


def test_json_load_deletes_a_new_file_that_is_not_json_and_reads_the_old_one(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"count": 1}', encoding="utf8")
    # json.dump writes the closing brace last, so a write that the disk cut off leaves a file like this
    (tmp_path / "data.json.new").write_text('{"count": ', encoding="utf8")

    assert json_load(path, {"count": 0}) == {"count": 1}
    assert [file.name for file in tmp_path.iterdir()] == ["data.json"]


def test_json_load_of_a_file_that_is_not_json_raises_json_decode_error(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{", encoding="utf8")

    with pytest.raises(json.JSONDecodeError):
        json_load(path, {})


def test_json_load_drops_a_value_of_an_unknown_type_and_merges_the_default_back(tmp_path):
    path = tmp_path / "data.json"
    unknown = {"__type": "Removed", "data": 1}
    path.write_text(json.dumps({"mode": unknown, "nested": {"value": unknown}}), encoding="utf8")
    defaults = {"mode": PriorityMode.PRIORITY_ONLY, "nested": {"flag": True}}

    assert json_load(path, defaults) == defaults
    assert json_load(path, defaults, merge=False) == {}


def test_json_load_without_merge_returns_the_file_as_it_is(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"other": "x"}', encoding="utf8")

    assert json_load(path, {"count": 5}, merge=False) == {"other": "x"}


def test_merge_json_removes_unknown_keys_replaces_other_types_and_adds_missing_keys():
    obj = {"unknown": 1, "count": "five", "names": ["a"], "nested": {"level": 2, "extra": True}}

    merge_json(obj, {"count": 5, "names": [], "nested": {"level": 1, "flag": False}, "added": "x"})

    assert obj == {"count": 5, "names": ["a"], "nested": {"level": 2, "flag": False}, "added": "x"}


@pytest.mark.parametrize("value, default", [(True, 5), (1, True), (1, 1.5), ({"a": 1}, [])])
def test_merge_json_replaces_a_value_whose_type_is_not_exactly_that_of_the_default(value, default):
    obj = {"key": value}

    merge_json(obj, {"key": default})

    assert obj == {"key": default}


def test_merge_json_with_an_empty_template_removes_every_key():
    obj = {"a": 1, "b": {"c": 2}}

    merge_json(obj, {})

    assert obj == {}
