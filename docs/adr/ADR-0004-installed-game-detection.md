# ADR-0004: Installed game detection

**Status:** Accepted (2026-10-20)

## Context

The app mines the games on the Priority list, and the user types each entry by hand. A user who wants drops
for every game they have installed has to add each one, and add new ones as campaigns start.

The Steam and Epic launchers already list the installed games in their own index files. The names in those
files rarely match the names Twitch uses: case, accents, apostrophes, trademark symbols, roman numerals and
edition words such as "Deluxe" differ. A wrong match is expensive, because the app then spends mining time on
a game the user never chose. A missed match costs little, because the user can still add the game by hand.

## Decision

1. **Detection adds games and does not filter.** Detected games are mined in addition to the Priority list.
   In `State.GAMES_UPDATE` (`Twitch._run`), a game that matches a Priority entry gets that entry's index as its
   rank. A detected game that matches no entry gets `len(priority)` plus its index in `detected_games`, which
   is sorted by name. Every detected game therefore ranks below every Priority entry, so an explicit choice
   always comes first. Under "Priority list only" (`PriorityMode.PRIORITY_ONLY`) any rank below `MAX_INT`
   counts as wanted, so a detected game is mined even when no Priority entry matches it.

2. **The scan follows the launcher's own index.** `gamelib.scan_directories` reads each folder in the
   `game_dirs` setting as both a Steam and an Epic install, so the user never says which launcher it is.
   - Steam (`scan_steam`): the folder can be the Steam root or a `steamapps` folder, or `steamapps/common`
     when its `steamapps` holds `libraryfolders.vdf`.
     `_steam_library_index` reads `libraryfolders.vdf` and adds every library it lists, so one folder finds
     the libraries on other drives. Each `appmanifest_*.acf` gives a name and an AppID. Entries in
     `STEAM_TOOL_APPIDS`, or whose name starts with one of `STEAM_TOOL_PREFIXES`, are runtimes, Proton
     builds or redistributables, and are skipped.
   - Epic (`scan_epic`): the `.item` manifests in the folder, in its `Manifests` subfolder and in the
     launcher's fixed manifests folder. DLC (`MainGameAppName` differs from `AppName`) and incomplete
     installs (`bIsIncompleteInstall`) are skipped. `_scan_legendary` reads the `installed.json` of Legendary
     and Heroic, the usual way Epic games are installed on Linux.

   The index finds the libraries on other drives from one folder, and gives each game its display name and its
   ID. The scan skips Steam tool entries by AppID first, because a test on the ID is exact.

3. **The Detected Games list cannot be edited by hand.** It shows `detected_games`, which only
   `Twitch.detect_games` writes, and it has no add or remove buttons. The Exclude list is the way to override a
   bad match: `State.GAMES_UPDATE` checks it as a separate condition (`gamelib.any_match` over the Exclude
   patterns), so an excluded game is never mined, whatever else matches it. A game that detection misses is
   added to the Priority list by hand. Every scan with a new result rewrites `detected_games`, so a hand edit
   would not last.

4. **Only high-confidence matches are kept.** `gamelib.match_games` pairs installed games only with the
   Twitch games that have a campaign in the inventory. `_match_one` tries three steps in order, and returns no
   match at any step that finds more than one candidate:
   - exact (`MatchKind.EXACT`): equal after `normalize`, which removes case, accents and apostrophes, writes
     `&` as `and` and turns the `™` and `℠` signs and other punctuation into spaces, keeping the letters and
     digits of every script;
   - variant (`MatchKind.VARIANT`): equal after the roman numerals in `ROMAN_NUMERALS` become digits or the
     trailing `EDITION_WORDS` are removed, on either side. `collection`, `remaster` and `remastered` are not
     edition words;
   - fuzzy (`MatchKind.FUZZY`): a `difflib.SequenceMatcher` ratio of at least `FUZZY_THRESHOLD` (0.92), both
     normalized names at least `FUZZY_MIN_LENGTH` (8) characters long, the same numbers on both sides (each
     run of digits, also inside a word, and the roman numerals), and no second Twitch name also at or above
     the threshold. A lone `i`, `v` or `x` counts as a number here and nowhere else, since a single letter is
     often part of a title.

   The numeric token check separates a sequel from its prequel: an installed `Counter-Strike 2` gets no match
   against a campaign for `Counter-Strike`, and `Grand Theft Auto V` none against `Grand Theft Auto`. The Detected
   Games list marks a variant or fuzzy match with `≈`, so a wrong one is easy to find.

   An edition word is removed because Twitch usually lists a re-release such as a Game of the Year Edition
   under the plain name. A collection or a remaster is usually listed under its full name, and its plain name
   is often another game: `Call of Duty: Modern Warfare` is the 2019 game, not `Modern Warfare Remastered`,
   and `Star Wars: Battlefront` is not `Star Wars: Battlefront Classic Collection`.

