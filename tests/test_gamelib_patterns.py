import pytest

from gamelib import (
    any_match,
    compile_pattern,
    compile_patterns,
    has_wildcard,
    match_rank,
    matches,
    matching_names,
)

TRADEMARK_REASON = (
    "normalize turns the ™ sign into the letters tm "
    "(docs/refinements/tasks/009-trademark-symbols-in-game-names.md)"
)


def test_match_rank_gives_the_index_of_the_entry_that_matches():
    patterns = compile_patterns(["Pokemon*", "Warframe"])
    assert match_rank(patterns, "Pokémon Scarlet") == 0
    assert match_rank(patterns, "WARFRAME") == 1


def test_match_rank_returns_none_when_no_entry_matches():
    assert match_rank(compile_patterns(["Pokemon*", "Warframe"]), "Rust") is None
    assert match_rank([], "Rust") is None


def test_match_rank_takes_the_first_entry_that_matches():
    patterns = compile_patterns(["Warframe", "Pokemon Scarlet", "Pokemon*"])
    assert match_rank(patterns, "Pokémon Scarlet") == 1
    assert match_rank(patterns, "Pokémon Violet") == 2


@pytest.mark.parametrize(
    ("entry", "game_name"),
    [
        ("pokemon", "Pokémon"),
        ("WARFRAME", "Warframe"),
        ("Ratchet and Clank", "Ratchet & Clank"),
        ("Tom Clancys Rainbow Six Siege", "Tom Clancy's Rainbow Six: Siege"),
    ],
)
def test_matches_ignores_case_accents_and_punctuation(entry, game_name):
    assert matches(compile_pattern(entry), game_name)


def test_matches_an_entry_without_a_wildcard_to_one_game_only():
    assert not matches(compile_pattern("Rust"), "Rust Console Edition")
    assert matches(compile_pattern("Rust*"), "Rust Console Edition")


def test_matches_star_also_matches_no_characters():
    assert matches(compile_pattern("Call of Duty*"), "Call of Duty")


def test_matches_question_mark_stands_for_exactly_one_character():
    assert matches(compile_pattern("Final Fantasy ?"), "Final Fantasy X")
    assert not matches(compile_pattern("Final Fantasy ?"), "Final Fantasy XV")
    assert matches(compile_pattern("Final Fantasy ??"), "Final Fantasy XV")
    assert not matches(compile_pattern("Final Fantasy ??"), "Final Fantasy X")


def test_compile_pattern_keeps_a_space_next_to_a_wildcard():
    assert matches(compile_pattern("Battlefield ?"), "Battlefield 6")
    assert not matches(compile_pattern("Battlefield ?"), "Battlefield6")
    assert matches(compile_pattern("Call *"), "Call of Duty")
    assert not matches(compile_pattern("Call *"), "Callisto Protocol")
    assert not matches(compile_pattern("Call of Duty *"), "Call of Duty")


def test_compile_pattern_matches_with_or_without_a_space_before_a_star():
    assert matches(compile_pattern("* Online"), "Dungeons & Dragons Online")
    assert matches(compile_pattern("*Online"), "Dungeons & Dragons Online")
    assert matches(compile_pattern("Battlefield*"), "Battlefield 6")


@pytest.mark.parametrize(
    ("entry", "game_name"),
    [
        ("Half-Life: ?", "Half-Life 2"),
        ("Half-Life:?", "Half-Life 2"),
        ("S.T.A.L.K.E.R.?*", "S.T.A.L.K.E.R. 2: Heart of Chornobyl"),
        ("Ratchet &*", "Ratchet & Clank"),
        ("Call of Duty* - *", "Call of Duty: Black Ops 6 - Zombies"),
    ],
)
def test_compile_pattern_turns_punctuation_next_to_a_wildcard_into_one_space(entry, game_name):
    assert matches(compile_pattern(entry), game_name)


def test_compile_pattern_reads_an_apostrophe_next_to_a_wildcard_as_no_character():
    assert matches(compile_pattern("*'s Creed"), "Assassin's Creed")
    assert not matches(compile_pattern("Assassin?s Creed"), "Assassin's Creed")


def test_compile_pattern_ignores_spaces_at_the_ends_of_an_entry():
    assert matches(compile_pattern(" *Online "), "Dungeons & Dragons Online")
    assert matches(compile_pattern("Battlefield* "), "Battlefield 6")
    assert matches(compile_pattern(" Warframe "), "Warframe")


def test_compile_pattern_reads_a_question_mark_in_a_game_name_as_a_wildcard():
    assert not matches(compile_pattern("Who's Your Daddy?!"), "Who's Your Daddy?!")
    assert matches(compile_pattern("Whos Your Daddy"), "Who's Your Daddy?!")


def test_compile_pattern_returns_the_cached_pattern_for_the_same_entry():
    assert compile_pattern("Warframe") is compile_pattern("Warframe")


def test_compile_patterns_compiles_each_entry_of_a_set():
    patterns = compile_patterns({"Rust", "Warframe"})
    assert len(patterns) == 2
    assert any_match(patterns, "warframe")
    assert any_match(patterns, "RUST")


def test_compile_patterns_returns_an_empty_list_for_no_entries():
    assert compile_patterns([]) == []


def test_any_match_is_true_when_one_entry_matches():
    patterns = compile_patterns(["Rust", "Pokemon*"])
    assert any_match(patterns, "Pokémon Violet")
    assert not any_match(patterns, "Rust Console Edition")


def test_any_match_is_false_without_entries():
    assert not any_match([], "Rust")


def test_matching_names_returns_the_matched_names_sorted():
    names = {"Warframe", "Pokémon Violet", "Pokémon Scarlet"}
    assert matching_names(compile_pattern("Pokemon*"), names) == ["Pokémon Scarlet", "Pokémon Violet"]


def test_matching_names_returns_an_empty_list_when_no_name_matches():
    assert matching_names(compile_pattern("Halo*"), ["Warframe"]) == []
    assert matching_names(compile_pattern("Halo*"), []) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Pokemon*", True), ("Final Fantasy ?", True), ("Warframe", False), ("", False)],
)
def test_has_wildcard_finds_a_star_or_a_question_mark(text, expected):
    assert has_wildcard(text) is expected


@pytest.mark.xfail(strict=True, reason=TRADEMARK_REASON)
def test_matches_ignores_the_trademark_sign():
    assert matches(compile_pattern("Warframe"), "Warframe™")


def test_matches_tells_apart_entries_written_in_cyrillic():
    assert not matches(compile_pattern("Мир танков"), "Мир кораблей")


def test_compile_pattern_matches_wildcards_in_any_script():
    assert matches(compile_pattern("Мир*"), "Мир танков")
    assert not matches(compile_pattern("Мир*"), "Тетрис")
    assert matches(compile_pattern("原?"), "原神")


def test_match_rank_ranks_an_entry_written_in_cjk():
    assert match_rank(compile_patterns(["Warframe", "原神"]), "原神") == 1


def test_compile_pattern_matches_one_hangul_syllable_with_one_question_mark():
    assert matches(compile_pattern("원?"), "원신")
    assert not matches(compile_pattern("원???"), "원신")
