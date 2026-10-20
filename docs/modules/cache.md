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
| The response is a 404, the body of another response is not an image (such as a 403 page), or `Twitch.request` raises an error that it does not retry (such as `ExitRequest` when the window closes during the download). It retries connection errors other than a certificate error, timeouts and statuses of 500 and above until a try succeeds, so these never reach `get()` | `get()` logs a warning with the URL and the status, or the error's class and text, uses a 10 by 10 white image, saves it and maps the URL to it like a real image |
| The body is an image cut off after its header | `decode_image` decodes the whole body and returns None ([imagedata.md](imagedata.md)), and `get()` uses the white image as for a body that is not an image |
| The resize raises `OSError` | `get()` returns a white image of the size asked for |

A white image saved for a failed download stays in place while the URL is still requested: each `get()` finds
the mapped file and renews its date. The image is downloaded again only after the URL goes 7 days without a
request and its entry expires ([task 017](../refinements/tasks/017-failed-image-downloads-cached.md)).

## Invariants

- `get()` holds one `asyncio.Lock` while it looks up and downloads, so the cache downloads one image at a time and
  two calls for one URL download it once.
- Downloads go through `Twitch.request`, which retries a status of 500 or above and connection errors with no
  limit on the count, while `get()` holds the lock ([utils.md](utils.md#request-pacing)). They are plain HTTP
  requests to the image host, not GQL, so the GQL `RateLimiter` does not count them.
- Every `get()` marks the cache as changed, so the next `save()` writes the mapping.

**Dependencies.** `utils` (`json_load`, `json_save`), `imagedata` (`decode_image`), `constants` (`URLType`,
`CACHE_PATH`, `CACHE_DB`) and Pillow. `gui.GUIManager` is imported for type checking only.
