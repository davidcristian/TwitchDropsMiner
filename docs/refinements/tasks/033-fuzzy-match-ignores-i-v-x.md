# A fuzzy game match ignores the numerals I, V and X

**Status:** open
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

## History

- 2026-10-18: Opened. The first `gamelib` tests found it, and direct calls of `match_games` confirmed it.
