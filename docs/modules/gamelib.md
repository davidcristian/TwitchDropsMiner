# `gamelib/`

**Purpose.** Finds the games installed through Steam, the Epic Games Launcher, Legendary and Heroic, pairs them
with the Twitch games that have campaigns, and matches game names against the Priority and Exclude list entries.
It reads files and compares strings. It sends no request to Twitch, needs no display and imports no other repo
module, so it can be called and tested on its own. [ADR-0004](../adr/ADR-0004-installed-game-detection.md)
explains the detection design and [ADR-0005](../adr/ADR-0005-list-patterns.md) the list patterns.

## Modules

| Module | What it holds |
| --- | --- |
| `__init__.py` | Re-exports the public names listed in `__all__`. Callers import from `gamelib`, never from a submodule |
| `common.py` | The shared types and `read_text`, which returns a file's text or `None` (logged at `DEBUG`) when it cannot be read |
| `steam.py` | `scan_steam`, `STEAM_TOOL_APPIDS`, `STEAM_TOOL_PREFIXES` |
| `epic.py` | `scan_epic`, for Epic manifests and the Legendary and Heroic index, and `launcher_indexes` with its `LauncherIndexes` |
| `scan.py` | `scan_directories`, which runs both scanners on each folder |
| `matching.py` | `normalize`, `match_games`, `EDITION_WORDS`, `ROMAN_NUMERALS`, `SINGLE_LETTER_NUMERALS`, `FUZZY_THRESHOLD`, `FUZZY_MIN_LENGTH` |
| `patterns.py` | `compile_pattern`, `compile_patterns`, `matches`, `match_rank`, `any_match`, `matching_names`, `has_wildcard` |

## Public contract

**Types** (`common.py`):

- `Platform`: `STEAM`, `EPIC`. `str()` gives `Steam` or `Epic`.
- `MatchKind`: `EXACT`, `VARIANT`, `FUZZY`, strongest first.
- `LocalGame(name, platform, path=None, app_id="")`: a frozen dataclass for one installed game.
- `GameMatch(game_name, local, kind, ratio=1.0)`: `game_name` is the Twitch name as the campaigns write it.
  `ratio` is the similarity of a `FUZZY` match and 1.0 otherwise.
- `ScanResult`: `games`, `libraries` (the folders that were read) and `errors` (English text lines).
- `LauncherIndexes(manifests, legendary)` (`epic.py`): the Epic manifest folders and the Legendary and Heroic
  `installed.json` files that `scan_epic` reads for every added folder.

**Functions:**

