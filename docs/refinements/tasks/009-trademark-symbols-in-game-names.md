# The ™ sign becomes the letters TM in normalized game names

**Status:** done 2026-10-19
**Area:** gamelib (matching and patterns)
**Origin:** Found on 2026-10-18 while the docs were written, [gamelib.md](../../modules/gamelib.md#matching-rules)
**Verified:** 2026-10-19

`normalize` in `gamelib/matching.py` starts with Unicode NFKD decomposition. NFKD writes `™` (U+2122) as the
letters `TM` and `℠` (U+2120) as `SM`, and the later steps keep letters, so the sign joins the word before it:
`normalize("DOOM™")` returns `"doomtm"`. `®` and `©` have no decomposition, so the step that turns every other
character into a space removes them: `normalize("Warframe®")` returns `"warframe"`.

[ADR-0004](../../adr/ADR-0004-installed-game-detection.md) lists trademark symbols among the differences
between launcher names and Twitch names, which must not keep a game from matching.

## What it does to detection

Each row is one call of `match_games([LocalGame(local, Platform.STEAM)], [twitch])`. The names are test inputs,
not names read from a launcher.

| Local name | Normalized | Twitch name | Result |
| --- | --- | --- | --- |
| `Warframe™` | `warframetm` | `Warframe` | no match |
| `DOOM™` | `doomtm` | `DOOM` | no match |
| `Call of Duty®: Black Ops 6™` | `call of duty black ops 6tm` | `Call of Duty: Black Ops 6` | `FUZZY`, ratio 0.960 |
| `Game℠` | `gamesm` | `Game` | no match |
| `ARK: Survival Evolved™` | `ark survival evolvedtm` | `ARK: Survival Evolved` | `FUZZY`, ratio 0.952 |
| `STAR WARS™ Battlefront™ II` | `star warstm battlefronttm ii` | `Star Wars: Battlefront II` | `FUZZY`, ratio 0.923 |
| `Warframe®` | `warframe` | `Warframe` | `EXACT` |

Why each step fails:

- The exact and variant steps compare whole strings, and `warframetm` is not `warframe`.
- The fuzzy step needs both names to have at least `FUZZY_MIN_LENGTH` (8) characters and a ratio of at least
  `FUZZY_THRESHOLD` (0.92). Two extra letters on a short name lower the ratio: `warframetm` against `warframe`
  gives 16/18, 0.889. `doomtm` is too short for the step.
- A long name still matches, but as `FUZZY`. The Detected Games list marks it with `≈`, and the match is dropped
  when a second Twitch name also reaches the threshold.

Effect on a user: a game with `™` or `℠` in its launcher name is not detected when the name is short, as
`Warframe™` and `DOOM™` are. Under "Priority list only", the default mode,
it is then not mined unless the user adds it to the Priority list. A longer name is detected, but marked `≈`
as if the match were uncertain.

## The Priority and Exclude patterns

The lists use the same `normalize`. `compile_pattern` in `gamelib/patterns.py` normalizes each literal piece of
an entry, and `matches`, `match_rank` and `any_match` normalize the game name. Calls:

- `matches(compile_pattern("Warframe"), "Warframe™")` returns False.
- `compile_pattern("Warframe™")` compiles to `warframetm`, which does not match the game `Warframe`.
- `matches(compile_pattern("Warframe*"), "Warframe™")` returns True.

On this side the names are Twitch game names and the entries the user types, so the case needs a `™` or `℠` in
one of them. The Priority and Exclude boxes offer the Twitch names for selection, so an entry typed or pasted
from a launcher is the likely source.

## What a fix involves

Replace `™` and `℠` with a space before the NFKD step. A space keeps `Wars™Battlefront` as two words, and the
last step removes the extra spaces. `®` and `©` already become separators. With `normalize` replaced by a version
that makes this replacement first, `match_games` returned `EXACT` for all seven rows of the table.

What the change can alter:

- Two Twitch names that differ only by the sign, such as `DOOM` and `DOOM™`, normalize to the same string.
  `_match_one` then finds two candidates and returns no match: the same check with a local `DOOM` and both
  Twitch names returned an empty list. A Priority entry `DOOM` would match both games.
- An entry written with the letters, such as `doomtm`, no longer matches a Twitch name `DOOM™`.
- A fuzzy match of a name with the sign becomes exact, so its `≈` mark goes away.
- No saved data changes. `detected_games` stores Twitch names, and entries are compiled at each use.

Cost: no Twitch requests. [Task 003](003-test-suite.md) names this case among the tests for `gamelib`.

How it came about: `normalize`, with NFKD and its docstring, came with installed game detection on 2026-08-24
(the commit "Implement automatic game detection"). It moved to `gamelib/matching.py` when `gamelib.py` was
split into a package on 2026-10-18.

## How it was closed

`normalize` turns `™` and `℠` into spaces before the NFKD step. A space keeps `Wars™Battlefront` as two words.
Over every Unicode code point, alone and between two letters, the new `normalize` differs from the old one only
at U+2120 and U+2122, so a name without either sign gives the same result as before. All seven rows of the table
above now give `EXACT`.

The same 307 labeled pairs of real names as the review in [033](033-fuzzy-match-ignores-i-v-x.md) gave 10 changed
results, all for names with `™` and all correct: 9 `FUZZY` matches became `EXACT`, and `Mortal Kombat X™`
against `Mortal Kombat X` went from no match to `EXACT`. Of 653,337 calls of `matches` with those names as
entries and as game names, 44 changed, all from False to True, each with a sign in the entry or the name. The
calls ran on Python 3.10.

The effects that "What a fix involves" lists are still accurate. Also, an entry `*™` now compiles to `.*` and covers every
game, as `*®` already did.

## History

- 2026-10-18: Opened while the docs were written. `match_games`, `normalize` and the pattern functions were
  called with names that contain `™`, `℠` and `®`.
- 2026-10-18: Three strict `xfail` tests in `tests/test_gamelib_matching.py` and `tests/test_gamelib_patterns.py`
  assert the correct behavior. They pass, and the strict mark then fails the suite, once this is fixed.
- 2026-10-19: Checked again before the fix. `_numbers` now reads the digits inside a word, so `6tm` counts as
  6 and the Call of Duty row is `FUZZY`. The table and the reasons are corrected.
- 2026-10-19: Closed. `normalize` turns `™` and `℠` into spaces before the NFKD step.
