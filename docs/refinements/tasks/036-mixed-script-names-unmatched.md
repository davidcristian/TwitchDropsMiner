# A name that holds a native title and an English one does not match the English Twitch name

**Status:** open
**Area:** gamelib (matching)
**Origin:** [032](032-names-outside-a-to-z-dropped.md), found by the review of its fix
**Verified:** 2026-10-18

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
subtitle that two games of a series share, so it needs the same review over real names that 032 had.
Twitch requests: none.

## History

- 2026-10-18: Opened. The review of the 032 fix found the lost matches.
