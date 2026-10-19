import pytest

from gamelib import FUZZY_THRESHOLD, GameMatch, LocalGame, MatchKind, Platform, match_games, normalize

TRADEMARK_REASON = (
    "normalize turns the ™ sign into the letters tm "
    "(docs/refinements/tasks/009-trademark-symbols-in-game-names.md)"
)


def match_one(local_name, game_names):
    return [
        (match.game_name, match.kind)
        for match in match_games([LocalGame(local_name, Platform.STEAM)], game_names)
    ]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Pokémon", "pokemon"), ("ÉLDEN RING", "elden ring"), ("ＤＯＯＭ", "doom")],
)
def test_normalize_removes_accents_and_case(name, expected):
    assert normalize(name) == expected


@pytest.mark.parametrize("name", ["Clancy's", "Clancy’s", "Clancyʼs"])
def test_normalize_removes_apostrophes_without_a_gap(name):
    assert normalize(name) == "clancys"


def test_normalize_writes_an_ampersand_as_and():
    assert normalize("Ratchet & Clank") == "ratchet and clank"
    assert normalize("R&D") == "r and d"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Tom Clancy's Rainbow Six: Siege", "tom clancys rainbow six siege"),
        ("  Half-Life:   Alyx  ", "half life alyx"),
        ("Warframe®", "warframe"),
        ("Baldur's Gate 3", "baldurs gate 3"),
    ],
)
def test_normalize_turns_other_characters_into_single_spaces(name, expected):
    assert normalize(name) == expected


@pytest.mark.parametrize("name", ["", "!!!", "®"])
def test_normalize_returns_an_empty_string_for_a_name_without_letters_or_digits(name):
    assert normalize(name) == ""


def test_match_games_pairs_equal_normalized_names_as_exact():
    local = LocalGame("Pokemon Scarlet", Platform.STEAM)
    assert match_games([local], ["Warframe", "Pokémon Scarlet"]) == [
        GameMatch("Pokémon Scarlet", local, MatchKind.EXACT, 1.0)
    ]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [("Dark Souls 3", "Dark Souls III"), ("Dark Souls III", "Dark Souls 3")],
)
def test_match_games_pairs_roman_numerals_with_digits_as_variant(local_name, game_name):
    assert match_one(local_name, [game_name]) == [(game_name, MatchKind.VARIANT)]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("Mafia: Definitive Edition", "Mafia"),
        ("Mafia", "Mafia: Definitive Edition"),
        ("The Witcher 3: Wild Hunt - Game of the Year Edition", "The Witcher 3: Wild Hunt"),
        ("Dark Souls III: Deluxe Edition", "Dark Souls 3"),
    ],
)
def test_match_games_removes_trailing_edition_words_as_variant(local_name, game_name):
    assert match_one(local_name, [game_name]) == [(game_name, MatchKind.VARIANT)]


def test_match_games_pairs_v_and_5_by_a_fuzzy_match_only():
    assert match_one("Grand Theft Auto 5", ["Grand Theft Auto V"]) == [("Grand Theft Auto V", MatchKind.FUZZY)]


def test_match_games_keeps_a_lone_x_as_a_letter_for_exact_and_variant_matches():
    assert match_one("Mega Man X", ["Mega Man X"]) == [("Mega Man X", MatchKind.EXACT)]
    assert match_one("Mega Man X", ["Mega Man 10"]) == []


def test_match_games_prefers_an_exact_match_to_a_variant():
    assert match_one("Dark Souls Remastered", ["Dark Souls", "Dark Souls: Remastered"]) == [
        ("Dark Souls: Remastered", MatchKind.EXACT)
    ]


def test_match_games_gives_no_match_when_two_names_are_equal_after_normalizing():
    assert match_one("Halo Infinite", ["Halo Infinite", "Halo: Infinite"]) == []


def test_match_games_gives_no_match_when_two_variants_fit():
    assert match_one("Mafia", ["Mafia: Definitive Edition", "Mafia: Deluxe Edition"]) == []


def test_match_games_counts_a_repeated_twitch_name_once():
    # detect_games passes the game of each campaign, so a game with two campaigns comes twice
    assert match_one("Warframe", ["Warframe", "Warframe"]) == [("Warframe", MatchKind.EXACT)]


def test_match_games_pairs_a_close_long_name_as_fuzzy_with_its_ratio():
    local = LocalGame("Stardew Valey", Platform.STEAM)
    [match] = match_games([local], ["Stardew Valley", "Star Wars Outlaws"])
    assert (match.game_name, match.kind) == ("Stardew Valley", MatchKind.FUZZY)
    assert match.ratio == pytest.approx(26 / 27)


def test_match_games_rejects_a_fuzzy_ratio_below_the_threshold():
    assert match_one("Monster Hunter Wilds", ["Monster Hunter World"]) == []


def test_match_games_accepts_a_fuzzy_ratio_equal_to_the_threshold():
    # 23 equal characters out of 25 on each side give a ratio of exactly 0.92
    local_name, game_name = "abcdefghijklmnopqrstuvwxy", "abcdefghijklmnopqrstuvwzz"
    [match] = match_games([LocalGame(local_name, Platform.STEAM)], [game_name])
    assert (match.kind, match.ratio) == (MatchKind.FUZZY, FUZZY_THRESHOLD)


