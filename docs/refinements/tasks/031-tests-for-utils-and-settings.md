# The logic in utils and settings has no tests

**Status:** open
**Area:** utils, settings, tests
**Origin:** [ADR-0013](../../adr/ADR-0013-test-standard.md), and the candidates of
[task 003](003-test-suite.md)
**Verified:** 2026-10-20

The test suite covers `redact`, `reconnect`, `gamelib`, `gqldata`, `imagedata`, `savefiles`, `ratelimit` and
`scripts/`. Two candidates of task 003 are left: the helpers in `utils.py` and the loading of `settings.json`.

- **`utils`**: `chunk`, `deduplicate`, `ExponentialBackoff` and `Game.slug`.
- **Settings loading**: `json_load`, `json_save` and `merge_json` in `utils`, with `default_settings` from
  `settings`. `Settings.__init__` reads the fixed `SETTINGS_PATH`, so a test calls
  `json_load(path, default_settings)` with a temporary path. For example, a saved file with
  `"refresh_interval": "five"` and an unknown key loads back with `refresh_interval` set to 5, the unknown key
  removed, `exclude` as a `set` and `proxy` as a `URL`.

## Cost

`utils.py` imports `tkinter`, `PIL.ImageTk` and `yarl` when it loads, and `settings.py` imports `utils`. The
Validate job in CI installs only `requirements-dev.txt`, which has none of them except `yarl`. Two ways to test
them:

- **Install `requirements.txt` in the Validate job.** On Ubuntu that needs the system packages that
  [building.md](../../building.md#requirements) lists, because pip builds PyGObject from source, and a Python
  with `tkinter`. The tests then need no change to the code.
- **Split `utils.py` first** ([task 005](005-modules-over-the-line-cap.md)). The JSON helpers,
  `ExponentialBackoff` and the task helpers need neither `tkinter` nor Pillow, so as modules of their own they
  can be tested with the standard library and `yarl` alone, and added to the coverage list in `pyproject.toml`.

Twitch requests: none.

## History

- 2026-10-18: Opened. Task 003 closed with the suite for `redact`, `gamelib` and `scripts/`, and these two
  candidates were left because their imports need `requirements.txt`.
- 2026-10-20: `RateLimiter` moved from `utils.py` to the new module `ratelimit.py`, which
  `tests/test_ratelimit.py` tests, so it left the `utils` candidate.
