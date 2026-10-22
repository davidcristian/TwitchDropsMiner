from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import aiohttp
import pytest
from PIL import Image
from yarl import URL

import cache
from exceptions import ExitRequest, ReloadRequest
from fakes import FakeResponse, FakeTwitch
from utils import json_save

# Pillow 12.3 warns about `Image.getdata`, which Pillow 14 removes, so a hash that called it would raise there
pytestmark = pytest.mark.filterwarnings("error::DeprecationWarning")
IMAGE_URL = "https://example.invalid/reward.png"
WHITE_NAME = "fffffffffffffffffffffffff.png"


@pytest.fixture
def image_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cache")
    monkeypatch.setattr(cache, "CACHE_DB", tmp_path / "cache" / "mapping.json")
    return cache.ImageCache(SimpleNamespace(_root=None, _twitch=None))


class FakePhoto:
    """A `PhotoImage` that keeps the image it was made from, so a test needs no Tk window."""

    def __init__(self, master: None, image: Image.Image) -> None:
        self.image = image


@pytest.fixture
def cache_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(cache, "CACHE_PATH", tmp_path / "cache")
    monkeypatch.setattr(cache, "CACHE_DB", tmp_path / "cache" / "mapping.json")
    monkeypatch.setattr(cache, "PhotoImage", FakePhoto)
    return tmp_path / "cache"


def new_cache(twitch: FakeTwitch) -> cache.ImageCache:
    return cache.ImageCache(SimpleNamespace(_root=None, _twitch=twitch))


