from __future__ import annotations

import pytest

import prosecheck
from bannedwords import TableError, parse_table
from gitrepo import AGENTS, BEARING, HOOD, SEAM, make_repo
from sources import Problem

TABLE = parse_table(AGENTS)


def banned(name: str, line: int, word: str) -> Problem:
    return Problem(name, line, f'banned word "{word}"; the table in AGENTS.md gives a replacement')


def test_word_problems_reports_a_banned_word_in_markdown_prose_at_its_line():
    text = f"# Title\n\nThe {SEAM} here.\n"
    assert prosecheck.word_problems("docs/a.md", text, TABLE) == [banned("docs/a.md", 3, SEAM)]


def test_word_problems_reports_a_phrase_split_by_a_line_break_once():
    first, rest = HOOD.rsplit(" ", 1)
    text = f"It works {first}\n{rest} today.\n"
    assert prosecheck.word_problems("a.md", text, TABLE) == [banned("a.md", 1, HOOD)]


def test_word_problems_does_not_join_a_phrase_across_a_blank_line():
    first, rest = HOOD.rsplit(" ", 1)
    assert prosecheck.word_problems("a.md", f"It works {first}\n\n{rest} today.\n", TABLE) == []


@pytest.mark.parametrize(
    "quote",
    ["> ", "> > ", ">> ", "  >"],
    ids=["block quote", "nested block quote", "nested markers without a space", "indented marker without a space"],
)
def test_word_problems_reports_a_phrase_split_across_the_lines_of_a_block_quote(quote):
    first, rest = HOOD.rsplit(" ", 1)
    text = f"Intro.\n\n{quote}It works {first}\n{quote}{rest} today.\n"
    assert prosecheck.word_problems("a.md", text, TABLE) == [banned("a.md", 3, HOOD)]


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_word_problems_ignores_a_banned_word_in_a_fence(fence):
    text = f"one\n{fence}\n{SEAM} = 1\n{fence}\n"
    assert prosecheck.word_problems("a.md", text, TABLE) == []


def test_word_problems_ignores_a_banned_word_in_backticks_or_a_link_target():
    text = f"The `{SEAM}` value, see [the docs](docs/{SEAM}.md).\n"
    assert prosecheck.word_problems("a.md", text, TABLE) == []


def test_word_problems_skips_the_table_rows_of_agents_md_but_not_its_other_lines():
    text = AGENTS + f"\nA {BEARING} rule.\n"
    assert prosecheck.word_problems("AGENTS.md", text, TABLE) == [banned("AGENTS.md", 13, BEARING)]


def test_word_problems_reads_the_table_rows_of_another_file():
    assert prosecheck.word_problems("docs/copy.md", AGENTS, TABLE) != []


def test_word_problems_reads_python_comments_and_docstrings_but_not_code_or_strings():
    source = f'"""The {SEAM} module."""\n{SEAM} = "{SEAM}"  # one {SEAM}\n'
    assert sorted(prosecheck.word_problems("tool.py", source, TABLE)) == [
        banned("tool.py", 1, SEAM),
        banned("tool.py", 2, SEAM),
    ]


def test_word_problems_reads_the_strings_of_translate_py():
    source = f'TEXT = {{"key": "The {SEAM} is shown"}}\n'
    assert prosecheck.word_problems("translate.py", source, TABLE) == [banned("translate.py", 1, SEAM)]


def test_block_problems_accepts_a_comment_block_and_a_docstring_of_three_lines():
    source = '"""One.\n\nThree."""\n# a\n# b\n# c\nx = 1  # d\n# e\n'
    assert prosecheck.block_problems("tool.py", source) == []


def test_block_problems_reports_a_comment_block_of_four_lines_at_its_first_line():
    source = "x = 1\n# a\n# b\n# c\n# d\ny = 2\n"
    assert prosecheck.block_problems("tool.py", source) == [
        Problem("tool.py", 2, "comment block of 4 lines; the limit is 3")
    ]


def test_block_problems_reports_a_docstring_of_four_lines():
    source = 'def f():\n    """One.\n\n    Three.\n    Four.\n    """\n'
    assert prosecheck.block_problems("tool.py", source) == [
        Problem("tool.py", 2, "docstring of 4 lines; the limit is 3")
    ]


@pytest.mark.parametrize(
    "source",
    ["x = = 1\n# a\n# b\n# c\n# d\n", "x = (\n# a\n# b\n# c\n# d\n"],
    ids=["invalid syntax", "unclosed bracket that tokenize rejects"],
)
def test_block_problems_returns_nothing_for_a_file_that_does_not_parse(source):
    assert prosecheck.block_problems("broken.py", source) == []


