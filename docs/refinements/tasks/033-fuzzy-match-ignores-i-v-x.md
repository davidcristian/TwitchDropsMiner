# A fuzzy game match ignores the numerals I, V and X

**Status:** done 2026-10-18
**Area:** gamelib (matching)
**Origin:** Found on 2026-10-18 by the first tests of `gamelib`, [ADR-0013](../../adr/ADR-0013-test-standard.md)
**Verified:** 2026-10-18

A fuzzy match in `match_games` (`gamelib/matching.py`) must keep the numbers of the two names equal, so that a
sequel does not match its original ([ADR-0004](../../adr/ADR-0004-installed-game-detection.md)). `_numbers`
collects the digit tokens and the tokens in `ROMAN_NUMERALS`, which lists `ii` to `xv` but not `i`, `v` or `x`.
A name that ends in one of those three letters therefore has the same numbers as the name without it:

| Local name | Twitch name | Result |
| --- | --- | --- |
| `Grand Theft Auto V` | `Grand Theft Auto` | `FUZZY` |
| `Final Fantasy X` | `Final Fantasy` | `FUZZY` |
| `Sid Meier's Civilization V` | `Sid Meier's Civilization` | `FUZZY` |
| `Grand Theft Auto 5` | `Grand Theft Auto` | no match |

Each row is one call of `match_games([LocalGame(local, Platform.STEAM)], [twitch])` on Python 3.10. The names
are test inputs. When Twitch also lists `Grand Theft Auto V`, the exact match wins. When it lists
`Grand Theft Auto 5` and `Grand Theft Auto`, the number check skips the first and the fuzzy match still pairs
the second. A false match makes the installed sequel add the original to the games the app mines.

A fix counts a lone `i`, `v` or `x` token as a number in `_numbers` only, where it is compared and not shown, or
lists them in `ROMAN_NUMERALS` if the variant matching in `_variants` should also fold them. A single letter is
sometimes a word (`Mega Man X`), so the fix keeps exact and variant matches as they are. The strict `xfail` test
in `tests/test_gamelib_matching.py` that names this file passes once it is fixed. Twitch requests: none.

## How it was closed

`_numbers` counts a lone `i`, `v` or `x` as 1, 5 or 10 (`SINGLE_LETTER_NUMERALS`), only where the numbers of
two names are compared. `Grand Theft Auto V`, `Final Fantasy X` and `Sid Meier's Civilization V` no longer
match the name without the numeral, and neither does `Mega Man X Legacy Collection` match
`Mega Man Legacy Collection`. Exact and variant matches still read the letters as letters, so `Mega Man X` is
not a variant of `Mega Man 10`.

A review over 307 pairs of real names found no new wrong match. 13 wrong matches are gone, and 9 correct
ones are new: a game written once with 1, 5 or 10 and once with I, V or X pairs as `FUZZY`
(`Grand Theft Auto 5` and `Grand Theft Auto V`, `Street Fighter V` and `Street Fighter 5`). 18 correct
matches are lost, where one name has a lone numeral that the other lacks, such as `Mortal Kombat XL` against
`Mortal Kombat X` or `The Elder Scrolls V: Skyrim` against `The Elder Scrolls: Skyrim`.
[ADR-0004](../../adr/ADR-0004-installed-game-detection.md) records that cost, and a test asserts it.

## History

- 2026-10-18: Opened. The first `gamelib` tests found it, and direct calls of `match_games` confirmed it.
- 2026-10-18: Closed. A lone I, V or X counts as a number in the fuzzy match only.
