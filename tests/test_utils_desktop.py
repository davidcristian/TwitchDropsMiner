from __future__ import annotations

import gc
import os
import sys
import tkinter as tk
from types import SimpleNamespace

import pytest
from PIL import Image
from yarl import URL

import utils
from utils import set_root_icon, webopen

LD = "LD_LIBRARY_PATH"
ORIGINAL = "LD_LIBRARY_PATH_ORIG"


@pytest.fixture
def root(display):
    root = tk.Tk()
    yield root
    root.destroy()


def test_set_root_icon_keeps_the_icon_image_after_it_returns(root, tmp_path):
    path = tmp_path / "icon.png"
    Image.new("RGBA", (16, 24), "red").save(path)
    before = set(root.tk.call("image", "names"))

    set_root_icon(root, path)
    gc.collect()

    images = set(root.tk.call("image", "names")) - before
    assert [(root.tk.call("image", "width", name), root.tk.call("image", "height", name)) for name in images] == [
        (16, 24)
    ]


def test_set_root_icon_of_a_missing_file_raises_file_not_found_error(root, tmp_path):
    with pytest.raises(FileNotFoundError):
        set_root_icon(root, tmp_path / "missing.png")


@pytest.fixture
def opened(monkeypatch) -> list[tuple[str, str | None]]:
    """Replace the browser with one that records each URL and the LD_LIBRARY_PATH it starts with."""
    calls: list[tuple[str, str | None]] = []
    browser = SimpleNamespace(open_new_tab=lambda url: calls.append((url, os.environ.get(LD))))
    monkeypatch.setattr(utils, "webbrowser", browser)
    monkeypatch.delenv(LD, raising=False)
    monkeypatch.delenv(ORIGINAL, raising=False)
    return calls


@pytest.mark.parametrize("packaged, platform", [(False, "linux"), (True, "win32"), (True, "darwin")])
def test_webopen_opens_the_url_with_the_environment_as_it_is(opened, monkeypatch, packaged, platform):
    monkeypatch.setattr(utils, "IS_PACKAGED", packaged)
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv(LD, "/bundle")
    monkeypatch.setenv(ORIGINAL, "/system")

    webopen(URL("https://www.twitch.tv/drops/inventory"))

    assert opened == [("https://www.twitch.tv/drops/inventory", "/bundle")]
    assert (os.environ.get(LD), os.environ.get(ORIGINAL)) == ("/bundle", "/system")


@pytest.mark.parametrize("current, original", [
    ("/bundle", "/system"), ("/bundle", None), (None, "/system"), (None, None),
])
def test_webopen_in_a_packaged_linux_build_starts_the_browser_with_the_original_library_path(
    opened, monkeypatch, current, original
):
    monkeypatch.setattr(utils, "IS_PACKAGED", True)
    monkeypatch.setattr(sys, "platform", "linux")
    for name, value in ((LD, current), (ORIGINAL, original)):
        if value is not None:
            monkeypatch.setenv(name, value)

    webopen("https://www.twitch.tv")

    assert opened == [("https://www.twitch.tv", original)]
    assert (os.environ.get(LD), os.environ.get(ORIGINAL)) == (current, original)
