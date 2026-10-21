import io

import pytest

from imagedata import decode_image, png_mode

SIGNATURE = b"\x89PNG\r\n\x1a\n"
END = b"IEND"


class FakePng:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.pixels: bytes | None = None

    def load(self) -> None:
        body = self._data[len(SIGNATURE):]
        if not body.endswith(END):
            raise OSError("image file is truncated")
        self.pixels = body[:-len(END)]


def open_png(fp: io.BytesIO) -> FakePng:
    data = fp.read()
    if not data.startswith(SIGNATURE):
        raise OSError("cannot identify image file")
    return FakePng(data)


class DecompressionBombError(Exception):
    pass


def open_bomb(fp: io.BytesIO) -> FakePng:
    raise DecompressionBombError("Image size exceeds limit")


def test_decode_image_returns_the_image_with_its_data_decoded():
    image = decode_image(SIGNATURE + b"pixels" + END, open_png)
    assert image is not None
    assert image.pixels == b"pixels"


def test_decode_image_returns_none_for_an_image_cut_off_after_its_header():
    assert decode_image(SIGNATURE + b"pix", open_png) is None


def test_decode_image_returns_none_for_a_body_that_is_not_an_image():
    assert decode_image(b"<html>403 Forbidden</html>", open_png) is None


def test_decode_image_returns_none_for_empty_data():
    assert decode_image(b"", open_png) is None


def test_decode_image_passes_up_an_error_that_is_not_an_oserror():
    with pytest.raises(DecompressionBombError):
        decode_image(SIGNATURE + b"pixels" + END, open_bomb)


@pytest.mark.parametrize("mode", ["1", "L", "LA", "I;16", "I;16B", "P", "RGB", "RGBA"])
def test_png_mode_keeps_a_mode_that_png_stores(mode):
    assert png_mode(mode) == mode


@pytest.mark.parametrize("mode", ["CMYK", "YCbCr", "LAB", "HSV", "F", "I", "I;16L", "RGBX"])
def test_png_mode_converts_a_mode_without_transparency_that_png_cannot_store_to_rgb(mode):
    assert png_mode(mode) == "RGB"


@pytest.mark.parametrize("mode", ["PA", "RGBa"])
def test_png_mode_converts_a_mode_with_transparency_that_png_cannot_store_to_rgba(mode):
    assert png_mode(mode) == "RGBA"
