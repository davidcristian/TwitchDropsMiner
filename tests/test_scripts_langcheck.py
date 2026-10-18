from __future__ import annotations

import langcheck
from gitrepo import make_repo
from sources import Problem


def test_lang_problems_returns_nothing_for_a_json_object():
    assert langcheck.lang_problems("lang/Polski.json", '{"gui": {"tab": "Karta"}}') == []


def test_lang_problems_reports_invalid_json_at_the_line_of_the_error():
    text = '{\n  "a": "b",\n  "c": \n}\n'
    assert langcheck.lang_problems("lang/x.json", text) == [
        Problem("lang/x.json", 4, "is not valid JSON: Expecting value")
    ]


def test_lang_problems_reports_json_that_is_not_an_object():
    assert langcheck.lang_problems("lang/x.json", '["a", "b"]') == [Problem("lang/x.json", 1, "is not a JSON object")]


def test_lang_problems_reports_an_empty_file_as_invalid_json():
    assert langcheck.lang_problems("lang/x.json", "") == [
        Problem("lang/x.json", 1, "is not valid JSON: Expecting value")
    ]


def test_check_reads_only_the_json_files_in_lang(tmp_path):
    root = make_repo(tmp_path, {
        "lang/Good.json": "{}",
        "lang/Bad.json": "[1]",
        "lang/README.md": "not json",
        "settings.json": "not json",
    })
    assert langcheck.check(root) == (2, [Problem("lang/Bad.json", 1, "is not a JSON object")])


def test_check_counts_and_reports_a_language_file_that_is_not_utf8(tmp_path):
    root = make_repo(tmp_path, {"lang/Latin.json": '{"a": "caf\u00e9"}'.encode("latin-1")})
    assert langcheck.check(root) == (1, [Problem("lang/Latin.json", 1, "is not UTF-8 text")])


def test_check_skips_a_language_file_that_git_ignores(tmp_path):
    root = make_repo(tmp_path, {".gitignore": "lang/English.json\n", "lang/English.json": "["})
    assert langcheck.check(root) == (0, [])


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {"lang/Bad.json": "[]"})
    assert langcheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == "lang/Bad.json:1: is not a JSON object\nlangcheck: 1 files, 1 problems\n"


def test_main_returns_0_when_every_language_file_is_an_object(tmp_path, capsys):
    root = make_repo(tmp_path, {"lang/A.json": "{}", "lang/B.json": '{"x": 1}'})
    assert langcheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "langcheck: 2 files, 0 problems\n"
