# Some language files have strings at paths the app does not read

**Status:** open
**Area:** lang
**Origin:** Found on 2026-10-18 while the docs were written, [translate.md](../../modules/translate.md)
**Verified:** 2026-10-18

`Translator.set_language` in `translate.py` loads a language file with `json_load(path, default_translation)`.
`merge_json` in `utils.py` then deletes, without a message, every key that `default_translation` does not have.
Eleven files in `lang/` have 13 such keys:

| File | Key in the file | What the app reads |
| --- | --- | --- |
| Polski | `gui.invalidate.button`, `gui.invalidate.text` | `gui.help.invalidate.button` and `gui.help.invalidate.text` |
| Dansk, Deutsch, Indonesian, Italiano, Nederlandse, Português, Română, Čeština, العربية, 日本語 | `gui.settings.general.priority_only` | nothing; the key belonged to a check box that the Priority mode list replaced |
| Nederlandse | `gui.inventory.filter.linked` | `gui.inventory.filter.not_linked` |

No file has a value whose type differs from the English one, which the merge would also replace.

## How it was confirmed

- A script read `default_translation` from `translate.py` with `ast.literal_eval` and compared its nested key
  paths with those of each file in `lang/` other than `English.json`. It printed each path that a file has and
  `default_translation` lacks, and each value whose type differs. It printed the 13 keys above and no type
  difference.
- A real call loaded the files with `Translator.set_language`, from a copy of `lang/` in a temporary folder.
  After `set_language("Polski")`, `_("gui", "help", "invalidate", "button")` returned `'Invalidate'`, the text
  returned the English string, and the loaded data had no `gui.invalidate`. `Polski.json` has `"Unieważnij"` at
  `gui.invalidate.button`.
- After `set_language("Deutsch")` and `set_language("Nederlandse")`, the loaded data had no
  `gui.settings.general.priority_only`, and `gui.settings.general.priority_mode` returned the English
  `'Priority mode: '`. For Nederlandse, `gui.inventory.filter.not_linked` returned `'Not linked'`.

## Effect

A Polish user sees the Invalidate button on the Help tab and its label in English, although `Polski.json`
translates both. The other 11 keys change nothing on screen: the app does not read them, and the keys that
replaced them show in English. [Task 008](008-translations-for-new-strings.md) counts those replacement keys
among the missing ones.

## How it came about

From `git log -S` and `git show` on `translate.py` and the language files. All three come from the original
project.

- Polski: the English keys came in "Implement the auth token invalidation button" (2026-07-02). "Update Polish
  translation" (2026-07-15) added the two strings after the closing brace of `gui.help`, one level too high.
- `priority_only`: "Add a prioritization strategy for games outside of the priority list" (2024-09-11) replaced
  the Priority only check box with the Priority mode list. It removed `gui.settings.general.priority_only` from
  `default_translation` and added `gui.settings.general.priority_mode` and `gui.settings.priority_modes`. The
  ten files were not updated.
- Nederlandse: "Change inventory filters to show all campaigns when all of them are selected" (2023-10-29)
  replaced the English filter `linked` ("Linked only") with `not_linked` ("Not linked"). "Added Dutch language"
  (2023-11-03) used the old key, with "Alleen gekoppelde", which means "only linked".

## What a fix involves

- Polski: move the two strings from `gui.invalidate` to `gui.help.invalidate`. They are already in Polish, so
  this needs no translator.
- `priority_only`: delete it from the ten files. Its text, such as `"Nur Priorität:"` in `Deutsch.json`,
  translates the old English label "Priority Only: ". It does not fit "Priority mode: " or the choice
  "Priority list only" as it is, so a speaker of each language writes the new keys
  ([008](008-translations-for-new-strings.md)).
- Nederlandse `linked`: delete it. It means the opposite of `not_linked`, so it cannot be moved.

Each edit keeps the file valid JSON, which CI's Validate job checks. A script that lists keys the app does not
read fits in the check command of [004](004-single-check-command.md), next to the missing key report that 008
asks for. If [022](022-unused-code.md) removes the `login.chrome` keys or `english_name` from
`default_translation`, the files that have them gain more keys of this kind, and the same fix deletes them.

Cost: no Twitch requests.

## History

- 2026-10-18: Opened. A comparison of the key paths in each language file with `default_translation`, made
  while the docs were written, found the keys. Split from the part of 008 that needs no translator.
