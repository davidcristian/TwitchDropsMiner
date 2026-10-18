from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import commitlint
from bannedwords import parse_table
from commitlint import Line
from gitrepo import AGENTS, HOOD, SEAM, make_repo

TABLE = parse_table(AGENTS)
EM = "\u2014"
EN = "\u2013"
GOOD = "fix(twitch): keep the channel list after a reload\n\nThe list was cleared, so the miner switched channels.\n"


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo", {"AGENTS.md": AGENTS})


def lint(text: str, repo: Path) -> list[str]:
    return commitlint.check(text, TABLE, repo)


def test_message_lines_drops_comment_lines_and_everything_below_the_scissors_line():
    text = f"fix: a\n\nbody\n# a comment\n{commitlint.SCISSORS}\ndiff --git a/x b/x\n+{SEAM}\n"
    assert commitlint.message_lines(text) == ["fix: a", "", "body"]


def test_classify_marks_fences_the_lines_between_them_and_prompt_lines_as_pasted():
    lines = ["fix: a", "", "Text.", "```", "out -- put", "```", "  $ git log -- a", "$HOME is set", "after"]
    classified, opened = commitlint.classify(lines)
    assert [line.pasted for line in classified] == [False, False, False, True, True, True, True, False, False]
    assert opened is None


def test_classify_does_not_read_the_header_as_a_fence():
    classified, opened = commitlint.classify(["```", "body"])
    assert classified == [Line(1, "```", False), Line(2, "body", False)]
    assert opened is None


def test_classify_returns_the_line_of_a_fence_that_nothing_closes():
    classified, opened = commitlint.classify(["fix: a", "", "~~~", "out"])
    assert opened == 3
    assert classified[-1] == Line(4, "out", True)


@pytest.mark.parametrize(
    "header",
    ["fix: keep the list", "feat(gui)!: drop the old tab", "Update the readme.", "fix: " + "a" * 67],
    ids=["plain", "scope and breaking mark", "not conventional, left to conventional-pre-commit", "72 characters"],
)
def test_header_problems_accepts_a_header_in_the_format(header):
    assert commitlint.header_problems(header) == []


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("fix: " + "a" * 68, "the subject line is 73 characters; the limit is 72"),
        ("fix: Keep the list", "the subject starts with a capital letter"),
        ("fix: keep the list.", "the subject ends with a period"),
        ("docs(docs): fix a link", "the scope repeats the type 'docs'"),
    ],
)
def test_header_problems_reports_each_rule_the_header_breaks(header, problem):
    assert commitlint.header_problems(header) == [problem]


@pytest.mark.parametrize(
    ("text", "wide"),
    [
        ("word " * 14 + "abc", True),
        ("word " * 14 + "ab", False),
        ("https://example.invalid/" + "a" * 60, False),
        ("    " + "a" * 80, False),
        ("- https://example.invalid/" + "a" * 60, True),
    ],
    ids=["73 characters", "72 characters", "one long word", "one long indented word", "a list item of one long word"],
)
def test_too_wide_reports_a_line_over_the_width_that_has_a_place_to_break(text, wide):
    assert commitlint.too_wide(text) is wide


def test_too_wide_reports_a_line_of_words_and_a_long_word_that_can_break_before_it():
    assert commitlint.too_wide("See https://example.invalid/" + "a" * 60) is True


def test_check_accepts_a_message_that_follows_the_rules(repo):
    assert lint(GOOD, repo) == []


def test_check_reports_a_body_line_over_the_width_but_not_a_pasted_one(repo):
    wide = "word " * 14 + "abc"
    text = f"fix: a\n\n{wide}\n```\n{wide}\n```\n$ {wide}\n"
    assert lint(text, repo) == ["line 3 is 73 characters; the body wraps at 72"]


def test_check_accepts_a_body_line_of_one_word_over_the_width(repo):
    assert lint("fix: a\n\nSee the log at\nhttps://example.invalid/" + "a" * 80 + "\n", repo) == []


