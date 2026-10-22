# `cache.py`

**Purpose.** `ImageCache` downloads the game box art and the drop reward images that the Inventory tab shows,
keeps them on disk between runs, and returns them as Tk `PhotoImage` objects of the size asked for.
`GUIManager` creates the one instance, and `InventoryOverview` uses it through `manager._cache`.

## Public contract

- **`ImageCache(manager)`** takes the `GUIManager`. It uses `manager._root` as the Tk master of each `PhotoImage`
  and `manager._twitch` to download. It creates `cache/`, loads the mapping and removes expired entries
  (see [Expiry](#expiry)).
- **`await get(url, size=None) -> PhotoImage`** returns the image at `url`, resized to `size` (width, height);
  `None` keeps the image's own size. `InventoryOverview.add_campaign` asks for campaign art at `(108, 144)` and
  reward images at `(80, 80)`.
- **`retry_failed()`** makes the next `get()` of each URL whose download failed download it again.
  `InventoryOverview.clear` calls it, and `Twitch.fetch_inventory` calls that once per reload
  ([Failed downloads](#failed-downloads)).
- **`save(*, force=False)`** writes the mapping when anything changed since it was loaded, or when `force` is
  true. `GUIManager.save` calls it. `Twitch._run` calls that through `save_each` after each `INVENTORY_FETCH`,
  which logs an `OSError` and goes on ([savefiles.md](savefiles.md)), and `main.py` calls
  `Twitch.save(force=True)` at exit.
- **`LIFETIME`** is 7 days.

## Storage

The images are PNG files in `cache/` in the working directory (`CACHE_PATH`). The mapping is
`cache/mapping.json` (`CACHE_DB`), written by `json_save` with sorted keys:

```
{
    "<image URL>": {
        "expires": {"__type": "datetime", "data": <UTC timestamp in seconds>},
        "hash": "<hexadecimal hash>.png"
    }
}
```

The file name is a hash of how the image looks: the image is reduced to 10 by 10 grey pixels, each pixel gives
one bit (1 when it is at least the average), and the bits are written in hexadecimal with `.png` appended. Images
that look the same share one file, even when they come from different URLs. Two different images whose
reduced forms give the same bits also share one file, so the Inventory tab shows one of them for both.

In memory, the cache keeps each decoded image by hash and each `PhotoImage` by hash and size, until the app
exits.

## Expiry

Each `get()` for a URL sets its `expires` to now plus `LIFETIME`. The dates are checked only when `ImageCache` is
created at startup: entries past their date are removed, and a file that a removed entry names and no remaining
entry names is deleted. A file that no entry names stays, unless `mapping.json` is broken
([Broken data](#broken-data)). An image that the Inventory tab shows at least once a week stays on disk.

## Broken data

| Case | Result |
| --- | --- |
| `mapping.json` is not valid JSON | The cache starts with an empty mapping and deletes every `*.png` in `cache/` |
| `mapping.json.new` is not valid JSON | `json_load` deletes it and reads `mapping.json` ([utils.md](utils.md#json-files)) |
| An image file is missing or fails to decode | `get()` downloads the image again. It calls `load()` to decode the whole file, so a file damaged anywhere fails at this point |
| The response is a 404, the body of another response is not an image (such as a 403 page), or `Twitch.request` raises an error that it does not retry (such as `aiohttp.InvalidURL`). It retries connection errors other than a certificate error, timeouts and statuses of 500 and above until a try succeeds, so these never reach `get()` | `get()` logs a warning with the URL and the status, or the error's class and text, and returns a white image of the size asked for, 10 by 10 for `None`. It saves no file and does not map the URL ([Failed downloads](#failed-downloads)) |
| `Twitch.request` raises `ExitRequest`, because the window closed during the download, or `ReloadRequest` | The error passes up to the caller. `get()` maps nothing |
| The body is an image cut off after its header | `decode_image` decodes the whole body and returns None ([imagedata.md](imagedata.md)), and `get()` uses the white image as for a body that is not an image |
| The image has a mode that PNG cannot store, such as CMYK in a JPEG | `get()` converts it to RGB, or RGBA when it has transparency, before it hashes and saves it ([imagedata.md](imagedata.md)) |
| The resize raises `OSError` | `get()` returns a white image of the size asked for |
| Saving the image file raises `OSError`, such as on a full disk | `get()` logs `error.file_not_saved` with the file name through `save_each` ([savefiles.md](savefiles.md)), maps the URL and returns the image. Pillow can leave an empty or cut file |

An image whose file was not saved stays in memory, so later `get()` calls in the run send no request. The
mapping still names the file, so the next run cannot load it and downloads the image once. Leaving the URL out
of the mapping would download the image again at every reload while the disk stays full.

## Failed downloads

`get()` keeps each URL whose download failed in memory until `retry_failed()`. Until then, a `get()` of that URL
returns the white image and sends no request. `InventoryOverview.add_campaign` asks for one image several times
in a reload, such as the box art of a game with two campaigns, so a failed image is downloaded at most once per
reload. The next reload, which comes at least once an hour, downloads it again, and so does the next start,
because the URL is not in `mapping.json`. A 404 for an image that Twitch removed is also tried again: it saves no
file and changes nothing in `mapping.json`, and it costs one request per URL per reload.

A `cache/` folder can map a URL to the white image of an earlier failed download: the file
`fffffffffffffffffffffffff.png` of 10 by 10 pixels. `get()` does not use that file and downloads the URL again,
and a whole image replaces the mapping. Every image of one color gets this file name ([Storage](#storage)), but
a downloaded image keeps its own size, so `get()` uses such an image from its file.

## Invariants

- `get()` holds one `asyncio.Lock` while it looks up and downloads, so the cache downloads one image at a time and
  two calls for one URL download it once.
- Downloads go through `Twitch.request`, which retries a status of 500 or above and connection errors with no
  limit on the count, while `get()` holds the lock ([utils.md](utils.md#request-pacing)). They are plain HTTP
  requests to the image host, not GQL, so the GQL `RateLimiter` does not count them.
- Every `get()` marks the cache as changed, so the next `save()` writes the mapping.
- `get()` sends at most one request per URL between two `retry_failed()` calls, also when the download fails.

**Dependencies.** `utils` (`json_load`, `json_save`), `imagedata` (`decode_image`, `png_mode`), `savefiles`
(`save_each`), `translate` (`_`), `exceptions` (`ExitRequest`, `ReloadRequest`), `constants` (`URLType`,
`CACHE_PATH`, `CACHE_DB`) and Pillow.
`gui.GUIManager` is imported for type checking only.
