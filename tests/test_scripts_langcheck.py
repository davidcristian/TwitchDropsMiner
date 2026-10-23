from __future__ import annotations

import pytest

import langcheck
from gitrepo import make_repo
from sources import Problem

ENGLISH = {"error": {"no_connection": "Retrying in {seconds} s ({url})"}, "gui": {"idle": "Idle"}}
TRANSLATE = 'default_translation: Translation = {"error": {"no_connection": "Retrying in {seconds} s ({url})"}}\n'


def test_lang_problems_returns_nothing_for_a_json_object_with_english_keys():
    assert langcheck.lang_problems("lang/Polski.json", '{"gui": {"idle": "Bezczynny"}}', ENGLISH) == []


def test_lang_problems_reports_invalid_json_at_the_line_of_the_error():
    text = '{\n  "a": "b",\n  "c": \n}\n'
    assert langcheck.lang_problems("lang/x.json", text, ENGLISH) == [
        Problem("lang/x.json", 4, "is not valid JSON: Expecting value")
    ]


def test_lang_problems_reports_json_that_is_not_an_object():
    assert langcheck.lang_problems("lang/x.json", '["a", "b"]', ENGLISH) == [
        Problem("lang/x.json", 1, "is not a JSON object")
    ]


def test_lang_problems_reports_an_empty_file_as_invalid_json():
    assert langcheck.lang_problems("lang/x.json", "", ENGLISH) == [
        Problem("lang/x.json", 1, "is not valid JSON: Expecting value")
    ]


def test_lang_problems_reports_a_field_the_english_string_lacks_at_the_line_of_its_key():
    text = '{\n  "error": {\n    "no_connection": "Coba lagi dalam {detik} detik ({url})"\n  }\n}\n'
    assert langcheck.lang_problems("lang/Indonesian.json", text, ENGLISH) == [
        Problem("lang/Indonesian.json", 3, "error.no_connection has the field {detik}, which the English string lacks")
    ]


@pytest.mark.parametrize("value", ["{url} {seconds}", "{seconds!r:>3}", "no fields", "{{literal}} {url}"])
def test_lang_problems_accepts_the_english_fields_in_any_order_and_any_subset(value):
    assert langcheck.lang_problems("lang/x.json", f'{{"error": {{"no_connection": "{value}"}}}}', ENGLISH) == []


def test_lang_problems_reports_each_extra_field_sorted_by_name():
    text = '{"error": {"no_connection": "{seconds} {b} {} {a}"}}'
    assert [problem.message for problem in langcheck.lang_problems("lang/x.json", text, ENGLISH)] == [
        "error.no_connection has the field {}, which the English string lacks",
        "error.no_connection has the field {a}, which the English string lacks",
        "error.no_connection has the field {b}, which the English string lacks",
    ]


def test_lang_problems_reports_a_field_in_a_string_whose_english_has_none():
    assert langcheck.lang_problems("lang/x.json", '{"gui": {"idle": "{state}"}}', ENGLISH) == [
        Problem("lang/x.json", 1, "gui.idle has the field {state}, which the English string lacks")
    ]


def test_lang_problems_reports_a_lone_brace_in_a_template():
    assert langcheck.lang_problems("lang/x.json", '{"error": {"no_connection": "{seconds}}"}}', ENGLISH) == [
        Problem(
            "lang/x.json", 1, "error.no_connection is not a str.format template: Single '}' encountered in format string"
        )
    ]


def test_lang_problems_accepts_a_lone_brace_in_a_string_whose_english_has_no_field():
    assert langcheck.lang_problems("lang/x.json", '{"gui": {"idle": "{ idle"}}', ENGLISH) == []


def test_lang_problems_checks_no_field_of_a_key_or_a_value_type_english_does_not_have():
    text = '{"error": {"other": "{x}", "no_connection": 5}, "gui": {"idle": {"nested": "{x}"}}}'
    assert [problem.message for problem in langcheck.lang_problems("lang/x.json", text, ENGLISH)] == [
        "error.other is a key that the app does not read",
        "error.no_connection is a number where English has a string, so the app does not read it",
        "gui.idle is an object where English has a string, so the app does not read it",
    ]


@pytest.mark.parametrize(
    ("template", "fields"),
    [
        ("plain text", set()),
        ("{a} and {b}", {"a", "b"}),
        ("{a!r:>{width}} {c.attr} {d[0]}", {"a", "width", "c.attr", "d[0]"}),
        ("{} {0}", {"", "0"}),
        ("{{not a field}}", set()),
    ],
)
def test_format_fields_returns_every_field_name_with_those_in_a_format_spec(template, fields):
    assert langcheck.format_fields(template) == fields


@pytest.mark.parametrize("template", ["{open", "close}", "{a!}", "{a!x}"])
def test_format_fields_raises_value_error_where_str_format_does(template):
    with pytest.raises(ValueError):
        template.format(open=1, a=1)
    with pytest.raises(ValueError):
        langcheck.format_fields(template)


def test_english_strings_reads_the_annotated_dict_literal_and_its_joined_strings():
    source = (
        "﻿other: dict = {'a': '{x}'}\n"
        "default_translation: Translation = {\n"
        "    'status': {'watching': 'Watching: {channel}', 'idle': ('Idle, ' 'waiting {n}')},\n"
        "    'name': 'English',\n"
        "}\n"
    )
    assert langcheck.english_strings(source) == {
        "status": {"watching": "Watching: {channel}", "idle": "Idle, waiting {n}"},
        "name": "English",
    }


