from types import SimpleNamespace

import pytest
from PIL import Image

import cache

# Pillow 12.3 warns about `Image.getdata`, which Pillow 14 removes, so a hash that called it would raise there
pytestmark = pytest.mark.filterwarnings("error::DeprecationWarning")


@pytest.fixture
def image_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cache")
    monkeypatch.setattr(cache, "CACHE_DB", tmp_path / "cache" / "mapping.json")
    return cache.ImageCache(SimpleNamespace(_root=None, _twitch=None))


def half_black(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    image.paste("black", (0, 0, size[0] // 2, size[1]))
    return image


def top_half_red(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    image.paste((200, 30, 30), (0, 0, size[0], size[1] // 2))
    return image


# The names are those that the hash gave before, which the files already in `cache/` have
@pytest.mark.parametrize(
    ("image", "name"),
    [
        (half_black((10, 10)), "7c1f07c1f07c1f07c1f07c1f.png"),
        (top_half_red((285, 380)), "3ffffffffffff.png"),
        (Image.new("RGB", (10, 10), "white"), "fffffffffffffffffffffffff.png"),
    ],
)
def test_the_file_name_has_one_bit_for_each_grey_pixel_of_the_image_reduced_to_10_by_10(image_cache, image, name):
    assert image_cache._hash(image) == name
