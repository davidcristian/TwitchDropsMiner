# The image hash calls `getdata`, which Pillow 14 removes

**Status:** done 2026-10-22
**Area:** cache
**Origin:** Found on 2026-10-21: Pillow 12.3.0 printed a deprecation warning for `getdata` in a check of the
image conversions before the PNG save
**Verified:** 2026-10-22

`ImageCache._hash` in `cache.py` reads the 100 grey pixels of the reduced image with `getdata()`. Pillow 12.3.0
warns about that call:

```text
DeprecationWarning: Image.Image.getdata is deprecated and will be removed in Pillow 14 (2027-10-15). Use get_flattened_data instead.
```

The builds install the newest Pillow ([task 048](048-builds-install-the-newest-dependencies.md)). From the
warning, not checked: in a build with Pillow 14, `_hash` raises `AttributeError` for each downloaded image.
`get()` does not catch it, so the error ends the run as the save error of
[task 038](038-cmyk-image-download-ends-the-run.md) did.

## What a fix involves

`list(image.tobytes())` gives the same values as `getdata()` for a mode `L` image in every Pillow version, and
`get_flattened_data()` exists in Pillow 12.3.0. The hashes, and so the file names in `cache/`, stay the same.
No fix adds a request. It was left out of the change that found it, which fixed the save of a CMYK image.

## History

- 2026-10-21: Opened. A check of how Pillow converts mode `I` to RGB called `getdata()` and printed the warning.
- 2026-10-22: Done. `_hash` reads the grey pixels with `tobytes()`, which gave the values of `getdata()` for 400
  random images in eight modes, so the file names stay the same. `tests/test_cache.py` checks three names and
  fails on a Pillow deprecation warning. A changed hash would not have downloaded a cached image again: the
  mapping stores each URL's file name, and `get()` opens that file without hashing it.
