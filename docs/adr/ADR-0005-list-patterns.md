# ADR-0005: Priority and Exclude list patterns

**Status:** Accepted (2026-08-25)

## Context

The Priority list sets which games the app mines and in what order, and the Exclude list names games it must
never mine. Each entry is compared with the Twitch game names of the fetched campaigns. Twitch writes those
names with accents, apostrophes and other punctuation, as in `Pokémon` or `Tom Clancy's Rainbow Six Siege`,
which users type differently. A series such as Pokémon is many Twitch games, one per title, and an entry that
names a single game has to be repeated for each title.

With patterns and installed game detection ([ADR-0004](ADR-0004-installed-game-detection.md)) both deciding
what is mined, the lists alone do not show the result. The user needs to see which games the app will mine,
in which order, and which entry put each one there.

## Decision

1. **Entries and game names are compared after one normalization.** `gamelib.normalize` removes case, accents
   and apostrophes, writes `&` as `and`, and turns other punctuation into spaces. It is the same function that
   installed game detection uses. `compile_pattern` normalizes each literal piece of an entry, and `matches`
   normalizes the game name, so `Pokemon` matches `Pokémon` and `Tom Clancys Rainbow Six Siege` matches
   `Tom Clancy's Rainbow Six Siege`.

2. **`*` and `?` are wildcards, and the only special characters.** `*` matches any run of characters,
   including none, and `?` matches one character of the normalized name. One `Pokemon*` entry covers a whole
   series.

3. **A match is anchored at both ends.** `matches` uses `fullmatch`, so an entry without a wildcard covers
   one game only: `Rust` never matches `Rust Console Edition`.

4. **The first matching Priority entry sets the rank.** `gamelib.match_rank` returns the index of the first
   entry that matches. When an entry for one game is placed above a wildcard that also matches that game, the
   game gets the higher rank of the two. The Exclude list has no order (it is stored as a set), and any
   matching entry excludes the game (`gamelib.any_match`).

5. **Ranks are computed once per game.** `State.GAMES_UPDATE` in `Twitch._run` stores each game's rank in
   `priority_order`, then sorts and filters the campaigns by the stored rank. A game with several campaigns is
   matched once, because matching a pattern costs more than a dictionary lookup. `compile_pattern` keeps up to
   256 compiled entries in an `lru_cache`.

6. **Adding a wildcard entry reports what it matches.** `SettingsPanel._report_pattern`, called from
   `priority_add` and `exclude_add`, prints `"<entry>" matches <count> game(s): <names>` in the Output box, or
   `"<entry>" doesn't match any game with a campaign right now.` It matches against the game names of every
   campaign fetched since the app started (`_game_names`). An entry without a wildcard is not reported,
   because what it matches is already clear. Without the report, the user cannot tell whether a wildcard
   matches anything.

7. **The Games Being Mined table shows the result.** `SettingsPanel.set_wanted_games`, called at the end of
   `State.GAMES_UPDATE`, lists `wanted_games` in the order the app picks them, with the columns `#`, `Game`
   and `Matched by`. `Matched by` names the Priority entry that set the game's rank, or shows `installed` for
   a detected game, or `not on any list` when the Priority mode mines games on neither list. The column names
   only the first matching entry, so when a Priority entry never appears in it, no game is mined because of
   it. The table is filled where the games to mine are computed, so it shows the result of the last
   computation, not the lists as they are being edited.

## Consequences

- Every place that reads the lists calls the same `gamelib` functions: the games to mine in `Twitch._run`,
  the Games Being Mined table, and the campaign filter of the Inventory tab
  (`InventoryOverview._update_visibility`). They cannot disagree on what an entry matches. The Inventory filter
  does not count detected games, so under "Priority list only" it hides the campaigns of a detected game that the
  app mines ([018](../refinements/tasks/018-inventory-tab-hides-detected-games.md)).
- Entries are saved as typed, in the `priority` and `exclude` settings, and compiled at each use. An entry
  that is a game's exact name matches that game, unless the name contains a wildcard character.
- Matching is local and adds no request to Twitch. A list edit takes effect at the next
  `State.GAMES_UPDATE`, which every reload runs, including the one the `Reload` button starts.
- Each literal piece is normalized on its own, which removes the spaces at its ends. A space next to a
  wildcard is therefore dropped: `Battlefield ?` compiles to `battlefield.` and does not match
  `Battlefield 6`, while `Battlefield*` does.
- A game name that contains `*` or `?` is read as a pattern. The entry `Who's Your Daddy?!` compiles to
  `whos\ your\ daddy.` and does not match the game of that name; the entry `Whos Your Daddy` does.

## Alternatives rejected

- **Substring matching.** `Rust` would also match `Rust Console Edition`, so an entry without a wildcard could
  not name one game.
- **Exact text comparison.** The user would have to type the exact name Twitch uses, and add one entry per
  game of a series.

## Related

- [gamelib.md](../modules/gamelib.md) (`gamelib/patterns.py`, `normalize` in `gamelib/matching.py`),
  [twitch.md](../modules/twitch.md), [gui.md](../modules/gui.md).
- [ADR-0004](ADR-0004-installed-game-detection.md) (detected games and their rank).
- [Priority and Exclude lists](../troubleshooting.md#priority-and-exclude-lists), for users.
- [Test suite](../refinements/tasks/003-test-suite.md),
  [translations for new strings](../refinements/tasks/008-translations-for-new-strings.md).
