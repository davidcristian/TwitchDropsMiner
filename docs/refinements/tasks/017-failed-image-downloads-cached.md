# A failed image download stays blank while the image is in use

**Status:** done 2026-10-22
**Area:** cache
**Origin:** Found on 2026-10-18 while the docs were written, [cache.md](../../modules/cache.md#broken-data)
**Verified:** 2026-10-22

`ImageCache.get(url, size)` in `cache.py` downloads an image it does not have through `Twitch.request`. In three
cases it logs a warning and uses a 10 by 10 white image instead: the status is 404, `decode_image` cannot decode
the whole body, or the request raises an exception (`except Exception`). It then stores the white image like a
real one: `_hash` names it, it is saved in `cache/`, and `_hashes[url]` maps the URL to it with `expires` set to
now plus `LIFETIME` (7 days). Each later `get()` for that URL finds the mapping, sets `expires` to 7 days from
then, loads the white file and sends no request. `ImageCache.__init__` removes an entry only after its date has
passed. So the white image stays until the URL goes 7 days without a `get()`.

## Which failures reach the fallback

`Twitch.request` retries connection errors, timeouts, `ClientPayloadError` and statuses of 500 and above, with
a backoff of up to 3 minutes between tries, and returns only after a try succeeds. So a short network outage
does not produce a white image: the download waits and then succeeds. These cases do produce one:

- a 404, for an image that Twitch removed;
- another status below 500, such as 403 or 429, whose body is not an image;
- a 200 whose body is not an image, such as the login page of a hotel network, or is an image cut off after
  its header;
- an exception that `Twitch.request` passes up: `ClientConnectorCertificateError` (it re-raises that one),
  `aiohttp.InvalidURL`, `ClientHttpProxyError` from a proxy, or `ExitRequest`. `ExitRequest` is raised when the
  window is closed during the download, and it is a subclass of `Exception`, so `get()` catches it and maps the
  URL to the white image. `main.py` then writes `mapping.json` with `client.save(force=True)` at exit. `get()`
  holds one lock while it downloads, so this stores at most the one download in progress when the window
  closes.

## How it was confirmed

`ImageCache` was created with a Tk root under Xvfb and a stub `request` that returned a failure for the first
call for each URL and a valid 40 by 40 PNG for the second. Each URL was then read twice with `get()`:

| First response | File the URL maps to | Requests sent | Same image both times | `expires` renewed |
| --- | --- | --- | --- | --- |
| 403 with an HTML body | `fffffffffffffffffffffffff.png` | 1 | yes | yes |
| 404 | the same | 1 | yes | yes |
| 200 with an HTML body | the same | 1 | yes | yes |
| `RuntimeError` | the same | 1 | yes | yes |
| `ExitRequest` | the same | 1 | yes | yes |

After `save(force=True)` and a new `ImageCache` (a restart), `get()` for the 404 URL sent no request. A second
check called `Twitch.request` with a stub session that raised `aiohttp.ClientConnectionError` twice. It printed
`Cannot connect to Twitch, retrying in 2 seconds...` and returned the 200 of the third try.

## What the user sees

The Inventory tab shows a white square in place of a campaign's box art or a reward image. Nothing else uses
the cache. `InventoryOverview.add_campaign` calls `get()` for each campaign at each reload, and a reload runs at
least once an hour, so the image stays white while the campaign is in the inventory and for 7 days after.
Mining is not affected.

## What a fix involves

- Do not store a mapping for the white image: return it for that call only, so the next reload tries again. A
  404 can keep its white image with a short date, so an image that Twitch removed is not requested at every
  reload.
- Let `ExitRequest` and `ReloadRequest` pass through `get()` instead of catching them.
- `_hash` is an average hash of a 10 by 10 grey copy, so every image of one plain color gets the name
  `fffffffffffffffffffffffff.png`. A fix that finds the white image by that name also matches such an image.

Cost: the downloads go to Twitch's image servers. They are not GQL, so the GQL `RateLimiter` does not count
them ([ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md)). A retry costs at most one image request per
failed URL per reload, so one per hour with the hourly reload.

How it came about: the white image, the 404 test and `except Exception` were added on 2025-08-22 in the original
project, in the commit "Fix GUI debug code". The commit message gives no reason. The same commit changed the
preview code at the end of `gui.py`, which downloads sample images with `aiohttp.request`, without the retries
of `Twitch.request`.

## History

- 2026-10-18: Opened while the docs were written. `ImageCache.get` and `Twitch.request` were called with stubbed
  network responses. The claim that a passing network error leaves a blank image did not hold: `Twitch.request`
  retries those errors. The task names the failures that do reach the fallback.
- 2026-10-20: `get()` decodes the whole body with `decode_image` and logs a warning for each fallback, so an
  image cut off after its header also gets the white image. The task's problem is unchanged.
- 2026-10-22: Done. The claim still held: `tests/test_cache.py` gave a 404, a 403 page, a 200 page and
  `aiohttp.InvalidURL`, and after a restart each URL showed the white image with no request. `ExitRequest` and
  `ReloadRequest` did not pass up. `get()` now keeps a failed URL in memory only, until
  `InventoryOverview.clear` calls `ImageCache.retry_failed` at the next reload, and lets the two requests pass
  up. A 404 is tried again at each reload too, and a URL mapped to the white file of 10 by 10 pixels is
  downloaded again ([cache.md](../../modules/cache.md#failed-downloads)). A failed image costs at most one
  request per reload, and no GQL request.