5. **Standard library only.** Steam's KeyValues files (`.vdf`, `.acf`) are read with one regular expression
   for flat `"key" "value"` pairs (`_KV_PATTERN` in `gamelib/steam.py`), because every field the scan needs is
   such a pair. Epic manifests and `installed.json` are JSON. Matching uses `unicodedata` and `difflib`.
   AGENTS.md allows a new dependency only when the standard library cannot do the job.

6. **The scan runs on every reload and on demand.** `Twitch.detect_games` runs in `State.INVENTORY_FETCH`
   right after `fetch_inventory`, from the `Rescan` button (`SettingsPanel.rescan_games`), and after a folder
   is added or removed. The file reads run in a worker thread (`asyncio.to_thread`), so they do not block the
   event loop, and a second scan is skipped while one runs (`_scanning_games`). When the result differs from
   the stored `detected_games`, the method stores it and enters `State.GAMES_UPDATE`, so a newly detected game
   is mined at once instead of at the next hourly reload.

## Consequences

- A lone `I`, `V` or `X` that is part of a title or an edition blocks a fuzzy match, so the same game written
  with and without it is not paired: `Mortal Kombat XL` against `Mortal Kombat X`, or
  `The Elder Scrolls V: Skyrim` against `The Elder Scrolls: Skyrim`. Such a game can be added to the Priority
  list by hand, while a sequel paired with its original would mine a game the user did not choose.
- The other edition words can still pair a re-release with a different game of the same plain name. `classic`
  and `legacy` stay edition words, so a name that ends in one of them alone still matches the name without
  it. Only `collection`, `remaster` and `remastered` are left out, so every other edition match still pairs.
  A wrong match shows with `≈`, and the Exclude list overrides it.
- The scan reads local files only and sends no request to Twitch. A changed result enters
  `State.GAMES_UPDATE`, not `State.INVENTORY_FETCH`, so a `Rescan` never causes a full reload
  ([ADR-0002](ADR-0002-twitch-traffic-budget.md)). It does fetch the channels again: one `GameDirectory`
  request for each game to mine that has a campaign without a channel list, and one batched request for each
  20 channels on the campaigns' channel lists (`bulk_check_online`).
- A game can be detected only while a campaign for it is in the inventory. The Detected Games list changes
  as campaigns enter and leave the inventory.
- `detected_games` is saved in `settings.json`, so the Settings tab shows the last result at startup, before
  the first scan ends. Only the names are saved, so the `≈` mark appears only after a new scan.
- With no folder in `game_dirs`, `detect_games` clears `detected_games`, and enters `State.GAMES_UPDATE` when
  the list was not empty.
- A folder problem is printed in the Output box as `Game scan: ...` by the first scan that finds it, and not
  again while each later scan finds it too.
- Under "Priority list only", an installed game whose name the matcher cannot pair with certainty is not mined
  until the user adds it to the Priority list.

## Alternatives rejected

- **Mine only the Priority games that are installed.** Detection exists so the user does not add each
  installed game by hand.
- **A Detected Games list the user can edit.** The Exclude list already overrides any match, and the next scan
  would rewrite the edit.
- **Guess the closest name for an ambiguous match, or match fuzzily without the number check.** A sequel and
  its prequel score above `FUZZY_THRESHOLD`: `counter strike 2` and `counter strike` have a ratio of 0.93.
- **A KeyValues parsing package.** The fields the scan needs are flat pairs that one regular expression reads.

## Related

- [gamelib.md](../modules/gamelib.md), [twitch.md](../modules/twitch.md), [gui.md](../modules/gui.md),
  [settings.md](../modules/settings.md).
- [ADR-0002](ADR-0002-twitch-traffic-budget.md) (the request budget),
  [ADR-0005](ADR-0005-list-patterns.md) (list entries use the same `normalize`).
- [Installed games are not detected](../troubleshooting.md#installed-games-are-not-detected), for users.
- [Test suite](../refinements/tasks/003-test-suite.md),
  [translations for new strings](../refinements/tasks/008-translations-for-new-strings.md).
