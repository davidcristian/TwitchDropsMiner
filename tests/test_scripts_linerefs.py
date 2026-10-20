from __future__ import annotations

import pytest

import docscheck
import linerefs
from gitrepo import AGENTS, make_repo
from sources import Problem

MESSAGE = "cites a line by its number, not its function or class"


def cites(text: str) -> list[Problem]:
    return linerefs.line_number_problems("a.md", text)


@pytest.mark.parametrize(
    ("line", "cited"),
    [
        ("The loop is in `twitch.py:553`.", "twitch.py:553"),
        ("See gamelib/steam.py:12 for the parser.", "gamelib/steam.py:12"),
        ("The output names docs/index.md:1:", "docs/index.md:1"),
        ("See [the loop](../twitch.py#L553).", "../twitch.py#L553"),
        ("See [the range](../twitch.py#L3-L5).", "../twitch.py#L3-L5"),
        ("See `justfile:12`.", "justfile:12"),
        ("The rule is .gitignore:3.", ".gitignore:3"),
        ("See docs/.gitignore:1 for it.", "docs/.gitignore:1"),
        ("The grant is in LICENSE:4.", "LICENSE:4"),
        ("The notice is LICENSE.MIT:2.", "LICENSE.MIT:2"),
        ("The parser (Lines 3 to 5) reads the file.", "Lines 3 to 5"),
        ("It reads (lines 7-9, 11 and the end).", "lines 7-9, 11"),
        ("It is set in `settings.py` (line 37).", "line 37"),
        ("See `inventory.py` line 156.", "line 156"),
        ("See websocket.py, line 144.", "line 144"),
        ("It changed `gui.py` lines 220 and 236.", "lines 220 and 236"),
        ("See [`inventory.py`](../inventory.py) line 156.", "line 156"),
        ("See **`inventory.py`** line 156.", "line 156"),
        ("See `inventory.py`: line 156.", "line 156"),
        ("The `justfile` line 4 runs it.", "line 4"),
        ("The loop is line 553 of `twitch.py`.", "line 553"),
        ("Line 553 in twitch.py starts the loop.", "Line 553"),
        ("See lines 3 to 5 of [`gui.py`](../gui.py).", "lines 3 to 5"),
    ],
)
def test_line_number_problems_reports_a_line_cited_by_its_number(line, cited):
    assert cites(f"# A\n\n{line}\n") == [Problem("a.md", 3, f'"{cited}" {MESSAGE}')]


def test_line_number_problems_reports_each_citation_of_a_line_in_order():
    assert cites("Both `gui.py:581` and (line 4).\n") == [
        Problem("a.md", 1, f'"gui.py:581" {MESSAGE}'),
        Problem("a.md", 1, f'"line 4" {MESSAGE}'),
    ]


def test_line_number_problems_reads_on_past_a_line_break_that_a_number_and_a_period_start():
    text = "The fix is in (`twitch.py`, line\n553. It then waits).\n"
    assert cites(text) == [Problem("a.md", 1, f'"line 553" {MESSAGE}')]


def test_line_number_problems_reports_a_citation_split_by_a_line_break_once_at_its_first_line():
    text = "The fix changed `gui.py` lines 220 and\n236, and (see `inventory.py`, line\n156) reads it.\n"
    assert cites(text) == [
        Problem("a.md", 1, f'"lines 220 and 236" {MESSAGE}'),
        Problem("a.md", 2, f'"line 156" {MESSAGE}'),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "```\nraise LoginException: twitch.py:339\n(line 12)\n```\n",
        "~~~\ngui.py:581\n~~~\n",
        "The 300 line cap, and 1 line, token in 1.\n",
        "A deadline 12 days out, online 3 hours, inline 2 times, and the first line.\n",
        "Set `line-length = 120` and see [l10n](translate.md#l10n-support).\n",
        "The port example.com:443 and the time 12:30.\n",
        "The `twitch.py` line\n\n12 apples\n",
    ],
    ids=["backtick fence", "tilde fence", "count before line", "word ending in line", "no number", "no source file",
         "blank line between"],
)
def test_line_number_problems_ignores_code_fences_and_numbers_that_cite_no_line(text):
    assert cites(text) == []


@pytest.mark.parametrize(
    "line",
    [
        "A subject line 72 characters long is the limit.",
        "A `.py` line 120 characters long is the limit.",
        "Keep every `.md` line 120 characters or shorter.",
        "Lines 3 to 5 of a commit body are text.",
        "The subject goes on line 1 and the body starts on line 3.",
        "The loop starts at line 40.",
        "1. Write the subject line\n2. Leave a blank line",
        "1. Find the `README.md` line\n2. Leave a blank line",
        "Retry the check 3 times.",
    ],
    ids=["count after line", "a bare extension", "a bare extension in a rule", "no file", "commit message lines",
         "at line without a file", "a numbered list", "a list after a file name", "no line"],
)
def test_line_number_problems_ignores_line_n_that_is_not_in_a_citation_form(line):
    assert cites(f"{line}\n") == []


@pytest.mark.parametrize(
    "line",
    [
        "The time 1.2:3, e.g.:4 and MYLICENSE:5 or justfiles:6.",
        "See [the cache](docs/cache.md#l2-cache) and docs/cache.md#L2-cache.",
        "Not twitch.py#l553, twitch.py#L5x or twitch.py#L5-L6-L7.",
        "Use .NET:4 here, and the .py:3 kind.",
    ],
    ids=["no file name", "heading anchors", "not a line anchor", "not a dotfile"],
)
def test_line_number_problems_ignores_a_number_after_a_name_that_is_not_a_file_or_an_anchor_that_is_no_line(line):
    assert cites(f"{line}\n") == []


def test_check_reports_a_line_cited_by_its_number_in_every_markdown_file_but_not_in_a_fence(tmp_path):
    root = make_repo(tmp_path, {
        "AGENTS.md": AGENTS,
        "README.md": "# Read me\n\nSee `main.py:10`.\n",
        "docs/notes.md": "# Notes\n\n```\nmain.py:10\n```\n",
        "lang/notes.md": "See main.py:10.\n",
        "docs/binary.md": b"See main.py:10.\n\0\xff\n",
    })
    assert docscheck.check(root) == (3, [Problem("README.md", 3, f'"main.py:10" {MESSAGE}')])