def test_english_fields_gives_each_string_its_fields_and_leaves_out_one_str_format_cannot_read():
    english = {"status": {"watching": "Watching: {channel}", "count": 3}, "name": "English", "broken": "{"}
    assert langcheck.english_fields(english) == {("status", "watching"): {"channel"}, ("name",): set()}


@pytest.mark.parametrize(
    "source",
    [
        "x = 1\n",
        "default_translation = {'a': 'b'}\n",
        "default_translation: Translation\n",
        "default_translation: Translation = dict(a='b')\n",
        "default_translation: Translation = ['a']\n",
        "default_translation: Translation = {\n",
    ],
)
def test_english_strings_returns_none_without_an_annotated_dict_literal(source):
    assert langcheck.english_strings(source) is None


def test_key_lines_gives_a_name_repeated_at_two_depths_the_line_of_each():
    text = '{\n  "tabs": {"inventory": "x", "status": "y"},\n  "inventory" : {\n    "status": {\n      "idle": "z"\n  }}\n}'
    assert langcheck.key_lines(text) == {
        ("tabs",): 2,
        ("tabs", "inventory"): 2,
        ("tabs", "status"): 2,
        ("inventory",): 3,
        ("inventory", "status"): 4,
        ("inventory", "status", "idle"): 5,
    }


def test_key_lines_reads_brackets_and_quotes_inside_a_string_as_text():
    text = '{\n  "a": "{\\"b\\": [",\n  "c\\\\": "}",\n  "d": 1\n}'
    assert langcheck.key_lines(text) == {("a",): 2, ("c\\",): 3, ("d",): 4}


def test_key_lines_decodes_an_escaped_key_and_keeps_the_last_of_a_repeated_one():
    text = '{\n  "\\u0061": "x",\n  "b": [{"c": 1}],\n  "a": "y"\n}'
    assert langcheck.key_lines(text) == {("a",): 4, ("b",): 3, ("b", "", "c"): 3}


def test_check_reads_only_the_json_files_in_lang(tmp_path):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE,
        "lang/Good.json": "{}",
        "lang/Bad.json": "[1]",
        "lang/README.md": "not json",
        "settings.json": "not json",
    })
    assert langcheck.check(root) == (2, [Problem("lang/Bad.json", 1, "is not a JSON object")], {"lang/Good.json": 1})


def test_check_compares_the_fields_with_default_translation_in_translate_english_py(tmp_path):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE,
        "lang/Indonesian.json": '{"error": {"no_connection": "{detik} detik ({url})"}}',
        "lang/Polski.json": '{"error": {"no_connection": "{seconds} s ({url})"}}',
    })
    message = "error.no_connection has the field {detik}, which the English string lacks"
    assert langcheck.check(root) == (
        2, [Problem("lang/Indonesian.json", 1, message)], {"lang/Indonesian.json": 0, "lang/Polski.json": 0}
    )


@pytest.mark.parametrize("translate", [None, "default_translation = {}\n", b"\xff\xfe"])
def test_check_reports_an_english_py_without_default_translation_and_checks_the_json(tmp_path, translate):
    files: dict[str, str | bytes] = {"lang/Bad.json": "[1]", "lang/Good.json": '{"a": "{x}"}'}
    if translate is not None:
        files["translate/english.py"] = translate
    root = make_repo(tmp_path, files)
    assert langcheck.check(root) == (2, [
        Problem("translate/english.py", 1, "has no default_translation dict literal to read the English strings from"),
        Problem("lang/Bad.json", 1, "is not a JSON object"),
    ], {})


def test_check_counts_and_reports_a_language_file_that_is_not_utf8(tmp_path):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE, "lang/Latin.json": '{"a": "café"}'.encode("latin-1")
    })
    assert langcheck.check(root) == (1, [Problem("lang/Latin.json", 1, "is not UTF-8 text")], {})


def test_check_skips_a_language_file_that_git_ignores(tmp_path):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE, ".gitignore": "lang/English.json\n", "lang/English.json": "["
    })
    assert langcheck.check(root) == (0, [], {})


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE, "lang/Bad.json": "[]", "lang/Old.json": '{"old": "x"}'
    })
    assert langcheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == (
        "lang/Bad.json:1: is not a JSON object\n"
        "lang/Old.json:1: old is a key that the app does not read\n"
        "langcheck: lang/Old.json lacks 1 strings, which show in English\n"
        "langcheck: 2 files, 2 problems\n"
    )


def test_main_prints_the_strings_each_file_lacks_and_returns_0_when_that_is_all(tmp_path, capsys):
    root = make_repo(tmp_path, {
        "translate/english.py": TRANSLATE, "lang/A.json": "{}", "lang/B.json": '{"error": {"no_connection": "{url}"}}'
    })
    assert langcheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == (
        "langcheck: lang/A.json lacks 1 strings, which show in English\n"
        "langcheck: lang/B.json lacks 0 strings, which show in English\n"
        "langcheck: 2 files, 0 problems\n"
    )
