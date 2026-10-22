# The Settings tab repeats three setting defaults

**Status:** done 2026-10-23
**Area:** settings, gui
**Origin:** Found on 2026-10-18 while the docs were written, [settings.md](../../modules/settings.md)
**Verified:** 2026-10-23

`default_settings` in `settings.py` holds the default of each setting. `SettingsPanel.__init__` in `gui.py`
writes three of them again, as the value it sets when the stored one is not in its drop-down list:

| Setting | `default_settings` | Fallback in `SettingsPanel.__init__` | Choice list in `SettingsPanel` |
| --- | --- | --- | --- |
| `refresh_interval` | `5` | `5` | `REFRESH_INTERVALS`: 0, 1, 2, 5, 10, 15, 30 |
| `restart_delay` | `10` | `10` | `RESTART_DELAYS`: 0, 1, 5, 10, 15, 30, 60 |
| `priority_mode` | `PriorityMode.PRIORITY_ONLY` | the same | `PRIORITY_MODES`: all three `PriorityMode` members |

The fallback is then used as a key of the choice list, to set the text of the drop-down list. So each value
must match in three places: the default, the fallback, and the list. The `if __name__ == "__main__":` mock at
the end of `gui.py` repeats every default a fourth time (`refresh_interval=5`, `restart_delay=10`,
`priority_mode=PriorityMode.PRIORITY_ONLY` and the rest), as the AGENTS.md recipe for a new setting asks. It is
used only by `python gui.py`.

A search for each setting name in the `.py` files found two other corrections, and neither repeats a default.
`Twitch.get_session` limits `connection_quality` to 1 through 6, a range check. `proxy_validate` in `gui.py`
sets an entry whose URL has no host or no port to `URL()`, which means no proxy.

## How it was confirmed

`python gui.py` was run under Xvfb from two copies of the repo in a temporary folder, each with one change.

- In the first copy, the mock had `refresh_interval=3` and `restart_delay=7`, two values outside the lists,
  and a print followed the fallback. It printed `refresh_interval = 5 restart_delay = 10`.
- In the second copy, `REFRESH_INTERVALS` was built without 5, from `(1, 2, 10, 15, 30)`, and the mock kept
  `refresh_interval=5`. `SettingsPanel.__init__` raised `KeyError: 5` at
  `self.REFRESH_INTERVALS[refresh_interval]`, and the preview ended with that exception.

## Effect

Today the copies match, and a user sees nothing wrong. The problem is in the next change to one copy:

- **A new default in `settings.py` only.** A new user gets it. A stored value outside the list still falls
  back to the old 5 or 10. A new default that is not in the list is replaced by 5 or 10 at the first start,
  and `Settings` saves that, so the new default never takes effect.
- **A list without the fallback value.** Every user whose stored value is not in the new list gets the
  fallback, which is not a key either, and `SettingsPanel.__init__` raises `KeyError`. That includes every user
  who kept the old default. In the app, `main()` builds the GUI in `Twitch(settings)`, outside its `try`, so
  the process ends with a traceback on standard error and no dialog. `python gui.py` fails the same way,
  because the mock uses the same value, so the GUI check in AGENTS.md finds this case. It finds it only
  because the mock repeats the fallback.
- **A new `PriorityMode` member without an entry in `PRIORITY_MODES`.** The panel replaces a stored value of
  that member with `PRIORITY_ONLY` when the window is built, before `Twitch._run` reads the setting. This case
  is the least likely, because the panel is the only place where a user picks a mode.

## How it came about

From `git log -S` on `gui.py`. Upstream added the pattern for `priority_mode` in "Add a prioritization strategy
for games outside of the priority list" (2024-09-11). This project copied it for `refresh_interval` in
"Implement auto fetch" (2026-08-03) and for `restart_delay` in "Restart automatically after a fatal error"
(2026-08-25). [settings.md](../../modules/settings.md) states the resulting rule as an invariant: a default
changed in `default_settings` is changed in `SettingsPanel.__init__` too.

## What a fix involves

- Read the fallback from `default_settings` in `SettingsPanel.__init__`. `gui.py` imports `settings` only for
  type checking today. A runtime import adds no import cycle, because `settings.py` imports only `utils` and
  `constants`.
- Keep each list of choices next to its default in `settings.py`, and check that the default is in its list.
  The check fits the test suite of [003](003-test-suite.md), or an `assert` at import time.
- Optionally build the mock's values from `default_settings`, so the preview shows the real defaults.

The `gui.py` edit follows the AGENTS.md recipe for repeated lines. The docs that change with it are
[settings.md](../../modules/settings.md) (the invariant above) and the "A new setting" recipe in
[AGENTS.md](../../../AGENTS.md#recipes), if the mock changes.

Cost: no Twitch requests.

## History

- 2026-10-18: Opened. Found while the docs were written. Two runs of `python gui.py` from changed copies of
  the repo showed the fallback to 5 and 10 and the `KeyError` when the list lacks the fallback.
- 2026-10-23: Done. The claim held: `SettingsPanel.__init__` still set the fallbacks 5, 10 and
  `PriorityMode.PRIORITY_ONLY`. `settings.py` now has `setting_choices`, the values of each drop-down list, and
  the panel builds its lists from it and reads each fallback from `default_settings`. `tests/test_settings.py`
  checks that each default is in its list, and `tests/test_gui_settings.py` checks the panel with a changed
  default and changed lists. The preview mock still repeats the defaults, as the new setting recipe asks.
