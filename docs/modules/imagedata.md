# `imagedata.py`

**Purpose.** `decode_image` decodes the body of an image download for `ImageCache.get` in `cache.py`
([cache.md](cache.md#broken-data)). `PIL.Image.open` reads only an image's header, so an image cut off after its
header opens without an error and fails at its first use. In `get()` that use is the hash and the save, which run
after the handling of a failed download, so the error would end the run, and the restart would begin with a full
reload. The module imports no Pillow and sends no request, so a test runs it with a fake opener.

## Public contract

- `decode_image(data, open_image)` calls `open_image` with `data` in an `io.BytesIO`, then calls `load()` on the
  result to decode the rest of the data, and returns the result. It returns None when either call raises
  `OSError`. Pillow raises `UnidentifiedImageError`, a subclass of `OSError`, for data that is not an image, and
  `OSError("image file is truncated")` for an image cut off after its header.
- An error that is not an `OSError` passes up to the caller. `get()` catches it with the download's other errors.
- `Decodable` is the `Protocol` of the opened image: an object with a `load()` method. A Pillow image is one.

**Dependencies.** None: the standard library only.
