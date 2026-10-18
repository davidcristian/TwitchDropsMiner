# A game folder that names an unknown user ends the scan of every folder

**Status:** done 2026-10-18
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

## How it was closed

`scan_directories` calls `expanduser` in its own `try` and catches `RuntimeError`, so a folder such as
`~nosuchuser/Games` gets the error line `~nosuchuser/Games: <reason>` and the other folders are scanned. Other
errors keep their line with the expanded path. The strict `xfail` test passes without the mark, and a new test
checks that the line names the folder as it was written.

## History

- 2026-10-18: Opened. The first `gamelib` tests found it.
- 2026-10-18: Closed. An unknown user name gives an error line for its folder.
