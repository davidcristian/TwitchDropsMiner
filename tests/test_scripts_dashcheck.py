from __future__ import annotations

import pytest

import dashcheck
from gitrepo import make_repo
from sources import Problem

EM = "\u2014"
EN = "\u2013"
SPACED = "a spaced --; restructure the sentence"


def test_dash_problems_reports_an_em_dash_and_an_en_dash_on_any_line():
    text = f"one {EM} two\nyears 2010{EN}2020\nboth{EM}and{EN}\n"
    assert dashcheck.dash_problems("a.md", text) == [
        Problem("a.md", 1, "an em dash; restructure the sentence"),
        Problem("a.md", 2, "an en dash; restructure the sentence"),
        Problem("a.md", 3, "an em dash; restructure the sentence"),
        Problem("a.md", 3, "an en dash; restructure the sentence"),
    ]


@pytest.mark.parametrize(
    ("dash", "label"),
    [
        ("\u2012", "a figure dash"),
        ("\u2015", "a horizontal bar"),
        ("\u2e3a", "a two-em dash"),
        ("\u2e3b", "a three-em dash"),
        ("\ufe31", "a vertical em dash"),
        ("\ufe32", "a vertical en dash"),
        ("\ufe58", "a small em dash"),
    ],
)
def test_dash_problems_reports_the_other_unicode_dashes_by_name(dash, label):
    text = f"one\ntwo {dash} three\n"
    assert dashcheck.dash_problems("a.md", text) == [Problem("a.md", 2, f"{label}; restructure the sentence")]
    assert dashcheck.dash_problems("build.yml", text) == [Problem("build.yml", 2, f"{label}; restructure the sentence")]


@pytest.mark.parametrize(
    "line",
    ["2 \u00d7 5 \u2212 1", "a non\u2011breaking hyphen", "a well\u2010known name", "the scan ran - then it stopped"],
    ids=["minus sign", "non-breaking hyphen", "hyphen", "spaced hyphen"],
)
def test_dash_problems_ignores_a_minus_sign_a_hyphen_and_a_spaced_hyphen(line):
    assert dashcheck.dash_problems("a.md", line + "\n") == []


def test_dash_problems_reports_an_em_dash_in_code_too():
    text = f"x = 1\n```\ncode {EM} here\n```\n`span {EM}`\n"
    assert [problem.line for problem in dashcheck.dash_problems("a.md", text)] == [3, 5]
    source = f'x = "{EM}"\n'
    assert dashcheck.dash_problems("tool.py", source) == [Problem("tool.py", 1, "an em dash; restructure the sentence")]


def test_dash_problems_reports_a_spaced_double_hyphen_in_markdown_prose():
    assert dashcheck.dash_problems("a.md", "one\nthe check -- the first one\n") == [Problem("a.md", 2, SPACED)]


@pytest.mark.parametrize(
    "line",
    [
        "run `git log -- a.py` first",
        "the --root flag",
        "--root sets the folder",
        "a--b",
        "the end of a word--",
        "`a`-- b",
        "[link](x -- y.md)",
        "Title\n--",
        "---",
        "| --- | :--: |",
        "| -- | -- |",
    ],
    ids=[
        "code span", "flag", "flag at a line start", "unspaced", "unspaced at a line end", "after a code span",
        "link target", "heading underline", "horizontal rule", "table separator", "short table separator",
    ],
)
def test_dash_problems_ignores_a_double_hyphen_that_is_not_spaced_prose(line):
    assert dashcheck.dash_problems("a.md", line + "\n") == []


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_dash_problems_ignores_a_spaced_double_hyphen_in_a_fence(fence):
    text = f"one\n{fence}sh\ngit checkout -- a.py\n{fence}\n"
    assert dashcheck.dash_problems("a.md", text) == []


def test_dash_problems_reads_only_the_comments_and_docstrings_of_python_code():
    source = 'def f(a, b):\n    """Return a -- b."""\n    return a -- b  # minus -- minus\n'
    problems = dashcheck.dash_problems("tool.py", source)
    assert sorted(problems) == [Problem("tool.py", 2, SPACED), Problem("tool.py", 3, SPACED)]


