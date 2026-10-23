from __future__ import annotations

import pytest

import linecap
from gitrepo import make_repo
from sources import Problem


def lines(count: int) -> str:
    return "x = 1\n" * count


@pytest.mark.parametrize(
    ("name", "limit"),
    [
        ("gui.py", 300),
        ("gamelib/scan.py", 300),
        ("docs/index.md", 300),
        ("AGENTS.md", 300),
        ("docs/AGENTS.md", 300),
        ("build.spec", None),
        ("a.json", None),
    ],
)
def test_limit_for_returns_the_limit_of_python_and_markdown_files_only(name, limit):
    assert linecap.limit_for(name) == limit


def test_cap_problems_accepts_files_at_their_limit():
    assert linecap.cap_problems({"a.py": 300, "b.md": 300, "c.txt": 5000}) == []


def test_cap_problems_reports_a_file_one_line_over_its_limit():
    assert linecap.cap_problems({"a.py": 301, "docs/b.md": 301}) == [
        Problem("a.py", 301, "301 lines; the limit is 300, so split it"),
        Problem("docs/b.md", 301, "301 lines; the limit is 300, so split it"),
    ]


def test_cap_problems_accepts_markdown_files_of_251_and_300_lines():
    assert linecap.cap_problems({"AGENTS.md": 300, "README.md": 251, "docs/b.md": 300}) == []


def test_cap_problems_reports_agents_md_and_another_markdown_file_at_301_lines():
    assert linecap.cap_problems({"AGENTS.md": 301, "README.md": 301}) == [
        Problem("AGENTS.md", 301, "301 lines; the limit is 300, so split it"),
        Problem("README.md", 301, "301 lines; the limit is 300, so split it"),
    ]




def test_cap_problems_reports_the_modules_that_were_once_exempt_when_they_go_over_the_limit():
    assert linecap.cap_problems({"gui.py": 301, "twitch/client.py": 3200}) == [
        Problem("gui.py", 301, "301 lines; the limit is 300, so split it"),
        Problem("twitch/client.py", 3200, "3200 lines; the limit is 300, so split it"),
    ]


def test_check_measures_python_and_markdown_files_and_reports_the_long_one(tmp_path):
    root = make_repo(tmp_path, {
        "short.py": lines(300),
        "pkg/long.py": lines(301),
        "README.md": "line\n" * 300,
        "data.json": "{}\n" * 900,
    })
    assert linecap.check(root) == (3, [Problem("pkg/long.py", 301, "301 lines; the limit is 300, so split it")])


def test_check_measures_every_markdown_file_against_300_lines(tmp_path):
    root = make_repo(tmp_path, {
        "AGENTS.md": "line\n" * 300,
        "docs/a.md": "line\n" * 251,
        "docs/AGENTS.md": "line\n" * 301,
    })
    assert linecap.check(root) == (3, [Problem("docs/AGENTS.md", 301, "301 lines; the limit is 300, so split it")])


def test_check_counts_a_last_line_without_a_newline(tmp_path):
    root = make_repo(tmp_path, {"a.py": lines(300) + "y = 2"})
    assert linecap.check(root)[1] == [Problem("a.py", 301, "301 lines; the limit is 300, so split it")]


def test_check_reports_a_measured_file_that_is_not_utf8_and_skips_a_binary_file(tmp_path):
    root = make_repo(tmp_path, {"a.py": b"x = 1\n" + b"\xff\n" * 400, "b.md": b"\0\xff\n" * 400, "c.json": b"\xff"})
    assert linecap.check(root) == (0, [Problem("a.py", 2, "is not UTF-8 text")])


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {"docs/long.md": "x\n" * 310})
    assert linecap.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == (
        "docs/long.md:310: 310 lines; the limit is 300, so split it\nlinecap: 1 files, 1 problems\n"
    )


def test_main_returns_0_when_every_file_is_within_its_limit(tmp_path, capsys):
    root = make_repo(tmp_path, {"a.py": lines(10)})
    assert linecap.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "linecap: 1 files, 0 problems\n"

