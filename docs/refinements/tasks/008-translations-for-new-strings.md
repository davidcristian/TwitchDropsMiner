# The translations lack the strings of new features

**Status:** open
**Area:** lang
**Origin:** found on 2026-10-18 while the docs were written
**Verified:** 2026-10-23

`default_translation` in `translate.py` has 160 strings. Of the 20 files in `lang/` other than `English.json`,
ten have every string, which were written as [ADR-0019](../../adr/ADR-0019-strings-without-a-native-speaker.md)
says. Each of the other ten, the remaining languages, lacks between 47 and 59 of them. `English.json` is left
out because it is gitignored and every run from source writes it again from `default_translation`. The counts
come from comparing the nested key paths of `default_translation`, read from `translate.py` with the `ast`
module, with the key paths of each file.

A missing key shows in English. `Translator.set_language` loads a language with
`json_load(path, default_translation)`, and `merge_json` in `utils.py` adds every key the file lacks from
`default_translation`. It also deletes every key that `default_translation` lacks, so a string at the wrong
path shows in English as well ([023](023-language-file-keys-dropped.md)).

## The 47 keys every remaining language lacks

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

- The Invalidate button, `gui.help.invalidate` (2 keys): every remaining language except 简体中文 and 繁體中文.
- The Advanced frame, `gui.settings.advanced` (5 keys): Português, Română, Čeština, Українська, العربية and
  日本語.
- Priority mode, `gui.settings.general.priority_mode` and `gui.settings.priority_modes` (4 keys): Português,
  Română, Čeština, العربية and 日本語.
- Tray notifications, `gui.settings.general.tray_notifications` (1 key): Čeština.

## Missing keys per language

- 59: Čeština.
- 58: Português, Română, العربية and 日本語.
- 54: Українська.
- 49: Türkçe and Русский.
- 47: 简体中文 and 繁體中文.
- 0: Dansk, Deutsch, Español, Français, Indonesian, Italiano, Magyar, Nederlandse, Norsk and Polski.

## What closes it

The missing strings of each remaining language are written as ADR-0019 says. The keys at a wrong path, which
need no translator, were moved or deleted in [023](023-language-file-keys-dropped.md). AGENTS.md says
a new string needs no edit to other languages, so new features keep adding to these counts. Every edit to
`lang/*.json` must stay valid JSON, which the CI Validate job checks. `scripts/langcheck.py` prints the
number of missing keys per language at each `just check`.

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
- 2026-10-23: `scripts/langcheck.py` now prints the number of strings each language lacks, without failing.
  It printed the counts above.
- 2026-10-23: The missing strings of ten languages were written in each language, as ADR-0019 says:
  Dansk 58, Deutsch 59, Español 47, Français 54, Indonesian 58, Italiano 58, Magyar 49, Nederlandse 60,
  Norsk 49 and Polski 47. `scripts/langcheck.py` now prints 0 for each of them. The other ten languages still
  lack 47 to 59 strings.
