from __future__ import annotations

import pytest

from bannedwords import Hit, Table, TableError, compile_words, find_words, mask, mask_run, parse_table, runs
from gitrepo import AGENTS, BEARING, HANGING, HOOD, SEAM, TABLE

PATTERN = compile_words([SEAM, SEAM + "s", BEARING, HOOD, HANGING])


def test_parse_table_returns_the_lowercase_words_of_the_first_column_and_the_row_lines():
    assert parse_table(AGENTS) == Table((SEAM, SEAM + "s", BEARING, HOOD, HANGING), first=5, last=9)


def test_parse_table_reads_words_written_in_capitals():
    text = "| Do not write | Write instead |\n| :---: | --- |\n| " + SEAM.upper() + " | boundary |\n"
    assert parse_table(text).words == (SEAM,)


def test_parse_table_ends_the_table_at_the_first_line_that_is_not_a_row():
    text = TABLE + "\n| " + "ga" + "te | check |\n"
    assert "ga" + "te" not in parse_table(text).words


def test_parse_table_skips_a_table_with_another_header():
    text = "| Word | Use |\n| --- | --- |\n| other | x |\n\n" + TABLE
    assert parse_table(text).first == 5


def test_parse_table_fails_when_no_table_has_the_header():
    with pytest.raises(TableError, match="no table has a first column headed"):
        parse_table("# Rules\n\n| Word | Use |\n| --- | --- |\n| x | y |\n")


def test_parse_table_fails_when_the_table_lists_no_word():
    with pytest.raises(TableError, match="lists no word"):
        parse_table("| Do not write | Write instead |\n| --- | --- |\n")


def test_compile_words_matches_a_word_in_any_case():
    assert PATTERN.search("A " + SEAM.capitalize() + " here").group() == SEAM.capitalize()


def test_compile_words_does_not_match_a_word_inside_a_longer_word():
    assert PATTERN.search("a " + SEAM + "stress and " + SEAM + "ed") is None


def test_compile_words_matches_the_longer_of_two_listed_words():
    assert PATTERN.search("two " + SEAM + "s").group() == SEAM + "s"


def test_compile_words_matches_a_phrase_split_by_any_whitespace():
    split = HOOD.replace(" ", "\n   ", 1).replace(" ", "\t", 1)
    assert PATTERN.search("it is " + split + " now").group() == split


def test_compile_words_matches_a_listed_hyphenated_compound():
    assert PATTERN.search("a " + BEARING + " part").group() == BEARING


def test_compile_words_does_not_match_a_word_inside_a_hyphenated_compound():
    assert PATTERN.search("a " + SEAM + "-free run and pre-" + SEAM) is None


def test_mask_blanks_a_code_span_and_keeps_the_length():
    text = "use `" + SEAM + "` here"
    assert mask(text) == "use " + " " * (len(SEAM) + 2) + " here"


def test_mask_blanks_a_double_backtick_code_span_that_contains_a_backtick():
    assert mask("a ``x ` " + SEAM + "`` b") == "a " + " " * (len(SEAM) + 8) + " b"


def test_mask_keeps_the_link_text_and_blanks_the_link_target():
    assert mask("[" + SEAM + "](docs/" + SEAM + ".md)") == "[" + SEAM + "]" + " " * (len(SEAM) + 10)


def test_mask_blanks_a_url_in_plain_text():
    assert mask("see https://example.invalid/" + SEAM + " now") == "see " + " " * (24 + len(SEAM)) + " now"


def test_mask_keeps_text_after_a_backtick_that_nothing_closes():
    assert mask("a `" + SEAM) == "a `" + SEAM


def test_mask_blanks_a_code_span_across_one_line_break_and_keeps_the_break():
    assert mask("a `b\n" + SEAM + "` c") == "a   \n" + " " * (len(SEAM) + 1) + " c"


def test_mask_run_blanks_a_code_span_across_a_line_break_and_returns_each_line():
    run = [(1, "run `git checkout"), (2, "-- README.md` now")]
    assert mask_run(run) == ["run" + " " * 14, " " * 13 + " now"]


def test_mask_run_cuts_a_line_that_holds_line_breaks_by_its_length():
    assert mask_run([(5, "a\n`b"), (6, "c` d")]) == ["a\n  ", "   d"]


def test_mask_run_returns_nothing_for_an_empty_run():
    assert mask_run([]) == []


def test_runs_splits_lines_at_a_blank_line_and_at_a_gap_in_the_numbers():
    lines = [(1, "a"), (2, "b"), (3, "  "), (4, "c"), (7, "d"), (8, "e")]
    assert runs(lines) == [[(1, "a"), (2, "b")], [(4, "c")], [(7, "d"), (8, "e")]]


def test_runs_returns_nothing_for_blank_lines():
    assert runs([(1, ""), (2, " ")]) == []


def test_find_words_reports_a_phrase_split_by_a_line_break():
    first, rest = HOOD.rsplit(" ", 1)
    run = [(10, "it works " + first.capitalize()), (11, rest.upper() + " today")]
    assert find_words(run, PATTERN) == [Hit(10, HOOD)]


def test_find_words_reports_each_word_once_on_its_own_line():
    run = [(1, "a " + SEAM), (2, "b " + SEAM + "s and " + BEARING)]
    assert find_words(run, PATTERN) == [Hit(1, SEAM), Hit(2, SEAM + "s"), Hit(2, BEARING)]


def test_find_words_skips_a_word_inside_backticks_or_a_link_target():
    run = [(1, "the `" + SEAM + "` and [text](" + SEAM + ".md) and <https://x.invalid/" + SEAM + ">")]
    assert find_words(run, PATTERN) == []


def test_find_words_reports_a_word_in_link_text():
    assert find_words([(3, "[the " + SEAM + "](x.md)")], PATTERN) == [Hit(3, SEAM)]


def test_find_words_skips_a_word_inside_a_code_span_split_by_a_line_break():
    run = [(1, "run `python tool.py"), (2, SEAM + "` first")]
    assert find_words(run, PATTERN) == []


def test_find_words_reads_every_part_of_a_line_that_holds_line_breaks():
    run = [(5, "first\nsecond " + SEAM + "\nthird `x"), (6, "y` " + BEARING)]
    assert find_words(run, PATTERN) == [Hit(5, SEAM), Hit(6, BEARING)]


def test_find_words_reports_a_word_between_backticks_two_line_breaks_apart():
    run = [(1, "a `x"), (2, SEAM), (3, "y` b")]
    assert find_words(run, PATTERN) == [Hit(2, SEAM)]


def test_find_words_pairs_backticks_on_one_line_before_pairing_across_a_break():
    run = [(1, "`a` " + SEAM + " `b"), (2, "c` d")]
    assert find_words(run, PATTERN) == [Hit(1, SEAM)]


@pytest.mark.parametrize(
    ("run", "line"),
    [([(1, "[x](a " + SEAM), (2, "b) c")], 1), ([(1, "see https://x.invalid/a"), (2, SEAM + " b")], 2)],
    ids=["link target", "url"],
)
def test_find_words_does_not_mask_a_link_target_or_a_url_across_a_line_break(run, line):
    assert find_words(run, PATTERN) == [Hit(line, SEAM)]
