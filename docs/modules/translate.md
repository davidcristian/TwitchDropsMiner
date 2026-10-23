# `translate.py`

**Purpose.** The strings the app shows to the user. It holds the `Translation` types that name each string,
the English strings in `default_translation`, and `_`, the one `Translator` instance that returns a string in
the current language. Other languages are JSON files in `lang/`. To add a string, follow the recipe in
[AGENTS.md](../../AGENTS.md#recipes).

## Public contract

### The `Translation` types

`Translation` is a tree of `TypedDict` classes. Each leaf is a `str`.

| Key | Type | What it holds |
| --- | --- | --- |
| `language_name` | `NotRequired[str]` | Set by `Translator` to the name of the loaded language; a file cannot set it |
| `english_name` | `str` | The language's name in English. No code reads it. It stays to tell a reader which language a file such as `العربية.json` holds |
| `status` | `StatusMessages` | Lines printed to the Output box, such as `watching` and `claimed_drop` |
| `login` | `LoginMessages` | `unexpected_content` |
| `error` | `ErrorMessages` | `no_connection`, `site_down`, `save_failed`, `file_not_saved`, `cannot_start`, `folder_not_writable` |
| `arguments` | `ArgumentMessages` | `title` and `error_title`, the titles of the message box that shows the command line output ([main.md](main.md#command-line-flags)) |
| `gui` | `GUIMessages` | The window's text, one nested type per part |

`GUIMessages` contains `GUIStatus`, `GUITabs`, `GUITray`, `GUILoginForm`, `GUIWebsocket`, `GUIProgress`,
`GUIChannels` (with `GUIChannelHeadings`), `GUIInventory` (with `GUIInvFilter` and `GUIInvStatus`),
`GUISettings` and `GUIHelp`. `GUISettings` contains `GUISettingsGeneral`, `GUISettingsAdvanced`,
`GUIPriorityModes`, `GUIRefreshIntervals`, `GUIRestartDelays`, `GUISettingsDetect` and `GUISettingsWanted`.
`GUIHelp` contains `GUIHelpAbout`, `GUIHelpLinks` and `GUIHelpInvalidate`.

### `default_translation`

The English strings, typed as `Translation`. It is the only source of translatable English text: the app reads
English from it in memory, and every other language falls back to it. Some strings are `str.format` templates
with named fields, such as `"Watching: {channel}"`.

### `_` and `Translator`

- `_(*path)` returns the string at `path` in the current translation: `_("gui", "status", "idle")` returns
  `"Idle"` in English. With no `path` it raises `ValueError`. When a key on the path does not exist, it raises
  `MinerException` naming the language and the path. A path that ends at a dict returns the dict.
- `_.languages` iterates over the language names: `"English"` first, then the other file names in `lang/`
  without `.json`, sorted.
- `_.current` is the name of the loaded language.
- `_.set_language(language)` loads a language. It raises `ValueError` for a name not in `_.languages`. `main()`
  calls it once at start with the `language` setting, before the window is built ([main.md](main.md)).
- `save_template(folder=LANG_PATH)` writes `default_translation` to `English.json` in `folder` with `json_save`.
  An `OSError` from the write passes to the caller.

## How the language files are found and loaded

`LANG_PATH` in `constants.py` is the `lang` folder next to the code: the folder of `main.py` in a run from
source, the PyInstaller unpack folder (`sys._MEIPASS`) in a PyInstaller build, and the folder of the started
script in the AppImage. `Translator.__init__` lists the `*.json` files in it once, when `translate` is imported.
A language's name is its file name, such as `Polski` for `lang/Polski.json`.

`set_language` does nothing for the language already loaded. For `"English"` it takes a copy of
`default_translation` and reads no file. For any other language it calls `json_load` (`utils/jsonfile.py`) with
`default_translation` as the template, which changes the file's data in memory:

- A key that the file does not have gets the English string, so a missing key shows in English.
- A key that `default_translation` does not have is removed.
- A value whose type differs from the English one, such as a string where a section is expected, is replaced
  by the English value.

`scripts/langcheck.py` fails on a key that the merge removes or replaces, so that no translated text is lost
this way. The merge removes `language_name` from a file as an unknown key, so a file cannot change the name of
its language.

A file that is not valid JSON makes `set_language` raise `json.JSONDecodeError`. It is a `ValueError`, so
`main()` catches it and the app stays in English without a message. `scripts/langcheck.py`, which
[`just check`](../../AGENTS.md#what-every-change-must-pass) runs locally and in CI's Validate job on each pull
request and each push to `master`, parses each `lang/*.json` file to find such a file.

## Why `lang/English.json` is rewritten on every run from source

In a run from source (`IS_PACKAGED` is false), `main.py` calls `save_template()` at start, which writes
`default_translation` to `lang/English.json`. The file is a template: it always contains the current keys and
English strings, for a translator to copy. The file is only generated output, so `.gitignore` lists it and
`default_translation` stays the one place where English is edited. An edit to `lang/English.json` is
overwritten on the next run. A packaged build does not write it, and `build.spec` leaves it out of the
PyInstaller build.

Importing `translate` writes no file, so that a test can import it and the modules that import it: under
pytest, `LANG_PATH` is in the folder of pytest itself, which has no `lang` folder. The GUI preview,
`python gui.py`, does not write the file either.

## Text that stays English

The window and the Output box show text from `_()`, except this, which stays English:

- What `main.py` shows before it calls `_.set_language`: the "Settings error" dialog, argparse's output and the
  titles of its dialog ([main.md](main.md#command-line-flags)), and the error for a Python older than 3.10.
- Names and addresses: the product name `Twitch Drops Miner`, the links on the Help tab, and the proxy
  placeholder `http://username:password@address:port`, which shows the form of a proxy URL.
- The `Name` and `Description` lines of the Linux autostart entry, which the desktop reads
  ([autostart.md](autostart.md)).
- The word `Language` before a translated "Language" label ([Invariants](#invariants)).
- Log records. `_TKOutputHandler` writes each record of the `TwitchDrops` loggers at the chosen level to the
  Output box, so the `error` and `exception` calls show there at the default level, such as
  `Drop claim has potentially failed! Drop ID: {id}`. They are diagnostics, the same text that `log.txt` gets
  with `--log`. A log call for a problem that the user solves, such as a failed save, passes its text through
  `_()`.

## Invariants

- No module calls `_()` at import time. The language is set in `main()` after all imports, so a string read
  earlier would always be English. `SettingsPanel` reads its choice names in `cached_property` attributes for
  this reason ([gui.md](gui.md)).
- Widgets read their text when they are built, so a language change needs a restart. The "Language" label in
  the Settings tab says so. When its text differs from the English string, `SettingsPanel` puts the English word
  before it, as in `Language / Język`, so a user who picked a language they cannot read still finds the setting.
- A key added to a `TypedDict` is added to `default_translation` too. A key missing there raises
  `MinerException` when it is read, in every language.
- A translated template uses only the named fields of the English one. `str.format` raises `KeyError` for a
  field the code does not pass, and `ValueError` for a lone brace. `scripts/langcheck.py` fails on a field that
  the English string at the same keys lacks. It fails on a lone brace or an unknown conversion such as `!x` only
  where the English string has a field, because the code formats only those strings. It does not check a format
  spec such as `:>3`, which `str.format` reads with the value.
- Other languages need no edit for a new key, because the merge fills it in English
  ([task 008](../refinements/tasks/008-translations-for-new-strings.md)). `scripts/langcheck.py` prints how many
  strings each language lacks, and does not fail on them.

**Dependencies.** Repo modules: `exceptions` (`MinerException`), `utils` (`json_load`, `json_save`) and
`constants` (`LANG_PATH`, `DEFAULT_LANG`). No third-party package.
