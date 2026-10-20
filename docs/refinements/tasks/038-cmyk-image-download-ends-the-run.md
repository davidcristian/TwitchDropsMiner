# A downloaded CMYK image ends the run

**Status:** open
**Area:** cache
**Origin:** Found on 2026-10-20 while `ImageCache.get` was changed to decode the whole download
**Verified:** 2026-10-20

`ImageCache.get` in `cache.py` saves each downloaded image in `cache/` as a PNG file with `image.save`, which
runs after the handling of a failed download. Pillow cannot write a CMYK image as PNG, and a CMYK JPEG is a
valid image, so `decode_image` returns it. The error passes up through `InventoryOverview.add_campaign` to
`Twitch.fetch_inventory`, which ends the run, and the restart begins with a full reload
([task 019](019-restart-runs-a-full-reload.md)). Nothing is cached for the URL, so every run fails the same way
while a campaign uses the image.

A real `ImageCache` under Xvfb, with a stub `request` that returned a 40 by 40 CMYK JPEG made with Pillow 12.3.0:

```
attempt 1 raised OSError: cannot write mode CMYK as PNG
attempt 2 raised OSError: cannot write mode CMYK as PNG
```

Whether Twitch serves any CMYK image was not checked. The URLs come from campaign data: `boxArtURL` for the
game and `imageAssetURL` for each reward.

## What a fix involves

Convert an image whose mode PNG cannot write to RGB before `get()` hashes and saves it, or use the white image
when `save` raises `OSError`. A test needs the decision in a module that imports no Pillow, as `imagedata.py`
does ([imagedata.md](../../modules/imagedata.md)). No fix adds a request.

## History

- 2026-10-20: Opened. While `get()` was changed to decode the whole download, the steps after the decode were
  run with a CMYK JPEG, and the save raised.
