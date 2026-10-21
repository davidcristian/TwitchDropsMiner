"""Decode the data of a downloaded image and choose the mode it is saved in."""
from __future__ import annotations

import io
from collections import abc
from typing import Protocol, TypeVar

# Pillow 12 also writes mode I as PNG, with a warning that Pillow 13 removes it.
_PNG_MODES = frozenset({"1", "L", "LA", "I;16", "I;16B", "P", "RGB", "RGBA"})
_TRANSPARENT_MODES = frozenset({"PA", "RGBa"})


class Decodable(Protocol):
    """An opened image whose `load()` decodes the data after its header."""

    def load(self) -> object: ...


ImageT = TypeVar("ImageT", bound=Decodable)


def decode_image(data: bytes, open_image: abc.Callable[[io.BytesIO], ImageT]) -> ImageT | None:
    """Return the image in data, decoded in full, or None when opening or decoding it raises OSError.

    open_image is `PIL.Image.open`, which reads only the header, so an image cut off later fails at `load()`.
    """
    try:
        image = open_image(io.BytesIO(data))
        image.load()
    except OSError:
        return None
    return image


def png_mode(mode: str) -> str:
    """Return the Pillow mode to convert an image of the given mode to before it is saved as PNG."""
    if mode in _PNG_MODES:
        return mode
    return "RGBA" if mode in _TRANSPARENT_MODES else "RGB"
