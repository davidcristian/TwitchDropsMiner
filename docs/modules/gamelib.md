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
- `GameMatch(game_name, local, kind, ratio=1.0, local_count=1)`: `game_name` is the Twitch name as the campaigns
  write it. `ratio` is the similarity of a `FUZZY` match and 1.0 otherwise. `local_count` is the number of local
  games that matched `game_name`, and `local` is the strongest of them.
- `ScanResult`: `games`, `libraries` (the folders that were read) and `errors`, a list of `ScanError`.
- `ScanError(kind, path, reason="")`: a frozen dataclass for a problem with one folder. `kind` is a
  `ScanErrorKind`: `NOT_A_FOLDER`, `NO_GAMES` (neither scanner recognized the folder) or `FAILED` (a check of
  the folder raised an error). `path` is the folder as text, and `reason` is the text of the error of `FAILED`.
- `LauncherIndexes(manifests, legendary)` (`epic.py`): the Epic manifest folders and the Legendary and Heroic
  `installed.json` files that `scan_epic` reads for every added folder.

**Functions:**

| Function | Returns |
| --- | --- |
| `scan_directories(directories)` | A `ScanResult` for the given folders, without duplicates and sorted by name ([The scan](#the-scan)) |
| `scan_steam(directory, result)`, `scan_epic(directory, result, indexes=None)` | Whether the folder looked like that kind of install. Games are added to `result`. `indexes` defaults to `launcher_indexes` for the running platform |
| `launcher_indexes(platform, environ, home)` | The `LauncherIndexes` for a `sys.platform` value, an environment and a home folder ([Launcher indexes](#launcher-indexes)) |
| `normalize(name)` | The comparable form of a name ([Matching rules](#matching-rules)) |
| `match_games(local_games, game_names)` | One `GameMatch` for each Twitch name that a local game clearly matches, sorted by Twitch name ([Matching rules](#matching-rules)) |
| `compile_pattern(text)`, `compile_patterns(entries)` | A compiled list entry, or one per entry. `compile_pattern` keeps the 256 most recently used in an `lru_cache` |
| `matches(pattern, game_name)`, `any_match(patterns, game_name)` | Whether one entry, or any entry, covers the name |
| `match_rank(patterns, game_name)` | The index of the first entry that covers the name, or `None` |
| `matching_names(pattern, game_names)` | The covered names, sorted |
| `has_wildcard(text)` | Whether the text contains `*` or `?` |

## The scan

`scan_directories` expands `~` in each folder and adds a `NOT_A_FOLDER` error when it is not a folder. A
`~name` that names no user on Linux or macOS gives a `FAILED` error with the folder as written, and the other
folders are still scanned. It runs both scanners on every folder, because one folder can hold both kinds of
install, and adds a `NO_GAMES` error when neither recognizes it. A Legendary or Heroic index, or an Epic launcher
folder that holds a manifest, among the [launcher indexes](#launcher-indexes) makes the Epic scanner recognize
every folder, so that error does not appear then. A scanner can raise `OSError`, such as `PermissionError` for a
path inside a folder the user may not open. The scan of that folder then ends with a `FAILED` error, as for an
unknown user. The games found in it before the error are kept, and the other folders are still scanned. On
Python 3.14, `Path.is_dir` and `Path.is_file` return `False` there instead of raising, so such a folder gets a
`NO_GAMES` error. It then keeps the first game of each lower
case name and platform, and sorts by lower case name. A Steam library or an Epic manifest folder that is already
in `result.libraries` is not read again.

**Steam** (`steam.py`):

1. The added folder resolves to a `steamapps` folder: the folder itself when it holds `appmanifest_*.acf` files,
   its `steamapps` or `SteamApps` subfolder, or, for a `common` folder, its parent when the parent holds
   `libraryfolders.vdf`.
2. The library index is `steamapps/libraryfolders.vdf`, or `config/libraryfolders.vdf` next to `steamapps` in the
   older layout. For each `"path"` value in it, the `steamapps` folder under that path is another library when it
   exists. One added folder therefore covers the Steam libraries on other drives. A library that cannot be
   checked gets one `FAILED` error, and the other libraries are still read. On Python 3.14 it is skipped
   without an error.
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
   name itself, the name with the `ROMAN_NUMERALS` (`ii` to `xxxix`) written as digits, and the name without its
   trailing `EDITION_WORDS`, with and without the digits. `Dark Souls 3` matches `Dark Souls III`, and
   `Mafia: Definitive Edition` matches `Mafia`. `of`, `the`, `year` and `game` are edition words, so all of
   `Game of the Year Edition` is removed. `collection`, `remaster` and `remastered` are not edition words:
   Twitch usually lists a collection or a remaster under its full name, and the plain name is often another game.
   `Call of Duty: Modern Warfare Remastered` does not match `Call of Duty: Modern Warfare`, the 2019 game, and
   `Mega Man Legacy Collection` does not match `Mega Man`. `i`, `v` and `x` are not in `ROMAN_NUMERALS`,
   because a single letter is often part of a title (`Mega Man X`), so `Grand Theft Auto 5` is not a variant of
   `Grand Theft Auto V`. `ROMAN_NUMERALS` holds each number from 2 to 39 in its one correct form, so `iiii` and
   `xiix` stay words. A higher number needs `l`, `c`, `d` or `m`, and `xl`, `dc` and `mix` are words in titles,
   so `Mortal Kombat XL` is not a variant of `Mortal Kombat 40`.
3. **`FUZZY`**: only for normalized names of at least `FUZZY_MIN_LENGTH` (8) characters on both sides, and only
   when the numbers in both names are equal, in order: every run of digits, also inside a word (`lineage2`),
   the `ROMAN_NUMERALS` words, a lone `i`, `v` or `x` (`SINGLE_LETTER_NUMERALS`), and any other word of one
   letter, in any script, which counts as itself. The `difflib.SequenceMatcher` ratio must be at least
   `FUZZY_THRESHOLD` (0.92). The number rule keeps `Counter-Strike 2` from matching `Counter-Strike`, and
   `Grand Theft Auto V` from matching `Grand Theft Auto`. A lone letter often names another release of a series,
   so `NINJA GAIDEN Σ` does not match `Ninja Gaiden` or `NINJA GAIDEN Ω`, and `New Super Mario Bros. U` does not
   match `New Super Mario Bros.`. `Grand Theft Auto 5` and `Grand Theft Auto V` have the same numbers, so they
   pair as a fuzzy match. The same game written once with its lone numeral or letter and once without
   (`Mortal Kombat XL` and `Mortal Kombat X`, or `A Plague Tale: Innocence` and `Plague Tale: Innocence`) does
   not pair, which [ADR-0004](../adr/ADR-0004-installed-game-detection.md) accepts.

A local name that starts with a native title and ends with an English one, such as `原神 Genshin Impact`, is
also matched by its English title. The native title is the leading words that hold no letter `a` to `z` and no
digit. The English title is the rest: it must be written in `a` to `z` and digits only, with at least
`FUZZY_MIN_LENGTH` characters. Step 2 adds its variants to those of the whole name, so `原神 Genshin Impact`
matches `Genshin Impact` as `VARIANT`. Step 3 also compares it with each Twitch name written in `a` to `z` and
digits, so `雀魂麻將(MahjongSoul)` matches `Mahjong Soul` as `FUZZY`. Step 1 compares the whole name only. These
limits keep two games apart:

- Only a local name is read this way, because the app asks Twitch for English names. `仙剑奇侠传 Sword and Fairy`
  does not match a Twitch name `轩辕剑 Sword and Fairy`.
- A digit in the native title, or a numeral at the end of one of its words, can name a sequel that the English
  title leaves out, so `三國志14 Romance of the Three Kingdoms` and `仙剑奇侠传七 Sword and Fairy` keep their whole name.
  A numeral inside a word counts as a letter: `鬼谷八荒 Tale of Immortal` matches `Tale of Immortal`.
- Words of another script after the English title keep the whole name: `Escape from Tarkov: Арена` does not
  match `Escape from Tarkov`.

A native title that names another game than its English title, with no number, still matches that title. A
correct pair is missed when the sequel number is in both titles but the native title ends with it, as in
`天命奇御二 Fate Seeker II`.

A step that finds more than one Twitch name gives no match, and the next step is not tried. A fuzzy match is
also dropped when a second Twitch name reaches the threshold. For example, a local `Halo Infinite` gets no match
when the inventory has both `Halo Infinite` and `Halo: Infinite`. The GUI shows a match that is not `EXACT` with
`≈` before its name in the Detected Games list.

Two local games can match the same Twitch name, such as `Fortnite` from Steam and from Epic, or
`Grand Theft Auto V` and its Premium Edition. `match_games` returns that name once, with the strongest match:
`EXACT` before `VARIANT` before `FUZZY`, then the higher ratio, then the first in `local_games`. The Detected Games
list therefore shows each name once, with `≈` only when no local game matched it exactly. The line under the list
counts installed games on both sides: its first number adds up the `local_count` of each match, so `Fortnite` from
Steam and from Epic reads `2 of 2 installed games matched`.

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
| `Twitch.detect_games` (`twitch/`) | `scan_directories` through `asyncio.to_thread`, then `match_games` with the game of each campaign in the inventory | In `INVENTORY_FETCH` after `fetch_inventory`, and from `SettingsPanel.rescan_games`: the `Rescan` button and adding or removing a game folder |
| `Twitch._run`, state `GAMES_UPDATE` | `compile_patterns`, `match_rank`, `any_match` | Builds `wanted_games` from the Priority, Exclude and detected lists |
| `InventoryOverview._update_visibility` (`ui/inventorytab.py`) | `compile_patterns`, `any_match` | Decides whether a campaign is shown under the filters. Without the "Excluded" filter it applies the rule of `GAMES_UPDATE` to the Priority, Exclude and detected lists |
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
- The scan reads the file system and blocks, so callers in the event loop run it in a thread. A `DEBUG` record
  that it logs there reaches the Output box through the queue of `_TKOutputHandler` in `ui/output.py`
  ([ui.md](ui.md#log-records-in-the-output-box)).
- `appimage/AppImageBuilder.yml` copies and compiles `gamelib/` by name ([AGENTS.md](../../AGENTS.md#recipes)).
- gamelib builds no text that the user sees. `Twitch.detect_games` turns each `ScanError` into a line of the
  Output box with `_()`, from the key that `SCAN_ERROR_KEYS` in `twitch/` names for its kind.

**Dependencies.** The standard library only, including `unicodedata`, `difflib` and the `TwitchDrops` logger. No
repo module.
