# Some text the app shows is written in the code and is not translated

**Status:** open
**Area:** gui, gamelib, translate
**Origin:** Found on 2026-10-18 while the docs were written, [translate.md](../../modules/translate.md#invariants)
**Verified:** 2026-10-18

[AGENTS.md](../../../AGENTS.md#recipes) says text that the GUI or the console shows comes from `_()`. These
strings are written in English in the code, so a user who picked another language sees them in English:

| Where | Text | Where it shows |
| --- | --- | --- |
| `LoginForm.ask_enter_code` in `gui.py` | `Enter this code on the Twitch's device activation page: {user_code}` | Output box, at each login that needs a device code |
| `GUIManager.__init__` in `gui.py` | `Logging level: {name}`, with the name from `logging.getLevelName` | Output box at start, with any `-v` flag (the level is below `ERROR`) |
| `scan_directories` in `gamelib/scan.py` | `Not a directory: {directory}` and `No Steam or Epic games found in: {directory}` | Output box, inside the translated `Game scan: {error}` line that `Twitch.detect_games` prints |
| `SettingsPanel.__init__` in `gui.py`, the language frame | `Language 🌐 (requires restart): ` | Settings tab, next to the language box |

`scan_directories` also reports `{directory}: {exc}` when `is_dir()` raises `OSError`. That text comes from the
operating system.

The line before the login code, `Please log in to continue.` (`gui.login.request`), is translated, so the two
lines of the login message appear in two languages.

## The language label

The label came in the commit that added translations ("Implement the translation feature", 2022-08-18, in the
original project), already in English. No commit message or code comment gives a reason. A later commit on the
original project's `no_emoji` branch removed the `🌐` and kept the English text. A likely reason, which is an
assumption: a user who picked a language they cannot read still finds the setting to switch back. This task
does not count the label as a string to translate. The fix records the reason in a comment next to the label,
or gives the label a translated part followed by the English word.

## Strings that stay English for a reason

The search below found these as well. Each has a reason to stay as it is:

- In `main.py`, the "Settings error" dialog and the argparse output. Both appear before `main()` calls
  `_.set_language`, and the settings error means the language setting could not be read. The title of the
  argparse dialog is the subject of [task 025](025-version-and-help-shown-as-error.md).
- `RuntimeError("Python 3.10 or higher is required")` in `main.py`, raised before the GUI exists.
- The product name `Twitch Drops Miner` (`WINDOW_TITLE`, `TrayIcon.TITLE`) and the GitHub link on the Help tab.
- The `Name` and `Description` lines of the Linux autostart `.desktop` file, which the desktop reads, not the
  app.
- Log records. `_TKOutputHandler` writes each record of `TwitchDrops` and its child loggers at the chosen level
  to the Output box. At the default level (`ERROR`, no `-v`) that includes 14 `error` and `exception` calls,
  such as `Drop claim has potentially failed! Drop ID: {id}` in `TimedDrop.claim` and `Game folder scan failed`
  in `Twitch.detect_games`. They are English diagnostics, the same text that `log.txt` gets with `--log`.
  Whether a user-facing error among them also gets a translated line is a decision for the fix.

One case is unclear: the proxy placeholder `http://username:password@address:port` in `SettingsPanel`. It shows
the form of a proxy URL, and its four words are English.

How the search was done: `grep` for `.print(`, `status.update(`, `text=`, `placeholder=`, `messagebox` and English
string literals in `gui.py` (above the preview under `if __name__ == "__main__":`), `twitch.py`, `main.py`,
`inventory.py`, `channel.py`, `websocket.py` and `gamelib/`. Every `print` and `status.update` call in
`twitch.py`, and the claim message in `inventory.py`, use `_()`.

## What a fix involves

1. Add a key for each string in the first table to the `TypedDict`s and `default_translation` in `translate.py`,
   with the same named fields (`{code}` for the login code, `{level}` for the logging level), and read it with
   `_()` ([AGENTS.md](../../../AGENTS.md#recipes)).
2. `gamelib` imports no repo module ([gamelib.md](../../modules/gamelib.md)), so it cannot call `_()`.
   `ScanResult.errors` can hold a kind and a path instead of a sentence, and `Twitch.detect_games` builds the
   text with `_()`. `detect_games` compares the error strings of one scan with the last one
   (`_scan_errors_printed`) to print each problem once. A language change needs a restart, so the strings stay
   the same within a run.
3. Other languages need no edit. A missing key shows in English until someone translates it
   ([task 008](008-translations-for-new-strings.md)).

Cost: no Twitch requests. The language label and the login line are GUI changes, so the fix is run in
`python gui.py`.

How the strings came in: the device activation line with the SmartTV OAuth2 login flow (2022-12-23) and the
logging level line with "Review and adjust the logging module levels" (2022-12-07), both in the original
project; the scan errors with installed game detection on 2026-08-24.

## History

- 2026-10-18: Opened while the docs were written, from a search of the modules for text shown without `_()` and
  `git log -S` for the commit that added each string.