def test_dash_problems_reads_every_line_of_a_txt_file():
    assert dashcheck.dash_problems("notes.txt", "a -- b\n") == [Problem("notes.txt", 1, SPACED)]


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("The check runs first --\nthen the build.\n", 1),
        ("The check runs first\n-- then the build.\n", 2),
        ("one\n`just check` -- then the build.\n", 2),
        ("`just check` --\nthen the build.\n", 1),
    ],
    ids=["end of a line", "start of a line", "after a code span at a line start", "after a code span at a line end"],
)
def test_dash_problems_reports_a_spaced_double_hyphen_at_a_line_break(text, line):
    assert dashcheck.dash_problems("a.md", text) == [Problem("a.md", line, SPACED)]


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("a.md", "To restore a file, run `git checkout\n-- README.md` in the repo root.\n"),
        ("tool.py", "# To restore a file, run `git checkout\n# -- README.md` in the repo root.\nx = 1\n"),
    ],
    ids=["markdown", "python comment"],
)
def test_dash_problems_ignores_a_spaced_double_hyphen_in_a_code_span_across_a_line_break(name, text):
    assert dashcheck.dash_problems(name, text) == []


def test_dash_problems_reports_a_spaced_double_hyphen_after_a_code_span_across_a_line_break():
    text = "run `git checkout\n-- README.md` -- then commit\n"
    assert dashcheck.dash_problems("a.md", text) == [Problem("a.md", 2, SPACED)]


def test_dash_problems_does_not_join_a_code_span_across_a_fence():
    text = "run `git\n```\ncode\n```\n-- b` c\n"
    assert dashcheck.dash_problems("a.md", text) == [Problem("a.md", 5, SPACED)]


def test_dash_problems_ignores_the_end_of_options_in_a_shell_script():
    assert dashcheck.dash_problems("setup.sh", "#!/bin/sh\ngit checkout -- README.md\n") == []


@pytest.mark.parametrize("name", ["build.bat", ".github/workflows/ci.yml", "justfile", "pyproject.toml"])
def test_dash_problems_reads_only_the_em_and_en_dash_in_a_file_that_is_not_prose(name):
    text = f"# the end -- of options\nrun -- a.py\necho one {EM} two {EN} three\n"
    assert dashcheck.dash_problems(name, text) == [
        Problem(name, 3, "an em dash; restructure the sentence"),
        Problem(name, 3, "an en dash; restructure the sentence"),
    ]


def test_dash_problems_reads_only_the_comments_and_docstrings_of_a_spec_file():
    source = '"""Build -- the app."""\na = b -- c\n# one -- two\n'
    assert sorted(dashcheck.dash_problems("build.spec", source)) == [
        Problem("build.spec", 1, SPACED),
        Problem("build.spec", 3, SPACED),
    ]


def test_check_reports_an_em_dash_in_a_python_file_that_does_not_parse(tmp_path):
    root = make_repo(tmp_path, {"broken.py": f"x = (\n# one {EM} two\n"})
    assert dashcheck.check(root) == (1, [Problem("broken.py", 2, "an em dash; restructure the sentence")])


def test_check_reads_only_the_comments_of_a_python_file_saved_with_a_bom(tmp_path):
    root = make_repo(tmp_path, {"bom.py": b"\xef\xbb\xbf# minus -- minus\nx = a -- b\n"})
    assert dashcheck.check(root) == (1, [Problem("bom.py", 1, SPACED)])


def test_check_skips_the_licenses_the_translations_and_binary_files(tmp_path):
    root = make_repo(tmp_path, {
        "LICENSE": f"a {EM} b\n",
        "lang/Deutsch.json": f'{{"a": "b {EM} c"}}',
        "image.png": b"\0\0" + EM.encode("utf-8"),
        "docs/a.md": "fine\n",
    })
    assert dashcheck.check(root) == (1, [])


def test_check_reports_a_text_file_of_any_kind_that_is_not_utf8_but_not_a_license_or_a_translation(tmp_path):
    root = make_repo(tmp_path, {
        "build.sh": f"echo one\necho a {EM} b\n".encode("cp1252"),
        "LICENSE": f"a {EM} b\n".encode("cp1252"),
        "lang/Deutsch.json": f'{{"a": "b {EM} c"}}'.encode("cp1252"),
        "docs/a.md": "fine\n",
    })
    assert dashcheck.check(root) == (1, [Problem("build.sh", 2, "is not UTF-8 text")])


def test_check_returns_the_problems_of_every_file_in_order(tmp_path):
    root = make_repo(tmp_path, {"b.md": f"x {EM} y\n", "a.md": "one\ntwo -- three\n"})
    assert dashcheck.check(root) == (2, [
        Problem("a.md", 2, SPACED),
        Problem("b.md", 1, "an em dash; restructure the sentence"),
    ])


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {"a.md": "one -- two\n"})
    assert dashcheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == f"a.md:1: {SPACED}\ndashcheck: 1 files, 1 problems\n"


def test_main_returns_0_when_no_file_uses_a_dash(tmp_path, capsys):
    root = make_repo(tmp_path, {"a.md": "one - two\n"})
    assert dashcheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "dashcheck: 1 files, 0 problems\n"
