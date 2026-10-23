# `savefiles.py`

**Purpose.** `save_each` runs the saves that `Twitch._run` makes after each inventory fetch
(`State.INVENTORY_FETCH`): the image cache's `cache/mapping.json` through `GUIManager.save`, then
`settings.json` through `Settings.save`. A save raises `OSError` when the disk is full, or on Windows when another
program has the file open. Without `save_each` that error ends the run, and while the cause stays, each restart
runs a full reload and fails again. `replace_file` writes `cookies.jar` through a second file.
`UnsavedChanges` keeps the record of whether `settings.json` has a change that is not written yet. The module
imports no other module of the app, so a test runs it with fakes.

## Public contract

- `save_each(saves, report)` calls each function in `saves` in order. When one raises `OSError`, it passes the
  error to `report` and goes on with the next one, so a failed cache save does not skip the settings save.
- An error that is not an `OSError` passes up to the caller, and the later saves do not run. `json_save` raises
  `TypeError` for a value that JSON cannot hold, which is a bug in the app and still ends the run.
- `replace_file(path, write)` calls `write` with `<name>.new` in the folder of `path`, then replaces `path` with
  that file by `os.replace`. When `write` or the rename raises, the error passes up, `path` keeps its old
  contents and `<name>.new` is deleted. Only a whole file replaces `path`, with one rename, so a kill of the
  process leaves the old file or the new one, and at most a `<name>.new` that the next save writes over.
- `UnsavedChanges(write)` starts with no change pending. `mark()` records a change. `save(force=False)` calls
  `write` when a change is pending or `force` is true, and then clears the pending change. When `write` raises,
  the error passes up and the change stays pending. `Settings` creates one, whose `write` calls `json_save`, and
  calls `mark()` on each assignment and each `alter()` ([settings.md](settings.md)).

`Twitch._run` passes a `report` that logs the string `error.save_failed` from `translate/` at `ERROR` level,
with the error's text. That level shows in the Output box with no `-v` flag, and in `log.txt` with `--log`, so
the line is translated, and the app prints no second line for it. A file that fails keeps its changes in
memory, and the next inventory fetch writes it again: `Settings.save` clears its pending change only after a
write that succeeds, and `ImageCache.save` never clears its changed flag. What a failed save leaves on disk is
in [utils.md](utils.md#json-files).

## Saves during the run outside the inventory fetch

`save_cookies` in `twitch.py` saves the aiohttp cookie jar at the end of each login and in `Twitch.shutdown`. It
passes `CookieJar.save` to `replace_file`, because `CookieJar.save` truncates the file and writes it in place:
with aiohttp 3.14.3 on a full disk, a save that needs new space left a cut `cookies.jar` that failed to load, so
the next run asked for a new login. `save_each` runs it with a `report` that logs the string
`error.file_not_saved` at `ERROR` level, with the file name and the error's text, because `error.save_failed`
says that the next reload saves again, which is not true for this file. The run keeps the login in memory,
`Twitch.shutdown` saves the jar again, and until a save succeeds the old `cookies.jar` stays whole. The second
file needs free space even when the new contents would fit in the space of the old file. `CookieJar.save` takes
a path in aiohttp 3.13.4, which pickles the jar, and in 3.14.3, which writes JSON.

`ImageCache.get` in `cache.py` saves each new image through `save_each` and logs `error.file_not_saved` the same
way ([cache.md](cache.md#broken-data)).

`main.py` does not use `save_each`: an `OSError` from its `client.save(force=True)` after the window closes
passes up out of `main()` ([main.md](main.md)).

**Dependencies.** None: the standard library only.
