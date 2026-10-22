import pytest

from gamelib import ROMAN_NUMERALS, LocalGame, MatchKind, Platform, match_games


def match_one(local_name, game_names):
    return [
        (match.game_name, match.kind)
        for match in match_games([LocalGame(local_name, Platform.STEAM)], game_names)
    ]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("FINAL FANTASY XVI", "Final Fantasy XVII"),
        ("Final Fantasy XX", "Final Fantasy XXI"),
        ("Romance of the Three Kingdoms XXXIX", "Romance of the Three Kingdoms XXXVIII"),
    ],
)
def test_match_games_gives_no_fuzzy_match_when_a_roman_numeral_above_15_differs(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [("Final Fantasy XVI", "Final Fantasy 16"), ("Final Fantasy 39", "Final Fantasy XXXIX")],
)
def test_match_games_pairs_a_roman_numeral_above_15_with_its_digits_as_variant(local_name, game_name):
    assert match_one(local_name, [game_name]) == [(game_name, MatchKind.VARIANT)]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("Final Fantasy IIII", "Final Fantasy 4"),
        ("Final Fantasy XIIX", "Final Fantasy 18"),
        ("Mortal Kombat XL", "Mortal Kombat 40"),
        ("Puzzle Mix", "Puzzle 1009"),
        ("LEGO DC Heroes", "LEGO 600 Heroes"),
    ],
    ids=["four i", "x before ix", "xl", "mix", "dc"],
)
def test_match_games_keeps_a_word_that_is_not_a_correct_numeral_below_40_as_a_word(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


def test_roman_numerals_lists_2_to_39_without_the_lone_letters():
    assert sorted(map(int, ROMAN_NUMERALS.values())) == [number for number in range(2, 40) if number not in (5, 10)]
    assert (ROMAN_NUMERALS["xix"], ROMAN_NUMERALS["xxiv"], ROMAN_NUMERALS["xxxix"]) == ("19", "24", "39")


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("NINJA GAIDEN Σ", "Ninja Gaiden"),
        ("Ninja Gaiden", "NINJA GAIDEN Σ"),
        ("NINJA GAIDEN Σ", "NINJA GAIDEN Ω"),
        ("Kingdom Hearts χ Back Cover", "Kingdom Hearts Back Cover"),
        ("New Super Mario Bros. U", "New Super Mario Bros."),
        ("Persona Q: Shadow of the Labyrinth", "Persona: Shadow of the Labyrinth"),
    ],
    ids=[
        "greek letter at the end", "greek letter on the twitch side", "another greek letter",
        "greek letter inside the name", "latin letter at the end", "latin letter inside the name",
    ],
)
def test_match_games_gives_no_fuzzy_match_when_a_lone_letter_differs(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


@pytest.mark.parametrize(
    ("local_name", "game_name", "kind"),
    [
        ("Dragon Ball Z: Kakarott", "Dragon Ball Z: Kakarot", MatchKind.FUZZY),
        ("NINJA GAIDEN Σ", "Ninja Gaiden: Σ", MatchKind.EXACT),
        ("New Super Mario Bros. U Deluxe", "New Super Mario Bros. U", MatchKind.VARIANT),
    ],
)
def test_match_games_pairs_names_with_the_same_lone_letters(local_name, game_name, kind):
    assert match_one(local_name, [game_name]) == [(game_name, kind)]


def test_match_games_gives_no_fuzzy_match_when_one_name_lacks_the_article_a():
    # The cost that ADR-0004 accepts: the article "a" is a lone letter too.
    assert match_one("A Plague Tale: Innocence", ["Plague Tale: Innocence"]) == []