def test_block_problems_reads_a_file_that_starts_with_a_utf8_bom():
    source = '\ufeff# a\n# b\n# c\n# d\ndef f():\n    """One.\n\n    Three.\n    Four.\n    """\n'
    assert prosecheck.block_problems("bom.py", source) == [
        Problem("bom.py", 1, "comment block of 4 lines; the limit is 3"),
        Problem("bom.py", 6, "docstring of 4 lines; the limit is 3"),
    ]


def test_block_problems_returns_nothing_when_tokenize_rejects_a_file_that_ast_parse_accepts():
    # Python 3.10 and 3.11 parse this last lone backslash and tokenize rejects it; Python 3.12 does not parse it
    assert prosecheck.block_problems("tool.py", "x = 1\r\n\\\r\n") == []


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["LF", "CRLF", "CR"])
def test_check_reads_the_comments_of_a_python_file_with_any_line_ending_at_their_lines(tmp_path, newline):
    source = newline.join(["x = 1", f"# a {SEAM}", "# b", "# c", "# d", "y = 2", ""])
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "tool.py": source.encode()})
    assert prosecheck.check(root) == (2, [
        banned("tool.py", 2, SEAM),
        Problem("tool.py", 2, "comment block of 4 lines; the limit is 3"),
    ])


def test_check_reads_only_the_comments_and_docstrings_of_a_python_file_saved_with_a_bom(tmp_path):
    source = f'"""The {SEAM} module."""\nX = "{SEAM}"\n# one {SEAM}\n'
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "bom.py": b"\xef\xbb\xbf" + source.encode()})
    assert prosecheck.check(root) == (2, [banned("bom.py", 1, SEAM), banned("bom.py", 3, SEAM)])


def test_check_reads_a_python_file_that_does_not_parse_line_by_line(tmp_path):
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "broken.py": f"x = (\n# a\n# b\n# c\n# d {SEAM}\n"})
    assert prosecheck.check(root) == (2, [banned("broken.py", 5, SEAM)])


def test_check_reports_words_and_blocks_and_skips_licenses_translations_and_binaries(tmp_path):
    root = make_repo(tmp_path, {
        "AGENTS.md": AGENTS,
        "LICENSE": f"{SEAM}\n",
        "lang/Polski.json": f'{{"a": "{SEAM}"}}',
        "blob.bin": b"\0" + SEAM.encode(),
        "docs/a.md": f"A {SEAM}.\n",
        "tool.py": "# a\n# b\n# c\n# d\n",
        "notes.txt": "# a\n# b\n# c\n# d\n",
    })
    assert prosecheck.check(root) == (4, [
        banned("docs/a.md", 1, SEAM),
        Problem("tool.py", 1, "comment block of 4 lines; the limit is 3"),
    ])


def test_check_reports_a_text_file_of_any_kind_that_is_not_utf8_but_not_a_license_or_a_binary(tmp_path):
    root = make_repo(tmp_path, {
        "AGENTS.md": AGENTS,
        "notes.txt": f"A {SEAM} \u00e9.\n".encode("cp1252"),
        "LICENSE": f"A {SEAM} \u00e9.\n".encode("cp1252"),
        "blob.bin": b"\0\xff" + SEAM.encode(),
    })
    assert prosecheck.check(root) == (1, [Problem("notes.txt", 1, "is not UTF-8 text")])


def test_check_reports_a_comment_block_of_four_lines_in_a_spec_file(tmp_path):
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "build.spec": "# a\n# b\n# c\n# d\nx = 1\n"})
    assert prosecheck.check(root)[1] == [Problem("build.spec", 1, "comment block of 4 lines; the limit is 3")]


def test_check_fails_when_agents_md_has_no_banned_word_table(tmp_path):
    root = make_repo(tmp_path, {"AGENTS.md": "# Rules\n"})
    with pytest.raises(TableError):
        prosecheck.check(root)


def test_main_prints_each_problem_and_a_summary_and_returns_1(tmp_path, capsys):
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "a.md": f"{SEAM.upper()}\n"})
    assert prosecheck.main(["--root", str(root)]) == 1
    assert capsys.readouterr().out == f"{banned('a.md', 1, SEAM)}\nprosecheck: 2 files, 1 problems\n"


def test_main_returns_0_when_the_prose_follows_the_rules(tmp_path, capsys):
    root = make_repo(tmp_path, {"AGENTS.md": AGENTS, "a.md": "Plain words.\n"})
    assert prosecheck.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == "prosecheck: 2 files, 0 problems\n"
