# `settingsdata.py`

**Purpose.** Checks the values that `json_load` returns for `settings.json` ([settings.md](settings.md)), before
the app uses them. `json_load` replaces a value whose type differs from its default, but it does not check the
items of a list or a set, so a hand edit can leave a number in the Priority or Exclude list. `SettingsPanel`
sorts the Exclude list while the window is built, and `compile_patterns` reads the Priority list, and both raise
`TypeError` on a number. The module imports no other module of the app, so a test runs it with plain dicts.

## Public contract

- `drop_non_text_items(settings)` removes each item that is not a `str` from every `list` and `set` value of
  `settings`, and returns a `(key, item)` pair for each item removed, in the order of the keys and of the items
  in a list. A number, `None`, a bool and a nested list are all removed.
- A value that loses items is replaced in `settings` by a new value of the same type, which keeps the order of
  a list's strings. The old list or set is not changed, because a value that the file lacks is the same object
  as the one in `default_settings`. A value that loses no items stays the same object.
- Values that are not a `list` or a `set` are left as they are.

`Settings.__init__` calls it on the merged settings and logs a warning on the `TwitchDrops` logger for each pair
it returns. Every list and set setting holds strings: `priority`, `exclude`, `game_dirs` and `detected_games`.

**Dependencies.** None: the standard library only.
