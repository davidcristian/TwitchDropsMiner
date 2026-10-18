# Letters outside a to z are removed from normalized game names

**Status:** done 2026-10-18
**Area:** gamelib (matching and patterns)
**Origin:** Found on 2026-10-18 by the first tests of `gamelib`, [ADR-0013](../../adr/ADR-0013-test-standard.md)
**Verified:** 2026-10-18

`normalize` in `gamelib/matching.py` decomposes a name with Unicode NFKD, drops the accents, and then turns every
character that is not `a` to `z` or `0` to `9` into a space. A letter of another script, or a Latin letter with
no decomposition, is removed with the punctuation. Calls on Python 3.10:

| Call | Result |
| --- | --- |
| `normalize("Мир танков")` | `""` |
| `normalize("Мир танков 2")` and `normalize("Тетрис 2")` | `"2"` for both |
| `normalize("Straße")` | `"stra e"` |
| `match_rank(compile_patterns(["Мир танков"]), "Мир кораблей")` | `0`, a match |
| `match_games([LocalGame("Мир танков 2", Platform.STEAM)], ["Тетрис 2"])` | an `EXACT` match |

[ADR-0005](../../adr/ADR-0005-list-patterns.md) says entries match names ignoring case, accents and punctuation.
A Priority or Exclude entry written in Cyrillic, Greek or CJK normalizes to an empty pattern or to its digits,
so it matches every name that normalizes the same way: an Exclude entry `Мир танков` excludes every game whose
name has no Latin letter or digit. Installed game detection pairs two different games that share only a number.
The app ships Russian, Ukrainian, Japanese and Chinese translations, whose users can see such names.

A fix keeps every letter and digit of every script (`str.isalnum` after the accents are dropped, or the regular
expression class `[^\W_]`) and still splits on punctuation. It changes the normalized form of no name written in
a to z, so the existing matches stay. The strict `xfail` tests in `tests/test_gamelib_matching.py` and
`tests/test_gamelib_patterns.py` that name this file pass once it is fixed. Twitch requests: none.

## How it was closed

`normalize` now keeps the letters, digits and marks of every script. It removes the accents of Latin and Greek
letters only, joins the other marks back to their letters with NFC (`й`, `ガ`, Hangul syllables), folds case with
`str.casefold`, and writes the Latin letters that have no accent form in English letters (`Æterna` as `aeterna`,
`Łódź` as `lodz`). `normalize("Мир танков")` returns `"мир танков"`, so the entry `Мир танков` no longer matches
`Мир кораблей`, and `Мир танков 2` no longer pairs with `Тетрис 2`. Every name written in `a` to `z` normalizes as
before, checked over 406 such names. The fuzzy number check also reads digits inside a word now (`σ2`, `三國志14`,
`lineage2`), because the letters around them stay. The two strict `xfail` tests pass without the mark, and new
tests cover the scripts, the marks and the numbers.

One correct match is lost: a name that holds a native title and an English one, such as
`原神 Genshin Impact`, no longer equals the English Twitch name ([036](036-mixed-script-names-unmatched.md)).

## History

- 2026-10-18: Opened. The first `gamelib` tests found it, and direct calls of `normalize`, `match_rank` and
  `match_games` confirmed it.
- 2026-10-18: Closed. `normalize` keeps the letters of every script and folds case.
