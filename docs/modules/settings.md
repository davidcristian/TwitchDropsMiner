# `settings.py`

**Purpose.** The app's settings: the keys of `settings.json` with their types and defaults, and the `Settings`
object that the rest of the app reads them from. `Settings` also exposes the command line flags, so callers
read flags and settings from one object. Loading and saving go through `json_load` and `json_save` in
`utils.py`. To add a setting, follow the recipe in [AGENTS.md](../../AGENTS.md#recipes): a setting missing from
the `gui.py` preview mock fails only when `python gui.py` runs.

## Public contract

- `SettingsFile` is the `TypedDict` of the keys in `settings.json`. `default_settings` is a `SettingsFile` with
  the default of each key.
- `setting_choices` holds, for each setting with a drop-down list on the Settings tab (`priority_mode`,
  `refresh_interval` and `restart_delay`), the values that the list offers, in their order there.
- `Settings(args)` loads `settings.json` (`SETTINGS_PATH`) and keeps `args`, the `ParsedArgs` from
  [main.py](main.md). `main.py` creates the only instance and passes it to `Twitch`, which stores it as
  `Twitch.settings`.
- Reading an attribute checks `args` first and the file second. `log`, `tray`, `dump`, `logging_level`,
  `debug_ws` and `debug_gql` come from the command line; every key of `SettingsFile` comes from the file.
- Assigning an attribute writes a key of `SettingsFile` and marks the settings as changed. Assigning any other
  name raises `TypeError`, so a flag cannot be changed at run time. Deleting an attribute raises `RuntimeError`.
- `alter()` marks the settings as changed. A caller calls it after it changes a list or a set in place, such as
  `settings.priority.append(name)`, because that does not go through assignment. `SettingsPanel` does this for
  each change to the Priority, Exclude and game folder lists.
- `save(force=False)` writes the file when the settings changed since the last successful save, or when `force`
  is true. `UnsavedChanges` in [savefiles.md](savefiles.md) keeps that record: a save that raises, such as on a
  full disk, leaves the changes marked, so the next save writes them.

## The keys

The GUI labels are the English strings in the Settings tab ([gui.md](gui.md)). A key without a label has no
widget and is changed only by the app or by editing the file.

| Key | Type | Default | GUI label | What reads it |
| --- | --- | --- | --- | --- |
| `language` | `str` | `DEFAULT_LANG` (`"English"`) | "Language 🌐 (requires restart): " | `main()` calls `_.set_language` with it once at start ([translate.md](translate.md)) |
| `proxy` | `yarl.URL` | `URL()` (no proxy) | "Proxy (requires restart):" | `Twitch.request` on every HTTP request, and each `Websocket` once, when its `_handle` task starts |
| `dark_mode` | `bool` | `False` | "Dark mode: " | `GUIManager.apply_theme`, at once |
| `priority` | `list[str]` | `[]` | "Priority" list | `Twitch._run` in `State.GAMES_UPDATE`, in list order, and the inventory filter ([ADR-0005](../adr/ADR-0005-list-patterns.md)) |
| `exclude` | `set[str]` | `set()` | "Exclude" list | `Twitch._run` in `State.GAMES_UPDATE`, and the inventory filter |
| `priority_mode` | `PriorityMode` | `PriorityMode.PRIORITY_ONLY` | "Priority mode: " | `Twitch._run` in `State.GAMES_UPDATE`, and the inventory filter |
| `refresh_interval` | `int` (minutes) | `5` | "Check for new streams every: " | `Twitch._maintenance_task` ([ADR-0003](../adr/ADR-0003-stream-refresh.md)) |
| `restart_delay` | `int` (minutes) | `10` | "Restart after a crash after: " | `Twitch._await_restart`, as the wait after the first fatal error. A later wait doubles while each run ends within an hour, up to 60 minutes ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)) |
| `autostart_tray` | `bool` | `False` | "Autostart into tray: " | `SettingsPanel.__init__`, for the checkbox. `update_autostart` stores the checkbox in it and adds `--tray` to the autostart command while the checkbox is on |
| `tray_notifications` | `bool` | `True` | "Tray notifications: " | `TrayIcon.notify` |
| `enable_badges_emotes` | `bool` | `False` | "Enable partial support for badges and emotes: " | `DropsCampaign.eligible` |
| `available_drops_check` | `bool` | `False` | "Enable extra available drops check: " | `Stream.__init__` and `Twitch.bulk_check_online` |
| `game_dirs` | `list[str]` | `[]` | "Game folders:" | `Twitch.detect_games` ([ADR-0004](../adr/ADR-0004-installed-game-detection.md)) |
| `detected_games` | `list[str]` | `[]` | "Detected Games" list, filled by the app | `Twitch._run` in `State.GAMES_UPDATE`, the Settings tab, and the inventory filter |
| `connection_quality` | `int` | `1` | none | `Twitch.get_session`, which multiplies the HTTP timeouts by it |

