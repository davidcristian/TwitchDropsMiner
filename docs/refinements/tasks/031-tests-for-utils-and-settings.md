# The logic in utils and settings has no tests

**Status:** open
**Area:** utils, settings, tests
**Origin:** [ADR-0013](../../adr/ADR-0013-test-standard.md), and the candidates of
[task 003](003-test-suite.md)
**Verified:** 2026-10-21

The test suite covers `redact`, `reconnect`, `gamelib`, `gqldata`, `imagedata`, `savefiles`, `ratelimit`,
`instancelock` and `scripts/`. Two candidates of task 003 are left: the helpers in `utils.py` and the loading of
`settings.json`.

- **`utils`**: `chunk`, `deduplicate`, `ExponentialBackoff` and `Game.slug`.
- **Settings loading**: `json_load`, `json_save` and `merge_json` in `utils`, with `default_settings` from
  `settings`. `Settings.__init__` reads the fixed `SETTINGS_PATH`, so a test calls
  `json_load(path, default_settings)` with a temporary path. For example, a saved file with
  `"refresh_interval": "five"` and an unknown key loads back with `refresh_interval` set to 5, the unknown key
  removed, `exclude` as a `set` and `proxy` as a `URL`.

## Cost

`utils.py` imports `tkinter`, `PIL.ImageTk` and `yarl` when it loads, and `settings.py` imports `utils`. The
Validate job in CI installs Pillow and `yarl` with `requirements-dev.txt`, and its Python has `tkinter`, so a
test can import both modules as they are.

Neither module is in the coverage list in `pyproject.toml`, which holds the modules that need neither Twitch
nor a display. Splitting `utils.py` ([task 005](005-modules-over-the-line-cap.md)) would put the JSON helpers,
`ExponentialBackoff` and the task helpers, which need neither `tkinter` nor Pillow, in modules that the list can
include.

Twitch requests: none.

## History

- 2026-10-18: Opened. Task 003 closed with the suite for `redact`, `gamelib` and `scripts/`, and these two
  candidates were left because their imports need `requirements.txt`.
- 2026-10-20: `RateLimiter` moved from `utils.py` to the new module `ratelimit.py`, which
  `tests/test_ratelimit.py` tests, so it left the `utils` candidate.
- 2026-10-20: `lock_file` moved from `utils.py` to the new module `instancelock.py`, which
  `tests/test_instancelock.py` tests.
- 2026-10-21: The check that removes the items that are not strings from the list and set settings after the
  load is in the new module `settingsdata.py`, which `tests/test_settingsdata.py` tests. `json_load`,
  `json_save` and `merge_json` still have no tests.
- 2026-10-21: The Validate job installs the app's packages except PyGObject and pywin32, and
  `tests/test_imports.py` imports `utils` and `settings`. Their logic still has no tests.
- 2026-10-21: `tests/test_utils.py` tests `start_task`, which a fix added to `utils.py`. The candidates above
  still have no tests.
- 2026-10-23: `utils.py` imports without a display or Twitch, so it joined the coverage list, and
  `tests/test_utils*.py` test each of its public functions. A test of `format_traceback` showed that it raised
  `ValueError` for every exception, which a fix with that test repaired.
