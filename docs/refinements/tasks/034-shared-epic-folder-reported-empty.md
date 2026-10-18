# A game folder scanned after another one is reported as holding no games

**Status:** done 2026-10-18
**Area:** gamelib (scan and epic)
**Origin:** Found on 2026-10-18 by the first tests of `gamelib`, [ADR-0013](../../adr/ADR-0013-test-standard.md)
**Verified:** 2026-10-18

`scan_directories` in `gamelib/scan.py` calls `scan_steam` and `scan_epic` on each folder in `game_dirs`, and
adds `No Steam or Epic games found in: <folder>` to the errors when neither returns True. `_epic_manifest_dirs`
in `gamelib/epic.py` returns the folder's own `.item` manifests and also the Epic launcher's system folder
(`C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests` on Windows) for every folder. `scan_epic` skips a
manifests folder that an earlier folder already read, and returns True only when it reads a manifests folder
or a Legendary or Heroic index.

So on a Windows machine with Epic installed, with a Steam folder first and the Epic games folder second in
`game_dirs`, the first folder reads the system manifests and the second folder gets the error line, although
the games of both are found. The Detected Games list shows the error for the Epic folder.

A fix makes `scan_epic` return True when a manifests folder it found was already read, since the folder is
still an Epic location. The strict `xfail` test in `tests/test_gamelib_scan.py` that names this file passes once
it is fixed. Twitch requests: none.

## How it was closed

`scan_epic` returns True for every manifests folder it finds, including one an earlier folder already read,
and still reads each folder once. On a machine where the Epic launcher's manifests folder holds a game, every
added folder is now recognized as an Epic location, as a Legendary or Heroic index in the home folder already
made it. The error line `No Steam or Epic games found in: ...` then does not appear, which gamelib.md and
troubleshooting.md now say. A review ran 104,832 scans on the old and the new code: the error lines differ only
in this case, and no game is lost or listed twice. The strict `xfail` test passes without the mark, and a new
test checks that the launcher folder is read once for two added folders.

## History

- 2026-10-18: Opened. The first `gamelib` tests found it, and reading `scan_epic` and `_epic_manifest_dirs`
  confirmed the order of the two calls. Not run on Windows.
- 2026-10-18: Closed. A manifests folder that an earlier folder read still counts as an Epic location.