def half_black(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    image.paste("black", (0, 0, size[0] // 2, size[1]))
    return image


def top_half_red(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    image.paste((200, 30, 30), (0, 0, size[0], size[1] // 2))
    return image


class ImageResponse(FakeResponse):
    """A response whose body is an image saved as PNG."""

    def __init__(self, image: Image.Image) -> None:
        super().__init__()
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        self.data = buffer.getvalue()

    async def read(self) -> bytes:
        return self.data


def answers(*responses: Callable[[], FakeResponse]) -> Callable[[str, URL], FakeResponse]:
    """Return an HTTP answer that calls the next function of responses for each request."""
    queue = list(responses)
    return lambda method, url: queue.pop(0)()


def raises(error: Exception) -> Callable[[], FakeResponse]:
    def answer() -> FakeResponse:
        raise error

    return answer


def is_white(image: Image.Image, size: tuple[int, int]) -> bool:
    return image.size == size and image.getextrema() == ((255, 255),) * 3


FAILURES = {
    "404": lambda: FakeResponse(404),
    "403 page": lambda: FakeResponse(403, "<html>Forbidden</html>"),
    "200 page": lambda: FakeResponse(200, "<html>Log in to this network</html>"),
    "error": raises(aiohttp.InvalidURL(IMAGE_URL)),
}


# The names are those that the hash gave before, which the files already in `cache/` have
@pytest.mark.parametrize(
    ("image", "name"),
    [
        (half_black((10, 10)), "7c1f07c1f07c1f07c1f07c1f.png"),
        (top_half_red((285, 380)), "3ffffffffffff.png"),
        (Image.new("RGB", (10, 10), "white"), WHITE_NAME),
    ],
)
def test_the_file_name_has_one_bit_for_each_grey_pixel_of_the_image_reduced_to_10_by_10(image_cache, image, name):
    assert image_cache._hash(image) == name


@pytest.mark.parametrize("failure", FAILURES.values(), ids=FAILURES.keys())
def test_a_failed_download_shows_a_white_image_and_the_next_start_downloads_it_again(cache_folder, failure):
    twitch = FakeTwitch(http=answers(failure, lambda: ImageResponse(half_black((80, 80)))))

    async def scenario() -> tuple[FakePhoto, FakePhoto]:
        first_run = new_cache(twitch)
        blank = await first_run.get(IMAGE_URL, (80, 80))
        first_run.save(force=True)
        return blank, await new_cache(twitch).get(IMAGE_URL, (80, 80))

    blank, image = asyncio.run(scenario())

    assert is_white(blank.image, (80, 80))
    assert image.image.tobytes() == half_black((80, 80)).tobytes()
    assert twitch.http_sent == ["GET example.invalid"] * 2


def test_a_failed_download_is_sent_once_until_the_next_reload_and_then_again(cache_folder):
    twitch = FakeTwitch(http=answers(FAILURES["404"], lambda: ImageResponse(half_black((80, 80)))))
    image_cache = new_cache(twitch)

    async def scenario() -> tuple[list[FakePhoto], int, FakePhoto]:
        before = [await image_cache.get(IMAGE_URL, size) for size in ((80, 80), (108, 144), None)]
        sent = len(twitch.http_sent)
        image_cache.retry_failed()
        return before, sent, await image_cache.get(IMAGE_URL, (80, 80))

    before, sent_before_reload, after = asyncio.run(scenario())

    assert [is_white(photo.image, size) for photo, size in zip(before, ((80, 80), (108, 144), (10, 10)))] == [True] * 3
    assert sent_before_reload == 1
    assert after.image.tobytes() == half_black((80, 80)).tobytes()
    assert len(twitch.http_sent) == 2


@pytest.mark.parametrize("request_class", [ExitRequest, ReloadRequest])
def test_an_exit_or_reload_during_a_download_passes_up_and_maps_nothing(cache_folder, request_class):
    image_cache = new_cache(FakeTwitch(http=answers(raises(request_class()))))

    with pytest.raises(request_class):
        asyncio.run(image_cache.get(IMAGE_URL, (80, 80)))
    image_cache.save(force=True)

    assert json.loads((cache_folder / "mapping.json").read_text()) == {}


def test_a_url_mapped_to_the_white_image_of_an_old_failed_download_is_downloaded_again(cache_folder):
    cache_folder.mkdir()
    Image.new("RGB", (10, 10), "white").save(cache_folder / WHITE_NAME)
    expires = datetime.now(timezone.utc) + timedelta(days=3)
    json_save(cache_folder / "mapping.json", {IMAGE_URL: {"hash": WHITE_NAME, "expires": expires}})
    twitch = FakeTwitch(http=answers(lambda: ImageResponse(half_black((80, 80)))))

    image = asyncio.run(new_cache(twitch).get(IMAGE_URL, (80, 80)))

    assert image.image.tobytes() == half_black((80, 80)).tobytes()
    assert twitch.http_sent == ["GET example.invalid"]


def test_an_image_of_one_color_is_loaded_from_its_file_at_the_next_start(cache_folder):
    red = Image.new("RGB", (80, 80), (200, 30, 30))
    twitch = FakeTwitch(http=answers(lambda: ImageResponse(red)))

    async def scenario() -> FakePhoto:
        first_run = new_cache(twitch)
        await first_run.get(IMAGE_URL)
        first_run.save(force=True)
        return await new_cache(twitch).get(IMAGE_URL)

    image = asyncio.run(scenario())

    # every image of one color has the name of the white image
    assert (cache_folder / WHITE_NAME).is_file()
    assert image.image.tobytes() == red.tobytes()
    assert twitch.http_sent == ["GET example.invalid"]


def test_clearing_the_inventory_tab_for_a_reload_lets_a_failed_download_be_sent_again(window):
    twitch = FakeTwitch(http=answers(FAILURES["404"], lambda: ImageResponse(half_black((80, 80)))))
    gui = window(twitch)

    async def scenario() -> None:
        await gui._cache.get(IMAGE_URL, (80, 80))
        await gui._cache.get(IMAGE_URL, (80, 80))
        gui.inv.clear()
        await gui._cache.get(IMAGE_URL, (80, 80))

    asyncio.run(scenario())

    assert twitch.http_sent == ["GET example.invalid"] * 2
