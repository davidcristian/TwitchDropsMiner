# A game folder that names an unknown user ends the scan of every folder

**Status:** open
**Area:** gamelib (scan)
**Origin:** Found on 2026-10-18 by the first tests of `gamelib`, [ADR-0013](../../adr/ADR-0013-test-standard.md)
**Verified:** 2026-10-18

`scan_directories` in `gamelib/scan.py` calls `Path(raw_directory).expanduser()` before its `try` block. On Linux
and macOS, a path such as `~nosuchuser/Games` makes `expanduser` raise `RuntimeError`, which leaves the loop, so
no folder is scanned. `Twitch.detect_games` logs `Game folder scan failed`. On Windows, `expanduser` forms a
home folder for any user name and raises nothing.

The GUI adds folders with a folder picker, which returns an absolute path, so only a hand-edited
`settings.json` can hold such a path. A fix moves `expanduser` inside the `try` and catches `RuntimeError` there,
so the folder gets an error line and the others are scanned. The strict `xfail` test in
`tests/test_gamelib_scan.py` that names this file passes once it is fixed. Twitch requests: none.

## History

- 2026-10-18: Opened. The first `gamelib` tests found it.
