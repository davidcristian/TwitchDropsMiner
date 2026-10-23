from __future__ import annotations

import pytest

from utils import Game


def test_a_game_reads_its_id_as_a_number_and_prefers_the_display_name():
    game = Game({"id": "509658", "name": "just chatting", "displayName": "Just Chatting"})

    assert (game.id, game.name, str(game)) == (509658, "Just Chatting", "Just Chatting")
    assert repr(game) == "Game(509658, Just Chatting)"


@pytest.mark.parametrize("data", [
    {"id": "1", "name": "Rust"},
    {"id": "1", "name": "Rust", "displayName": None},
    {"id": "1", "name": "Rust", "displayName": ""},
])
def test_a_game_without_a_display_name_takes_its_name(data):
    assert Game(data).name == "Rust"


@pytest.mark.parametrize("data", [{"id": "1"}, {"name": "Rust"}])
def test_a_game_without_an_id_or_a_name_raises_key_error(data):
    with pytest.raises(KeyError):
        Game(data)


def test_a_game_keeps_the_slug_of_its_data():
    assert Game({"id": "1", "name": "Pokémon GO", "slug": "pokemon-go"}).slug == "pokemon-go"


@pytest.mark.parametrize("name, slug", [
    ("World of Warcraft", "world-of-warcraft"),
    ("Tom Clancy's Rainbow Six Siege", "tom-clancys-rainbow-six-siege"),
    ("  Counter-Strike: Global Offensive!", "counter-strike-global-offensive"),
    ("Hearts_of_Iron IV", "hearts_of_iron-iv"),
    ("Pokémon", "pokémon"),
    ("!!!", ""),
])
def test_a_game_without_a_slug_makes_one_from_its_name(name, slug):
    assert Game({"id": "1", "name": name}).slug == slug


def test_games_with_the_same_id_are_equal_and_hash_alike():
    first, second = Game({"id": "1", "name": "A"}), Game({"id": 1, "name": "B"})

    assert first == second and hash(first) == hash(second)
    assert len({first, second}) == 1
    assert first != Game({"id": "2", "name": "A"})


def test_a_game_is_not_equal_to_its_id():
    assert Game({"id": "1", "name": "A"}) != 1


@pytest.mark.parametrize("game_id, special", [(509663, True), (509672, True), (509658, False)])
def test_is_special_is_true_for_the_special_game_ids(game_id, special):
    assert Game({"id": game_id, "name": "A"}).is_special() is special
