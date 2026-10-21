# `imagedata.py`

**Purpose.** `decode_image` decodes the body of an image download for `ImageCache.get` in `cache.py`
([cache.md](cache.md#broken-data)). `PIL.Image.open` reads only an image's header, so an image cut off after its
header opens without an error and fails at its first use. In `get()` that use is the hash and the save, which run
after the handling of a failed download, so the error would end the run, and the restart would begin with a full
reload. `png_mode` chooses the mode in which `get()` saves the image, because Pillow cannot write every mode as
PNG: a CMYK JPEG raises `OSError: cannot write mode CMYK as PNG` at the save. The module imports no Pillow and
sends no request, so a test runs it with a fake opener and plain mode names.

## Public contract

- `decode_image(data, open_image)` calls `open_image` with `data` in an `io.BytesIO`, then calls `load()` on the
  result to decode the rest of the data, and returns the result. It returns None when either call raises
  `OSError`. Pillow raises `UnidentifiedImageError`, a subclass of `OSError`, for data that is not an image, and
  `OSError("image file is truncated")` for an image cut off after its header.
- An error that is not an `OSError` passes up to the caller. `get()` catches it with the download's other errors.
- `Decodable` is the `Protocol` of the opened image: an object with a `load()` method. A Pillow image is one.
- `png_mode(mode)` takes a Pillow mode name and returns the mode to convert the image to before the PNG save. It
  returns the same mode for `1`, `L`, `LA`, `I;16`, `I;16B`, `P`, `RGB` and `RGBA`, which Pillow writes as PNG.
  It returns `RGBA` for `PA` and `RGBa`, which have transparency, and `RGB` for every other mode, such as `CMYK`
  and `YCbCr`.
- `png_mode` returns `RGB` for mode `I`, which a TIFF file can have. Pillow 12.3 writes `I` as PNG with a warning
  that Pillow 13 removes this, and the builds install the newest Pillow
  ([task 048](../refinements/tasks/048-builds-install-the-newest-dependencies.md)). The conversion sets each pixel
  above 255 to 255.

**Dependencies.** None: the standard library only.
