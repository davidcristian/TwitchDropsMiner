from __future__ import annotations

import pytest

import linecap
from gitrepo import make_repo
from sources import Problem


def lines(count: int) -> str:
    return "x = 1\n" * count


@pytest.mark.parametrize(
    ("name", "limit"),
    [("gui.py", 300), ("gamelib/scan.py", 300), ("docs/index.md", 250), ("build.spec", None), ("a.json", None)],
)
def test_limit_for_returns_the_limit_of_python_and_markdown_files_only(name, limit):
    assert linecap.limit_for(name) == limit


def test_cap_problems_accepts_files_at_their_limit(monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    assert linecap.cap_problems({"a.py": 300, "b.md": 250, "c.txt": 5000}) == []


def test_cap_problems_reports_a_file_one_line_over_its_limit(monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    assert linecap.cap_problems({"a.py": 301, "docs/b.md": 251}) == [
        Problem("a.py", 301, "301 lines; the limit is 300, so split it"),
        Problem("docs/b.md", 251, "251 lines; the limit is 250, so split it"),
    ]


def test_cap_problems_accepts_a_listed_exception_over_the_limit(monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset({"gui.py"}))
    assert linecap.cap_problems({"gui.py": 3200}) == []


@pytest.mark.parametrize("lengths", [{"gui.py": 300}, {"gui.py": 12}, {}], ids=["at the limit", "short", "deleted"])
def test_cap_problems_reports_a_stale_entry_in_exceptions(monkeypatch, lengths):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset({"gui.py"}))
    assert linecap.cap_problems(lengths) == [
        Problem("gui.py", 1, "listed in EXCEPTIONS in linecap.py but not over the limit")
    ]


def test_check_measures_python_and_markdown_files_and_reports_the_long_one(tmp_path, monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    root = make_repo(tmp_path, {
        "short.py": lines(300),
        "pkg/long.py": lines(301),
        "README.md": "line\n" * 250,
        "data.json": "{}\n" * 900,
    })
    assert linecap.check(root) == (3, [Problem("pkg/long.py", 301, "301 lines; the limit is 300, so split it")])


def test_check_counts_a_last_line_without_a_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    root = make_repo(tmp_path, {"a.py": lines(300) + "y = 2"})
    assert linecap.check(root)[1] == [Problem("a.py", 301, "301 lines; the limit is 300, so split it")]


def test_check_skips_a_file_that_is_not_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    root = make_repo(tmp_path, {"a.py": b"\xff\n" * 400})
    assert linecap.check(root) == (0, [])


def test_check_reports_an_exception_whose_module_is_now_short(tmp_path, monkeypatch):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset({"gui.py", "twitch.py"}))
    root = make_repo(tmp_path, {"gui.py": lines(301), "twitch.py": lines(299)})
    assert linecap.check(root)[1] == [
        Problem("twitch.py", 1, "listed in EXCEPTIONS in linecap.py but not over the limit")
    ]


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    root = make_repo(tmp_path, {"docs/long.md": "x\n" * 260})
    assert linecap.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == (
        "docs/long.md:260: 260 lines; the limit is 250, so split it\nlinecap: 1 files, 1 problems\n"
    )


def test_main_returns_0_when_every_file_is_within_its_limit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(linecap, "EXCEPTIONS", frozenset())
    root = make_repo(tmp_path, {"a.py": lines(10)})
    assert linecap.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "linecap: 1 files, 0 problems\n"

