# ADR-0019: Missing strings written without a native speaker

**Status:** Accepted (2026-10-23)

## Context

`default_translation` in `translate.py` has 160 strings. Each of the 20 language files in `lang/` other than
`English.json` lacked 47 to 60 of them, most of them the strings of this project's own features. A missing
string shows in English ([translate.md](../modules/translate.md#how-the-language-files-are-found-and-loaded)),
so the Settings tab of every language showed part of its text in English. The project has no translator for any
of these languages.

## Decision

1. **The maintainer's side writes the missing strings of each language.** No native speaker reviews them before
   they are merged. A string in the reader's language is more useful than the English one, even when a native
   speaker would choose other words.
2. **Each string follows its file.** It uses the file's own words for the app's terms, such as campaign, drop,
   channel, game, priority, exclude, reload and tray, and the file's form of address, formal or informal. It
   keeps every format field of the English string and its emoji. It keeps a trailing colon or space in the form
   that the file's own labels write it, such as a full-width colon in 日本語, a space before the colon in
   Română, no colon in the General frame of 简体中文, and the colon or ellipsis at the start of an العربية
   string. A string with a number reads correctly for any number, for example through an abbreviation such as
   `min` or with the number after a colon. A choice in a drop-down list or a button label stays about as short
   as the English one, so that the window is no wider than with the English string.
3. **The strings are inserted and nothing else changes.** A script adds each missing key at its path, in the
   order of `default_translation`. It keeps the file's indent, line endings, escaped characters and the order
   of its existing keys, and it changes no existing string.
4. **A speaker of the language may correct any of these strings.** A correction from a speaker replaces the
   string written here, through a pull request like any other change.
5. **A new string is added in English only.** As the recipe in [AGENTS.md](../../AGENTS.md#recipes) says, the
   change that adds a string edits `default_translation` and no language file, and the other languages show it
   in English. `scripts/langcheck.py` prints how many strings each language lacks at each `just check`. A later
   change writes those strings in each language as decisions 2 and 3 say.

## Consequences

- After the change that writes them, `langcheck.py` prints 0 missing strings for each language, until the next
  new string.
- Some strings may read as written by someone who does not speak the language, or use a word that a speaker
  would not choose. Only a speaker who reads them finds these.
- An existing string that no longer matches the English one stays as it is, such as a Getting Started text
  that names a checkbox the window no longer has. Decision 3 leaves it to a speaker.
- The README's translator credits name the people who wrote each file, and stay as they are
  ([ADR-0007](ADR-0007-kept-identifiers.md)).

## Alternatives rejected

- **Waiting for a speaker of each language.** Until one comes, every user of that language reads part of the
  window in English, and nothing shows when one will come.
- **Writing each new string in all 20 languages in the change that adds it.** Every change to the text would
  then need 20 translations, which the recipe in AGENTS.md leaves out on purpose.
- **Translating each whole file again.** It would replace the words that each file's translator chose.

## Related

- [translate.md](../modules/translate.md), and [ADR-0012](ADR-0012-check-command.md) for `langcheck.py`.
- Task [008](../refinements/tasks/008-translations-for-new-strings.md), the strings that the language files
  lacked.
