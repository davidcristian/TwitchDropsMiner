# On a full disk, the cookie and image writes still end the run

**Status:** open
**Area:** twitch, cache
**Origin:** Found on 2026-10-20 while a failed save after an inventory fetch was changed to be logged
([savefiles.md](../../modules/savefiles.md))
**Verified:** 2026-10-20

`save_each` keeps the run going when the save of `settings.json` or `cache/mapping.json` raises `OSError`. Three
other writes during a run have no such handling, and on a full disk each raises `OSError`:

- `_AuthState._validate` in `twitch.py` saves `cookies.jar` with `CookieJar.save` at the login of each run. The
  error ends the run, and the restart logs in and fails the same way while the disk stays full.
- `Twitch.shutdown` saves `cookies.jar` the same way. `run()` calls it on `ReloadRequest` inside its `except`
  branch, and `_await_restart` calls it before the restart wait, so the error ends the app with no restart.
- `ImageCache.get` in `cache.py` saves each new image as a PNG file with `image.save`. The error ends the run
  through `Twitch.fetch_inventory` ([task 038](038-cmyk-image-download-ends-the-run.md) has the same line
  for a CMYK image).

`CookieJar.save` in aiohttp 3.14.3 writes `cookies.jar` in place, not through a second file. A write that needs
new disk space fails and leaves an empty file, which `Twitch.get_session` cannot load, so it clears the jar and
the next run asks for a new login. A rewrite that fits in the file's current disk space succeeds.

Checked on an 8 KiB tmpfs filled with a file, with aiohttp 3.14.3 and Pillow 12.3.0:

```
cookie save raised OSError No space left on device | cookies.jar now 0 bytes
image save raised OSError No space left on device
```

## What a fix involves

Catch `OSError` around each write and log it, as `save_each` does ([savefiles.md](../../modules/savefiles.md)),
and for `cookies.jar` write a second file and rename it, as `json_save` does, so a failed write keeps the old
login. A test needs the decision in a module that imports neither aiohttp nor Pillow. No fix adds a request.

## History

- 2026-10-20: Opened. While the save after an inventory fetch was changed to log an `OSError`, the app's other
  writes were run on a full disk.
