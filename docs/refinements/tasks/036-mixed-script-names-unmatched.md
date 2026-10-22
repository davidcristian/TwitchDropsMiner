# A name that holds a native title and an English one does not match the English Twitch name

**Status:** done 2026-10-23
**Area:** gamelib (matching)
**Origin:** [032](032-names-outside-a-to-z-dropped.md), whose fix lost these matches
**Verified:** 2026-10-23

Some Steam releases of Chinese and Japanese games are named with both the native title and the English title.
The app asks Twitch for English names, so the Twitch side is the English title alone. Since `normalize` keeps
the letters of every script ([032](032-names-outside-a-to-z-dropped.md)), the native part stays, and these pairs
no longer match. Calls of `match_games([LocalGame(local, Platform.STEAM)], [twitch])` on Python 3.10:

| Local name | Twitch name | Before 032 | Now |
| --- | --- | --- | --- |
| `原神 Genshin Impact` | `Genshin Impact` | `EXACT` | no match |
| `鬼谷八荒 Tale of Immortal` | `Tale of Immortal` | `EXACT` | no match |
| `雀魂麻將(MahjongSoul)` | `Mahjong Soul` | `FUZZY` | no match |

The local names are test inputs; which of them a launcher writes this way was not checked. A missed match can be
added to the Priority list by hand ([ADR-0004](../../adr/ADR-0004-installed-game-detection.md)), so this was
left for later. A fix adds a variant in `_variants` without the words that hold no Latin letter or digit, when
what is left is at least `FUZZY_MIN_LENGTH` characters long. Its risk is a wrong match through an English
subtitle that two games of a series share, so it needs the same check over real names that 032 had.
Twitch requests: none.

## How it was closed

`_match_one` in `gamelib/matching.py` also matches a local name by its English title when the name starts with
a native title: leading words with no letter `a` to `z` and no digit, then only words of `a` to `z` and digits,
at least `FUZZY_MIN_LENGTH` characters long. The variant step adds the variants of that title, and the fuzzy
step compares it with the Twitch names written in `a` to `z` and digits. The three names in the table match
again, the first two as `VARIANT` and `雀魂麻將(MahjongSoul)` as `FUZZY`.

The variant in `_variants` that this file proposed would also remove words from Twitch names and words after
the English title, so `仙剑奇侠传 Sword and Fairy` would match `轩辕剑 Sword and Fairy`, and
`Escape from Tarkov: Арена` would match `Escape from Tarkov`. A digit in the native title, or a word of it that
ends with a numeral as in `仙剑奇侠传七`, keeps the whole name, because it can be a sequel number that the English
title leaves out.
[gamelib.md](../../modules/gamelib.md#matching-rules) lists the rules, and `tests/test_gamelib_native_titles.py`
tests each limit.

43 local names in two scripts were matched against 45 English Twitch names that include the other games of
each series. 25 results changed, each from no match or `FUZZY` to the correct game. A name with no native title
gives the same result as before. The same names showed that a name that ends with a lone letter such as `Σ`
pairs with the name without it ([076](076-lone-letter-at-the-end-pairs-as-fuzzy.md)).

## History

- 2026-10-18: Opened. The 032 fix lost these matches.
- 2026-10-23: Closed. A local name that starts with a native title is also matched by its English title. Opened
  [076](076-lone-letter-at-the-end-pairs-as-fuzzy.md).