| Function | Returns |
| --- | --- |
| `scan_directories(directories)` | A `ScanResult` for the given folders, without duplicates and sorted by name ([The scan](#the-scan)) |
| `scan_steam(directory, result)`, `scan_epic(directory, result, indexes=None)` | Whether the folder looked like that kind of install. Games are added to `result`. `indexes` defaults to `launcher_indexes` for the running platform |
| `launcher_indexes(platform, environ, home)` | The `LauncherIndexes` for a `sys.platform` value, an environment and a home folder ([Launcher indexes](#launcher-indexes)) |
| `normalize(name)` | The comparable form of a name ([Matching rules](#matching-rules)) |
| `match_games(local_games, game_names)` | A `GameMatch` for each local game with one clear Twitch match, sorted by Twitch name |
| `compile_pattern(text)`, `compile_patterns(entries)` | A compiled list entry, or one per entry. `compile_pattern` keeps the 256 most recently used in an `lru_cache` |
| `matches(pattern, game_name)`, `any_match(patterns, game_name)` | Whether one entry, or any entry, covers the name |
| `match_rank(patterns, game_name)` | The index of the first entry that covers the name, or `None` |
| `matching_names(pattern, game_names)` | The covered names, sorted |
| `has_wildcard(text)` | Whether the text contains `*` or `?` |

## The scan

`scan_directories` expands `~` in each folder and adds the error line `Not a directory: ...` when it is not a
folder. A `~name` that names no user on Linux or macOS gives the line `<folder as written>: <reason>`, and the
other folders are still scanned. It runs both scanners on every folder, because one folder can hold both kinds
of install, and adds `No Steam or Epic games found in: ...` when neither recognizes it. A Legendary or Heroic
index, or an Epic launcher folder that holds a manifest, among the [launcher indexes](#launcher-indexes) makes the
Epic scanner recognize every folder, so the line does not appear then. A scanner can raise `OSError`, such as
`PermissionError` for a path inside a folder the user may not open. The scan of that folder then ends with the
line `<folder>: <reason>`, as for an unknown user. The games found in it before the error are kept, and the other
folders are still scanned. On Python 3.14, `Path.is_dir` and `Path.is_file` return `False` there instead of
raising, so such a folder gets `No Steam or Epic games found in: ...`. It then keeps the first game of each lower
case name and platform, and sorts by lower case name. A Steam library or an Epic manifest folder that is already
in `result.libraries` is not read again.

**Steam** (`steam.py`):

1. The added folder resolves to a `steamapps` folder: the folder itself when it holds `appmanifest_*.acf` files,
   its `steamapps` or `SteamApps` subfolder, or, for a `common` folder, its parent when the parent holds
   `libraryfolders.vdf`.
2. The library index is `steamapps/libraryfolders.vdf`, or `config/libraryfolders.vdf` next to `steamapps` in the
   older layout. For each `"path"` value in it, the `steamapps` folder under that path is another library when it
   exists. One added folder therefore covers the Steam libraries on other drives. A library that cannot be
   checked gets the line `<library>: <reason>` once, and the other libraries are still read. On Python 3.14 it
   is skipped without a line.
3. Each `appmanifest_*.acf` gives `name`, `appid` and `installdir`. The parser reads only flat `"key" "value"`
   pairs with a regular expression, and the first value of a key is used. Steam writes a quote and a backslash
   inside a quoted string as `\"` and `\\`. The parser reads these two, and `\n` and `\t` as a line break and a
   tab. Any other backslash pair is kept as written.
4. An entry is skipped when its `name` is empty, when its `appid` is in `STEAM_TOOL_APPIDS` (Steamworks Common
   Redistributables, Steam Linux Runtime 1.0, 2.0 and 3.0, Proton Experimental, Proton Hotfix, Proton 9.0), or
   when its lower case name starts with one of `STEAM_TOOL_PREFIXES`: `proton`, `steam linux runtime`,
   `steamworks common`.

**Epic Games Launcher** (`epic.py`): the manifests are the `*.item` JSON files in the added folder, in its
`Manifests` subfolder, and in the launcher's own folders that `launcher_indexes` lists. The launcher's folders
are read whatever folder was added.
Each manifest gives `DisplayName`, `AppName` and `InstallLocation`. A field that is not a string, such as `null`,
counts as missing, here and in the Legendary index. A manifest is skipped when it is not valid JSON (logged at
`DEBUG`), is not an object, has an empty `DisplayName`, belongs to an add-on (`MainGameAppName` is set and differs
from `AppName`), or has `bIsIncompleteInstall` set.

**Legendary and Heroic** (`epic.py`): `installed.json` in the added folder and each Legendary or Heroic index
that `launcher_indexes` lists are read when they exist, for every added folder. Each key is an app name and each
entry gives `title` and `install_path`. An entry is skipped when it is not an object, has an empty `title`, or
has `is_dlc` set to `true`, which Legendary writes for an installed DLC (`InstalledGame` in Legendary's
`legendary/models/game.py`).

## Launcher indexes

`launcher_indexes(platform, environ, home)` is the one function in `gamelib` that checks the platform. It takes a
`sys.platform` value (`win32`, `darwin`, and any other value counts as Linux), an environment and a home folder.
`scan_epic` passes `sys.platform`, `os.environ` and `Path.home()`, and a test passes fakes. Every listed index that
exists is read, not only the one that a launcher would choose, because the app can run with another environment
than the launcher. An empty environment variable counts as unset. An index listed twice, as when
`XDG_CONFIG_HOME` is `~/.config`, is read once.

| Epic Games Launcher manifests folder | Platform | Source |
| --- | --- | --- |
| `%PROGRAMDATA%/Epic/EpicGamesLauncher/Data/Manifests`, in `C:/ProgramData` when `PROGRAMDATA` is unset | Windows | The launcher's own folder, which Legendary's `egl-sync` also reads (`EPCLFS` in `legendary/lfs/egl.py`) |
| `~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests` | macOS | The launcher's own folder on macOS (unconfirmed) |
| `~/.config/Epic/EpicGamesLauncher/Data/Manifests` | all | No known launcher (unconfirmed). A folder without manifests costs one check |

| Folder of a Legendary or Heroic `installed.json` | Platform | Source |
| --- | --- | --- |
| `$LEGENDARY_CONFIG_PATH`, `$XDG_CONFIG_HOME/legendary`, `~/.config/legendary` | all | `LGDLFS` in Legendary's `legendary/lfs/lgndry.py`, which uses the first of these that is set |
| `heroic/legendaryConfig/legendary` in `~/.config` | all | Heroic's own Legendary folder (`legendaryConfigPath` in Heroic's `src/backend/constants.ts`) is in Electron's `appData` folder, which is `$XDG_CONFIG_HOME` or `~/.config` on Linux (Electron's `app.getPath` docs). Heroic does not use `~/.config` on Windows or macOS |
| `heroic/legendaryConfig/legendary` in `$XDG_CONFIG_HOME` | Linux | The same |
| `heroic/legendaryConfig/legendary` in `~/.var/app/com.heroicgameslauncher.hgl/config` | Linux | Heroic as a Flatpak from Flathub, app ID `com.heroicgameslauncher.hgl`. Flatpak sets `XDG_CONFIG_HOME` to `~/.var/app/<app ID>/config` |
| `heroic/legendaryConfig/legendary` in `~/Library/Application Support` | macOS | Electron's `appData` folder on macOS (unconfirmed) |
| `heroic/legendaryConfig/legendary` in `%APPDATA%` | Windows | Electron's `appData` folder on Windows (unconfirmed) |

No path was checked against a real install. A path marked (unconfirmed) is not stated in the launcher's own code
or documentation: it follows from the launcher's folder layout, or has no known source.

## Matching rules

`normalize` turns a name into case-folded words of letters and digits, in any script, separated by single
spaces:

1. `™` and `℠` become spaces. NFKD would write them as the letters `TM` and `SM`, which would join the word
   before them.
2. Apostrophes (`'`, `’`, `ʼ`, `ʻ`, `´`) are removed without a gap: `Clancy's` becomes `clancys`.
3. NFKD decomposition, then the accents of Latin and Greek letters are removed: `Pokémon` becomes `pokemon`. The
   marks of other scripts are parts of their letters (the breve of `й`, the dakuten of `ガ`), so they stay, and
   NFC joins them back, which also joins Hangul syllables.
4. Case folding (`str.casefold`), which writes `ß` as `ss`. The Latin letters that have no accent to remove
   (`æ`, `œ`, `ø`, `ł`, `đ`, `ð`, `þ`, `ħ`, `ı`) are written as `ae`, `oe`, `o`, `l`, `d`, `d`, `th`, `h`, `i`
   (`LATIN_LETTERS`). `&` becomes `and`.
5. Every other run of characters that are not letters, digits or marks becomes one space, and the ends are
   trimmed.

So `Tom Clancy's Rainbow Six: Siege` becomes `tom clancys rainbow six siege`, `STAR WARS™ Battlefront™ II`
becomes `star wars battlefront ii`, `Łódź` becomes `lodz`, and `Мир Танков` becomes `мир танков`.

`match_games` compares each local game with the names of the games in the inventory. The first step that finds
a candidate decides:

1. **`EXACT`**: the normalized names are equal.
2. **`VARIANT`**: a variant of the local name equals a variant of a Twitch name. The variants of a name are the
   name itself, the name with the `ROMAN_NUMERALS` (`ii` to `xv`) written as digits, and the name without its
   trailing `EDITION_WORDS`, with and without the digits. `Dark Souls 3` matches `Dark Souls III`, and
   `Mafia: Definitive Edition` matches `Mafia`. `of`, `the`, `year` and `game` are edition words, so all of
   `Game of the Year Edition` is removed. `collection`, `remaster` and `remastered` are not edition words:
   Twitch usually lists a collection or a remaster under its full name, and the plain name is often another game.
   `Call of Duty: Modern Warfare Remastered` does not match `Call of Duty: Modern Warfare`, the 2019 game, and
   `Mega Man Legacy Collection` does not match `Mega Man`. `i`, `v` and `x` are not in `ROMAN_NUMERALS`,
   because a single letter is often part of a title (`Mega Man X`), so `Grand Theft Auto 5` is not a variant of
   `Grand Theft Auto V`.
3. **`FUZZY`**: only for normalized names of at least `FUZZY_MIN_LENGTH` (8) characters on both sides, and only
   when the numbers in both names are equal, in order: every run of digits, also inside a word (`lineage2`),
   the `ROMAN_NUMERALS` words, and a lone `i`, `v` or `x` (`SINGLE_LETTER_NUMERALS`). The
   `difflib.SequenceMatcher` ratio must be at least `FUZZY_THRESHOLD` (0.92). The number rule keeps
   `Counter-Strike 2` from matching `Counter-Strike`, and `Grand Theft Auto V` from matching `Grand Theft Auto`.
   `Grand Theft Auto 5` and `Grand Theft Auto V` have the same numbers, so they pair as a fuzzy match. The same
   game written once with its lone numeral and once without (`Mortal Kombat XL` and `Mortal Kombat X`) does not
   pair, which [ADR-0004](../adr/ADR-0004-installed-game-detection.md) accepts.

A step that finds more than one Twitch name gives no match, and the next step is not tried. A fuzzy match is
also dropped when a second Twitch name reaches the threshold. For example, a local `Halo Infinite` gets no match
when the inventory has both `Halo Infinite` and `Halo: Infinite`. The GUI shows a match that is not `EXACT` with
`≈` before its name in the Detected Games list.

## Patterns

`compile_pattern` splits an entry at each `*` and `?`. `*` becomes `.*`, `?` becomes `.`, and each other piece is
passed through `normalize` and `re.escape`. Wildcards with no text between them, or only text that `normalize`
removes such as an apostrophe, become one `.` per `?` and then one `.*` if the run has a `*`: `Halo*?*` becomes
`halo..*`. One `.*` matches the same names as several in a row, but with several a failed match tests every way
to split the name between them, and ten `*` take minutes for one name. `matches` compares the pattern with the
whole normalized game name (`fullmatch`). [troubleshooting.md](../troubleshooting.md#priority-and-exclude-lists) shows the rules from the
user's side.

- Case, accents, punctuation and the `™`, `℠` and `®` signs do not count, and `&` matches `and`:
  `Ratchet and Clank` matches `Ratchet & Clank`, and `Warframe` matches `Warframe™`.
- An entry without a wildcard matches one game: `Rust` does not match `Rust Console Edition`, but `Rust*` does.
- `*` also matches nothing, so `Call of Duty*` matches `Call of Duty`.
- Spaces and punctuation at an end of a piece that is next to a wildcard become one space, as `normalize`
  writes them in a game name. `Battlefield ?` becomes `battlefield\ .` and matches `Battlefield 6`, and
  `Half-Life:?` matches `Half-Life 2`. The space then has to be in the name: `Call *` does not match
  `Callisto Protocol`, and `Call of Duty *` does not match `Call of Duty`. Spaces at the start and end of the
  entry do not count.
- An apostrophe next to a wildcard is dropped without a space, as in a game name: `*'s Creed` matches
  `Assassin's Creed`, but `Assassin?s Creed` does not.
- In the Priority list, a game takes the rank of the first entry that covers it, so a specific entry above a
  wildcard decides that game's rank.

## Callers

| Caller | Calls | When |
| --- | --- | --- |
| `Twitch.detect_games` (`twitch.py`) | `scan_directories` through `asyncio.to_thread`, then `match_games` with the game of each campaign in the inventory | In `INVENTORY_FETCH` after `fetch_inventory`, and from `SettingsPanel.rescan_games`: the `Rescan` button and adding or removing a game folder |
| `Twitch._run`, state `GAMES_UPDATE` | `compile_patterns`, `match_rank`, `any_match` | Builds `wanted_games` from the Priority, Exclude and detected lists |
| `InventoryOverview._update_visibility` (`gui.py`) | `compile_patterns`, `any_match` | Decides whether a campaign is shown under the filters. It ignores the detected games ([task 018](../refinements/tasks/018-inventory-tab-hides-detected-games.md)) |
| `SettingsPanel.set_wanted_games` | `compile_patterns`, `match_rank` | Names the Priority entry that matched each game in the Games Being Mined table |
| `SettingsPanel.set_detected` | `GameMatch`, `MatchKind` | Fills the Detected Games list |
| `SettingsPanel._report_pattern` | `has_wildcard`, `compile_pattern`, `matching_names` | After `priority_add` or `exclude_add`, prints the games a wildcard entry covers |

`detect_games` stores the matched Twitch names in the `detected_games` setting and changes to `GAMES_UPDATE` when
the list changed. Only the names are stored, so after a restart every restored name shows without `≈` until the
next scan.

## Invariants

- Standard library only, and no import of another repo module, so the package runs without Twitch, a display or
  the third-party packages.
- `match_games` returns only clear matches, because a wrong match mines a game the user did not choose, while a
  missed game can be added to the Priority list by hand ([ADR-0004](../adr/ADR-0004-installed-game-detection.md)).
- Patterns and matching use the same `normalize`, so a list entry and a detected name compare the same way.
- The scan reads the file system and blocks, so callers in the event loop run it in a thread. At the `DEBUG`
  logging level, a record it logs then goes to `_TKOutputHandler` in `gui.py` on that thread, whose Tk call
  raises `RuntimeError` and ends the scan ([task 021](../refinements/tasks/021-scan-thread-logs-into-tk.md)).
- `appimage/AppImageBuilder.yml` copies and compiles `gamelib/` by name ([AGENTS.md](../../AGENTS.md#recipes)).
- The scan error lines are English text built in `scan.py`. The GUI prints them inside the translated
  `Game scan: {error}` line, so they are not translated.

**Dependencies.** The standard library only, including `unicodedata`, `difflib` and the `TwitchDrops` logger. No
repo module.
