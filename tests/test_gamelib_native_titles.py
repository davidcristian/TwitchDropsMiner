import pytest

from gamelib import LocalGame, MatchKind, Platform, match_games


def match_one(local_name, game_names):
    return [
        (match.game_name, match.kind)
        for match in match_games([LocalGame(local_name, Platform.STEAM)], game_names)
    ]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("原神 Genshin Impact", "Genshin Impact"),
        ("鬼谷八荒 Tale of Immortal", "Tale of Immortal"),
        ("東方紅魔郷 ～ the Embodiment of Scarlet Devil.", "The Embodiment of Scarlet Devil"),
        ("Мир танков World of Tanks", "World of Tanks"),
        ("鬼谷八荒 Tale of Immortal - Deluxe Edition", "Tale of Immortal"),
        ("泰拉瑞亚 Terraria", "Terraria"),
    ],
    ids=["han", "numeral inside the native title", "kanji", "cyrillic", "edition words", "eight characters"],
)
def test_match_games_pairs_the_english_title_after_a_native_title_as_variant(local_name, game_name):
    assert match_one(local_name, ["Warframe", game_name]) == [(game_name, MatchKind.VARIANT)]


def test_match_games_pairs_a_close_english_title_after_a_native_title_as_fuzzy():
    [match] = match_games([LocalGame("雀魂麻將(MahjongSoul)", Platform.STEAM)], ["Mahjong Soul"])
    assert (match.game_name, match.kind) == ("Mahjong Soul", MatchKind.FUZZY)
    assert match.ratio == pytest.approx(22 / 23)


def test_match_games_prefers_the_whole_name_to_its_english_title():
    assert match_one("原神 Genshin Impact", ["Genshin Impact", "原神 Genshin Impact"]) == [
        ("原神 Genshin Impact", MatchKind.EXACT)
    ]


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("仙剑奇侠传七 Sword and Fairy", "Sword and Fairy"),
        ("三國志14 Romance of the Three Kingdoms", "Romance of the Three Kingdoms"),
        ("महा२भारत War of Kings", "War of Kings"),
        ("仙剑奇侠传 Sword and Fairy 7", "Sword and Fairy"),
        ("三國志 Romance of the Three Kingdoms 十四", "Romance of the Three Kingdoms"),
    ],
    ids=[
        "numeral at the end of the native title", "digits in the native title", "digit of another script inside it",
        "number in the english title", "numeral after the english title",
    ],
)
def test_match_games_gives_no_match_when_a_sequel_number_is_in_one_script_only(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("仙剑奇侠传 Sword and Fairy", "轩辕剑 Sword and Fairy"),
        ("仙剑奇侠传 Romance of the Three Kingdoms", "三國志 Romance of the Three Kingdoms"),
        ("侠客风云传 Tale of Wuxia", "Tale of Wuxia: The Pre-Sequel"),
        ("侠客风云传前传 Tale of Wuxia：The Pre-Sequel", "Tale of Wuxia"),
    ],
    ids=["other native title", "other native title and a long english title", "prequel", "sequel"],
)
def test_match_games_tells_apart_two_games_that_share_the_english_title(local_name, game_name):
    assert match_one(local_name, [game_name]) == []


@pytest.mark.parametrize(
    ("local_name", "game_name"),
    [
        ("Escape from Tarkov: Арена", "Escape from Tarkov"),
        ("ΔV: Rings of Saturn", "Rings of Saturn"),
        ("蔚蓝 Celeste", "Celeste"),
    ],
    ids=["native words after the english title", "latin letter in the first word", "seven characters"],
)
def test_match_games_keeps_the_whole_name_without_a_leading_native_title_and_a_long_english_title(
    local_name, game_name
):
    assert match_one(local_name, [game_name]) == []


def test_match_games_gives_no_match_when_the_english_title_fits_two_twitch_names():
    assert match_one("原神 Genshin Impact", ["Genshin Impact", "Genshin: Impact"]) == []
