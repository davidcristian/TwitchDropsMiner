# A name that ends with a lone letter such as Σ pairs with the name without it

**Status:** done 2026-10-23
**Area:** gamelib (matching)
**Origin:** Found on 2026-10-23 while local names in two scripts were matched against English Twitch names for
[036](036-mixed-script-names-unmatched.md)
**Verified:** 2026-10-23

The fuzzy step of `match_games` in `gamelib/matching.py` pairs two names that differ by one word of one letter at
the end, when that letter is not one of the numerals `i`, `v` and `x` (`SINGLE_LETTER_NUMERALS`). Such a letter
often names another release of a series. Calls of `match_games([LocalGame(local, Platform.STEAM)], [twitch])` on
Python 3.12:

| Local name | Twitch name | Result |
| --- | --- | --- |
| `NINJA GAIDEN Σ` | `Ninja Gaiden` | `FUZZY`, ratio 0.923 |
| `Ninja Gaiden` | `NINJA GAIDEN Σ` | `FUZZY`, ratio 0.923 |
| `Kingdom Hearts χ` | `Kingdom Hearts` | `FUZZY`, ratio 0.933 |
| `New Super Mario Bros. U` | `New Super Mario Bros.` | `FUZZY`, ratio 0.952 |

`NINJA GAIDEN Σ` is a remake that Steam sells apart from the other games of its series. A wrong match mines a
game the user did not choose. The GUI marks it with `≈`, and the Exclude list overrides it
([ADR-0004](../../adr/ADR-0004-installed-game-detection.md)). A fix could let `_numbers` count every word of one
letter, so both names need the same such words, as they need the same numbers. It needs a check over real names
for the correct pairs it would lose, such as a name written once with a one letter word and once without.
Twitch requests: none.

## How it was closed

`_numbers` in `gamelib/matching.py` counts each word of one letter that is not `i`, `v` or `x` as itself, so
the fuzzy step needs the same lone letters on both sides, in order, as it needs the same numbers. The four pairs
in the table no longer match, nor do `NINJA GAIDEN Σ` and `NINJA GAIDEN Ω`. Names with the same lone letters
still pair, and exact and variant matches do not read numbers, so they are unchanged.

40 pairs built from real game names with lone letters, 26 of one game and 14 of two games, changed in 10
results. 9 wrong fuzzy matches are gone. One correct one is lost: `A Plague Tale: Innocence` and `Plague Tale: Innocence`, because the
article `a` is a lone letter too, which [ADR-0004](../../adr/ADR-0004-installed-game-detection.md) accepts as it
accepts the lone `x` of `Mortal Kombat X`. `tests/test_gamelib_numerals.py` tests both sides.

## History

- 2026-10-23: Opened. Local names in two scripts, matched for [036](036-mixed-script-names-unmatched.md),
  showed the pair `NINJA GAIDEN Σ` and `Ninja Gaiden`.
- 2026-10-23: Closed. A lone letter counts as a number in the fuzzy step.
