# The translations lack the strings of new features

**Status:** open
**Area:** lang
**Origin:** found on 2026-10-18 while the docs were written
**Verified:** 2026-10-23

`default_translation` in `translate.py` has 160 strings. Each of the 20 files in `lang/` other than
`English.json` lacks between 47 and 60 of them. `English.json` is left out because it is gitignored and every
run from source writes it again from `default_translation`. The counts come from comparing the nested key
paths of `default_translation`, read from `translate.py` with the `ast` module, with the key paths of each
file.

A missing key shows in English. `Translator.set_language` loads a language with
`json_load(path, default_translation)`, and `merge_json` in `utils.py` adds every key the file lacks from
`default_translation`. It also deletes every key that `default_translation` lacks, so a string at the wrong
path shows in English as well ([023](023-language-file-keys-dropped.md)).

## The 47 keys every language lacks

These are the strings of this project's own features:

- Installed game detection, `gui.settings.detect`: 11 keys.
- The Games Being Mined table, `gui.settings.wanted`: 7 keys.
- Restart after a fatal error, `gui.settings.general.restart_delay`, `gui.settings.restart_delays`,
  `gui.status.restarting`, `status.fatal_error`, `status.restarting` and `status.restart_longer`: 7 keys.
- The About box, `gui.help.about`: 4 keys.
- The new stream check, `gui.settings.general.refresh_interval` and `gui.settings.refresh_intervals`: 3 keys.
- Priority and Exclude patterns, `gui.settings.pattern_matches` and `gui.settings.pattern_empty`: 2 keys.
- A failed save during the run, `error.save_failed` and `error.file_not_saved`: 2 keys.
- The dialog when the app cannot start, `error.cannot_start` and `error.folder_not_writable`: 2 keys.
- The titles of the box that shows the command line output, `arguments.title` and `arguments.error_title`:
  2 keys.
- A failed change of the autostart entry, `error.autostart_not_changed`: 1 key.
- Text that the code wrote in English before: `gui.login.enter_code`, `status.logging_level`,
  `gui.settings.general.language`, and the scan errors `not_a_folder`, `no_games` and `failed` in
  `gui.settings.detect`: 6 keys.

## Older keys some languages lack

- The Invalidate button, `gui.help.invalidate` (2 keys): every language except Español, Polski, 简体中文 and
  繁體中文.
- The Advanced frame, `gui.settings.advanced` (5 keys): Dansk, Deutsch, Français, Indonesian, Italiano,
  Nederlandse, Português, Română, Čeština, Українська, العربية and 日本語.
- Priority mode, `gui.settings.general.priority_mode` and `gui.settings.priority_modes` (4 keys): Dansk,
  Deutsch, Indonesian, Italiano, Nederlandse, Português, Română, Čeština, العربية and 日本語.
- Tray notifications, `gui.settings.general.tray_notifications` (1 key): Deutsch, Nederlandse and Čeština.
- The inventory filter, `gui.inventory.filter.not_linked` (1 key): Nederlandse.

## Missing keys per language

- 60: Nederlandse.
- 59: Deutsch and Čeština.
- 58: Dansk, Indonesian, Italiano, Português, Română, العربية and 日本語.
- 54: Français and Українська.
- 49: Magyar, Norsk, Türkçe and Русский.
- 47: Español, Polski, 简体中文 and 繁體中文.

## What closes it

A speaker of each language adds the missing keys. The keys at a wrong path, which need no translator, were
moved or deleted in [023](023-language-file-keys-dropped.md). AGENTS.md says
a new string needs no edit to other languages, so new features keep adding to these counts. Every edit to
`lang/*.json` must stay valid JSON, which the CI Validate job checks. A script that reports the missing keys
per language fits in the check command of [004](004-single-check-command.md).

Cost: no Twitch requests.

## History

- 2026-10-18: Opened. Found while the docs were written, from a comparison of the key paths in each language
  file with `default_translation`.
- 2026-10-19: Counts checked again after the password login's 10 strings left `default_translation`: 150
  strings, and Čeština lacks 49 of them.
- 2026-10-20: Counts checked again after `error.save_failed` was added: 151 strings, and Čeština lacks 50
  of them.
- 2026-10-21: Counts checked again after `error.file_not_saved` was added: 154 strings, and Čeština lacks 53
  of them. The count includes `error.cannot_start` and `error.folder_not_writable`, which were added before.
- 2026-10-22: Counts checked again after `status.restart_longer` was added: 155 strings, and Čeština lacks 54
  of them.
- 2026-10-23: Counts checked again after the four `login.chrome` strings left `default_translation`: 154
  strings, and Čeština lacks 53 of them. The counts include `arguments.title`, `arguments.error_title` and
  `error.autostart_not_changed`, which were added before.
- 2026-10-23: Counts checked again after six strings that the code wrote in English were added to
  `default_translation`: 160 strings, and Čeština lacks 59 of them.
- 2026-10-23: Counts checked again after the keys at paths the app does not read left the language files
  ([023](023-language-file-keys-dropped.md)). Polski's two Invalidate strings moved to `gui.help.invalidate`,
  so Polski lacks 47 strings. The other counts did not change.
