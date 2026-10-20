# `savefiles.py`

**Purpose.** `save_each` runs the saves that `Twitch._run` makes after each inventory fetch
(`State.INVENTORY_FETCH`): the image cache's `cache/mapping.json` through `GUIManager.save`, then
`settings.json` through `Settings.save`. A save raises `OSError` when the disk is full, or on Windows when another
program has the file open. Without `save_each` that error ends the run, and while the cause stays, each restart
runs a full reload and fails again. `UnsavedChanges` keeps the record of whether `settings.json` has a change
that is not written yet. The module imports no other module of the app, so a test runs it with fakes.

## Public contract

- `save_each(saves, report)` calls each function in `saves` in order. When one raises `OSError`, it passes the
  error to `report` and goes on with the next one, so a failed cache save does not skip the settings save.
- An error that is not an `OSError` passes up to the caller, and the later saves do not run. `json_save` raises
  `TypeError` for a value that JSON cannot hold, which is a bug in the app and still ends the run.
- `UnsavedChanges(write)` starts with no change pending. `mark()` records a change. `save(force=False)` calls
  `write` when a change is pending or `force` is true, and then clears the pending change. When `write` raises,
  the error passes up and the change stays pending. `Settings` creates one, whose `write` calls `json_save`, and
  calls `mark()` on each assignment and each `alter()` ([settings.md](settings.md)).

`Twitch._run` passes a `report` that logs the string `error.save_failed` from `translate.py` at `ERROR` level,
with the error's text. That level shows in the Output box with no `-v` flag, and in `log.txt` with `--log`, so
the line is translated, and the app prints no second line for it. A file that fails keeps its changes in
memory, and the next inventory fetch writes it again: `Settings.save` clears its pending change only after a
write that succeeds, and `ImageCache.save` never clears its changed flag. What a failed save leaves on disk is
in [utils.md](utils.md#json-files).

`main.py` does not use `save_each`: an `OSError` from its `client.save(force=True)` after the window closes
passes up out of `main()` ([main.md](main.md)).

**Dependencies.** None: the standard library only.