def test_match_games_needs_a_long_name_on_both_sides_for_a_fuzzy_match():
    assert match_one("Fortnit", ["Fortnite"]) == []
    assert match_one("Fortnite", ["Fortnit"]) == []


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [("Counter-Strike 2", "Counter-Strike"), ("Counter-Strike", "Counter-Strike 2")],
)
def test_match_games_needs_the_same_numbers_for_a_fuzzy_match(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


@pytest.mark.parametrize(
    "game_names",
    [["Stardew Valley", "Stardew Valleys"], ["Stardew Valleys", "Stardew Valley"]],
)
def test_match_games_gives_no_fuzzy_match_when_a_second_name_reaches_the_threshold(game_names):
    assert match_one("Stardew Valey", game_names) == []


def test_match_games_skips_names_without_letters_or_digits():
    assert match_one("!!!", ["???"]) == []


def test_match_games_sorts_matches_by_twitch_name_ignoring_case():
    local_games = [LocalGame(name, Platform.STEAM) for name in ["Warframe", "Baldurs Gate 3", "Apex Legends"]]
    result = match_games(local_games, ["Warframe", "baldur's gate 3", "Apex Legends"])
    assert [match.game_name for match in result] == ["Apex Legends", "baldur's gate 3", "Warframe"]


def test_match_games_reads_the_twitch_names_from_a_generator():
    names = (name for name in ["Warframe", "Rust"])
    assert match_one("Warframe", names) == [("Warframe", MatchKind.EXACT)]


def test_match_games_returns_an_empty_list_for_empty_input():
    assert match_games([], ["Warframe"]) == []
    assert match_one("Warframe", []) == []


@pytest.mark.xfail(strict=True, reason=TRADEMARK_REASON)
def test_normalize_removes_the_trademark_sign():
    assert normalize("DOOM™") == "doom"


@pytest.mark.xfail(strict=True, reason=TRADEMARK_REASON)
def test_match_games_pairs_a_name_with_the_trademark_sign_as_exact():
    assert match_one("Warframe™", ["Warframe"]) == [("Warframe", MatchKind.EXACT)]


def test_match_games_tells_apart_names_written_in_cyrillic():
    assert match_one("Мир танков 2", ["Тетрис 2"]) == []


def test_match_games_needs_the_same_single_letter_numeral_for_a_fuzzy_match():
    assert match_one("Grand Theft Auto V", ["Grand Theft Auto"]) == []


@pytest.mark.parametrize(
    ("name", "normalized"),
    [
        ("Мир танков", "мир танков"),
        ("原神", "原神"),
        ("ΣΊΣΥΦΟΣ", "σισυφοσ"),
        ("Straße", "strasse"),
        ("snake_case_game", "snake case game"),
        ("Война", "война"),
        ("ｶﾞﾝﾀﾞﾑ", "ガンダム"),
        ("हिंदी", "हिंदी"),
        ("Æterna Noctis", "aeterna noctis"),
        ("Łódź Kıyamet Ørnen", "lodz kiyamet ornen"),
        ("Clancy\u00b4s Hawai\u02bbi", "clancys hawaii"),
    ],
    ids=[
        "cyrillic", "cjk", "greek accents and final sigma", "sharp s folds to ss", "underscore separates",
        "cyrillic short i stays", "half-width kana join their marks", "devanagari vowel signs stay in the word",
        "latin ligature", "latin letters without an accent form", "more apostrophes",
    ],
)
def test_normalize_keeps_the_letters_of_every_script_and_folds_case(name, normalized):
    assert normalize(name) == normalized


def test_normalize_matches_a_name_whatever_its_case_in_any_script():
    assert normalize("МИР ТАНКОВ") == normalize("мир танков")
    assert normalize("STRASSE") == normalize("Straße")


def test_match_games_pairs_the_same_cyrillic_name_as_exact():
    assert match_one("Мир Танков", ["Мир танков"]) == [("Мир танков", MatchKind.EXACT)]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [("Final Fantasy X", "Final Fantasy"), ("Sid Meier's Civilization V", "Sid Meier's Civilization")],
)
def test_match_games_gives_no_fuzzy_match_when_a_lone_numeral_differs(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


def test_normalize_keeps_letters_that_differ_only_by_a_mark_apart_outside_latin_and_greek():
    assert normalize("Война") != normalize("Воина")
    assert normalize("ガンダム") != normalize("カンタム")
    assert len(normalize("원신")) == 2


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("NINJA GAIDEN \u03a3", "NINJA GAIDEN \u03a32"),
        ("Lineage2 Revolution", "Lineage3 Revolution"),
        ("三國志14 with パワーアップキット", "三國志13 with パワーアップキット"),
    ],
    ids=["after a greek letter", "after a latin letter", "after a han letter"],
)
def test_match_games_reads_the_digits_inside_a_word_as_a_number(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


def test_match_games_pairs_a_number_inside_a_word_with_the_same_number_alone():
    assert match_one("Lineage2 Revolution", ["Lineage 2 Revolution"]) == [("Lineage 2 Revolution", MatchKind.FUZZY)]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [("Mortal Kombat XL", "Mortal Kombat X"), ("The Elder Scrolls V: Skyrim", "The Elder Scrolls: Skyrim")],
)
def test_match_games_gives_no_fuzzy_match_when_one_name_lacks_its_lone_numeral(local_name, game_name):
    # The cost that ADR-0004 accepts: the same game written with and without its numeral is not paired.
    assert match_one(local_name, [game_name]) == []