def test_check_reports_a_body_over_50_words_and_does_not_count_pasted_words(repo):
    body = "\n".join(["word " * 10] * 5)
    paste = "```\n" + "out " * 30 + "\n```\n"
    assert lint(f"fix: a\n\n{body}\n{paste}", repo) == []
    assert lint(f"fix: a\n\n{body}\nmore\n", repo) == ["the body is 51 words; the limit is 50"]


def test_check_reports_a_fence_that_nothing_closes(repo):
    assert lint("fix: a\n\nText.\n```\noutput\n", repo) == ["line 4 opens a code fence that nothing closes"]


def test_check_reports_each_dash_in_the_header_and_the_body_but_not_in_a_paste(repo):
    text = f"fix: a {EM} b\n\nOne {EN} two.\nThree -- four.\n```\nfive {EM} six -- seven\n```\n"
    assert lint(text, repo) == [
        "line 1 uses an em dash; restructure the sentence",
        "line 3 uses an en dash; restructure the sentence",
        "line 4 uses a spaced --; restructure the sentence",
    ]


def test_check_reports_a_spaced_double_hyphen_at_the_end_of_a_body_line(repo):
    text = "fix: a\n\nThe check runs first --\nthen the build.\n"
    assert lint(text, repo) == ["line 3 uses a spaced --; restructure the sentence"]


@pytest.mark.parametrize(
    ("line", "spaced"),
    [
        ("-- then the build.", True),
        ("    -- then the build.", True),
        ("Pass --log to see it.", False),
        ("--log turns it on.", False),
        ("--", False),
        ("  --  ", False),
        ("---", False),
    ],
    ids=["at the start", "after the indentation", "a flag", "a flag first", "only --", "only -- and spaces", "a rule"],
)
def test_check_reports_a_spaced_double_hyphen_at_the_start_of_a_line_but_not_a_flag_or_a_rule(repo, line, spaced):
    problems = lint(f"fix: a\n\nThe build runs.\n{line}\n", repo)
    assert problems == (["line 4 uses a spaced --; restructure the sentence"] if spaced else [])


def test_check_reports_a_spaced_double_hyphen_at_the_end_of_the_header(repo):
    assert lint("fix: keep the order --\n", repo) == ["line 1 uses a spaced --; restructure the sentence"]


@pytest.mark.parametrize(
    "text",
    [
        "fix: a\n\nRun `git log -- scripts/` to see the history.\n",
        "fix: a\n\nRun `git log\n-- scripts/` to see the history.\n",
        "fix: keep `a -- b` in the header\n",
        f"fix: a\n\nThe text `a {EM} b` and ``c {EN} d`` stays.\n",
        "fix: a\n\nSee [the notes](notes -- old.md) for it.\n",
        f"fix: a\n\nSee https://example.invalid/a{EM}b for it.\n",
    ],
    ids=["a code span", "a code span over a line break", "the header", "em and en dash", "a link target", "a URL"],
)
def test_check_accepts_a_dash_inside_a_code_span_a_link_target_or_a_url(repo, text):
    assert lint(text, repo) == []


@pytest.mark.parametrize(
    ("text", "spaced"),
    [
        ("Run `x` -- then y.", True),
        ("Run `x` --\nthen y.", True),
        ("Run `x`-- then y.", False),
        ("Run `a -- b` -- then y.", True),
        ("`x` --\nthen y.", True),
    ],
    ids=[
        "after a code span", "a line end after a code span", "against the backtick", "after a span that has one",
        "a line of only a code span and the double hyphen",
    ],
)
def test_check_reads_the_spacing_of_a_double_hyphen_outside_a_code_span_from_the_line_as_written(repo, text, spaced):
    problems = lint(f"fix: a\n\n{text}\n", repo)
    assert problems == (["line 3 uses a spaced --; restructure the sentence"] if spaced else [])


def test_check_does_not_count_the_trailers_as_body_words(repo):
    body = "\n".join(["word " * 12] * 4)
    text = f"fix: a\n\n{body}\n\nCo-authored-by: Some One <one@example.invalid>\n"
    assert lint(text, repo) == []


