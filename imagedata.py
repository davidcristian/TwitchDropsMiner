"""Decode the data of a downloaded image."""
from __future__ import annotations

import io
from collections import abc
from typing import Protocol, TypeVar


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