- In another language, the "Language" label starts with the English word, as in `Language / Język`, so a user
  who picked a language they cannot read still finds the setting ([translate.md](translate.md#invariants)).
- "Autostart into tray" and "Tray notifications" are not shown on macOS. The "Autostart" checkbox next to them is
  not a setting: `SettingsPanel` reads and writes the operating system's autostart entry instead.
- The "Proxy" label says that a change needs a restart. `Twitch.request` uses a change at once. Each websocket
  reads the setting once, when its `_handle` task starts, and keeps that value for its reconnects. So PubSub uses
  a change only in a connection task that starts later: at the next run, or in a connection that the pool adds
  when the others are full.
- `refresh_interval` takes the values of its drop-down list, 0, 1, 2, 5, 10, 15 or 30 minutes, and
  `restart_delay` takes 0, 1, 5, 10, 15, 30 or 60 minutes, as `setting_choices` sets them. In both lists 0 is
  shown as "Never".
- `connection_quality` sets the timeouts to 5 seconds times its value for connecting and 10 seconds times its
  value in total. `Twitch.get_session` sets a value below 1 to 1 and a value above 6 to 6.

## Loading `settings.json`

`json_load(SETTINGS_PATH, default_settings)` in `utils.py`:

1. When `settings.json.new` exists, it reads that file. When that file is not valid JSON, it deletes it.
2. Otherwise it reads `settings.json`. When that file is not valid JSON, `json.JSONDecodeError` reaches
   `main.py`, which shows the "Settings error" dialog and exits with code 4.
3. Without either file it starts from a copy of `default_settings`.
4. It merges the result with `default_settings`: a key that is not in `default_settings` is removed, a value
   whose type is not exactly the type of the default is replaced by the default, and a missing key gets the
   default. All three happen without a message.

The type check compares `type(value)` with `type(default)`, so `1` for a `bool` is reset to the default. A value
saved as `{"__type": ..., "data": ...}` with a `__type` that `utils.SERIALIZE_ENV` does not name is removed and
then refilled with the default.

The merge does not check the items of a list or set. `Settings.__init__` then removes each item that is not a
string from the list and set settings through `drop_non_text_items` ([settingsdata.md](settingsdata.md)), and
logs a warning for each one. Without that, a number in `exclude` makes `SettingsPanel` raise `TypeError` while
the window is built, and one in `priority` makes `compile_patterns` raise. An item is removed rather than
converted to a string, because a number or a nested list names no game or folder. `Settings` is created before
`main()` sets up logging, so the `logging.lastResort` handler of Python prints the warning to stderr, which a
run from a terminal shows. The Output box and `log.txt` do not show it. The file keeps the removed items until a
change to the settings is saved.

Some values with the right type are corrected later. `SettingsPanel.__init__` sets a `priority_mode`,
`refresh_interval` or `restart_delay` that is not in its list in `setting_choices` to its default in
`default_settings`. `Twitch.get_session` limits `connection_quality` to 1 through 6.

## Saving `settings.json`

After each inventory fetch (`State.INVENTORY_FETCH`), `Twitch._run` calls `Settings.save()` without `force`,
through `save_each` ([savefiles.md](savefiles.md)): an `OSError`, such as from a full disk, is logged and the run
goes on. After the window closes, `main()` calls `Twitch.save(force=True)`, which saves the image cache and the
settings, and there an `OSError` passes up ([main.md](main.md)). A changed setting is therefore written at the
next reload or when the app closes. When the process is killed, the changes since the last save are lost.

`json_save` writes `settings.json.new` and then renames it over `settings.json` with `Path.replace`, so a save
that stops halfway leaves the previous `settings.json` unchanged. It sorts the keys and indents by 4 spaces.
A `set`, `URL`, `Enum` or `datetime` value is written as `{"__type": <class name>, "data": <value>}`, and
`json_load` turns it back into the class that `SERIALIZE_ENV` names.

## Invariants

- One `Settings` instance exists. `json_load` copies `default_settings` shallowly, so a list or set that the file
  does not have is the same object as the one in `default_settings`. A second instance would share it.
- A list or set changed in place is followed by `alter()`. Otherwise the change is saved only after the next
  assignment to a setting, or by the forced save at exit.
- A new type of setting value needs a branch in `utils._serialize` and an entry in `SERIALIZE_ENV`. Without the
  branch, `json_save` raises `TypeError`. Without the entry, the saved value is dropped and reset to the default
  on the next start.
- Every list and set setting holds strings. A list or set setting with items of another type needs a change to
  `drop_non_text_items`, which would otherwise remove all its items at load.
- The default of each setting in `setting_choices` is one of its choices, which `tests/test_settings.py` checks.
  Otherwise `SettingsPanel.__init__` raises `KeyError` for a stored value outside the list, the default
  included, and the window is not built.

**Dependencies.** Repo modules: `utils` (`json_load`, `json_save`), `savefiles` (`UnsavedChanges`),
`settingsdata` (`drop_non_text_items`), `constants` (`SETTINGS_PATH`, `DEFAULT_LANG`, `PriorityMode`), and `main`
for type checking only. Third-party: `yarl`.