def test_check_counts_a_last_paragraph_that_is_not_only_trailers(repo):
    body = "\n".join(["word " * 12] * 4)
    text = f"fix: a\n\n{body}\n\nCo-authored-by: Some One <one@example.invalid>\nThanks to all.\n"
    assert lint(text, repo) == ["the body is 55 words; the limit is 50"]


def test_check_reads_the_trailers_for_every_rule_but_the_word_count(repo):
    text = f"fix: a\n\nBody.\n\nCo-authored-by: One {EM} {SEAM} <a@b>\nNote: {'word ' * 14}end\nRefs: #12\n"
    assert lint(text, repo) == [
        "line 6 is 79 characters; the body wraps at 72",
        "line 5 uses an em dash; restructure the sentence",
        "line 7 cites an issue or pull request number ('#12'); name the behavior instead",
        f'line 5 uses the banned word "{SEAM}"; the table in AGENTS.md gives a replacement',
    ]


@pytest.mark.parametrize(
    ("lines", "numbers"),
    [
        (["fix: a", "", "Body.", "", "Co-authored-by: A <a@b>", "BREAKING CHANGE: it moves", "Refs: x"], {5, 6, 7}),
        (["fix: a", "", "Body.", "", "Signed-off-by: A <a@b>", "", ""], {5}),
        (["fix: a", "", "Co-authored-by: A <a@b>"], {3}),
        (["fix: a", "", "Body.", "", "Co-authored-by: A <a@b>", "and more"], set()),
        (["fix: a", "", "Co-authored-by: A <a@b>", "", "Body."], set()),
        (["fix: a", "", "Body.", "", "Reviewed by: A <a@b>"], set()),
        (["fix: a", "", "Body.", "", "Note:"], set()),
        (["fix: a"], set()),
    ],
    ids=[
        "a block of trailers", "blank lines after it", "the only paragraph", "a line that is not a trailer",
        "not the last paragraph", "a token with a space", "no value", "no body",
    ],
)
def test_trailers_returns_the_last_paragraph_only_when_every_line_is_a_trailer(lines, numbers):
    assert commitlint.trailers(commitlint.classify(lines)[0]) == numbers


def test_check_reports_a_banned_word_in_the_header_and_body_but_not_in_a_paste_or_code(repo):
    first, rest = HOOD.rsplit(" ", 1)
    text = f"fix: drop the {SEAM}\n\nIt ran {first}\n{rest} and `{SEAM}` here.\n$ grep {SEAM}\n```\n{SEAM}\n```\n"
    assert lint(text, repo) == [
        f'line 1 uses the banned word "{SEAM}"; the table in AGENTS.md gives a replacement',
        f'line 3 uses the banned word "{HOOD}"; the table in AGENTS.md gives a replacement',
    ]


@pytest.mark.parametrize(
    "header",
    ["Merge branch 'feat/x'", 'Revert "fix: a"', "fixup! fix: a", "squash! fix: a", "amend! fix: a"],
)
def test_check_returns_nothing_for_a_merge_revert_or_fixup_message(repo, header):
    assert lint(f"{header} {SEAM} {EM}\n\n" + "word " * 80 + "\n", repo) == []


@pytest.mark.parametrize("text", ["", "\n\n", "# only a comment\n"])
def test_check_returns_nothing_for_an_empty_message(repo, text):
    assert lint(text, repo) == []


def test_main_prints_each_problem_to_stderr_and_returns_1(repo, tmp_path, capsys):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: Keep it.\n", encoding="utf-8")
    assert commitlint.main([str(message), "--root", str(repo)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "commitlint: the subject starts with a capital letter\ncommitlint: the subject ends with a period\n"
    )


def test_main_returns_0_for_a_message_that_follows_the_rules(repo, tmp_path, capsys):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(GOOD, encoding="utf-8")
    assert commitlint.main([str(message), "--root", str(repo)]) == 0
    assert capsys.readouterr().err == ""


def test_the_hook_run_as_a_program_exits_with_the_status_of_main(repo, tmp_path):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"fix: a {EM} b\n", encoding="utf-8")
    script = Path(commitlint.__file__)
    command = [sys.executable, str(script), str(message), "--root", str(repo)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stderr == "commitlint: line 1 uses an em dash; restructure the sentence\n"
