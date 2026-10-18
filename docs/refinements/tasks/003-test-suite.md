# There is no test suite

**Status:** open
**Area:** repo checks
**Origin:** [AGENTS.md](../../../AGENTS.md#what-every-change-must-pass)
**Verified:** 2026-10-18

AGENTS.md says the repo has no test suite and that a pytest suite is welcome, starting with logic that needs
neither Twitch nor a display. Until then, each change to such logic is checked by calling it by hand with real
inputs, and nothing repeats that check on the next change.

## Candidates

- **`gamelib.patterns`**: `compile_pattern`, `match_rank`, `any_match` and `matching_names`. They decide which
  games the Priority and Exclude lists select. For example,
  `match_rank(compile_patterns(["Pokemon*", "Warframe"]), "Pokémon Scarlet")` returns `0`, and the same call
  with `"WARFRAME"` returns `1`.
- **`gamelib.matching`**: `normalize` and `match_games`, with `FUZZY_THRESHOLD` (0.92) and `FUZZY_MIN_LENGTH`
  (8). A test would have found this case: `normalize("Pokémon™ Legends: Arceus")` returns
  `"pokemontm legends arceus"`, because Unicode NFKD turns `™` into the letters `TM`. As a result
  `match_games` does not pair a local game named `Warframe™` with the Twitch game `Warframe`, although the
  docstring of `normalize` says trademark symbols must not matter
  ([009](009-trademark-symbols-in-game-names.md)).
- **The scanners**: `scan_steam` in `gamelib.steam` reads `libraryfolders.vdf` and `appmanifest_*.acf`, and
  `scan_epic` in `gamelib.epic` reads Epic `.item` manifests and the Legendary or Heroic `installed.json`. A
  test writes these files to a temporary folder. `_epic_manifest_dirs` and `_scan_legendary` also read fixed
  paths under `Path.home()` and in `C:/ProgramData/Epic/EpicGamesLauncher/Data/Manifests`. A test replaces
  `Path.home()` and runs where that ProgramData folder does not exist, or it reads the launcher files of the
  machine it runs on.
- **`utils`**: `chunk`, `deduplicate`, `ExponentialBackoff`, `Game.slug`, and `RateLimiter`, which enforces
  the 5 GQL requests per second of [ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md). A test of
  `RateLimiter` enters it six times within one window and asserts that the sixth waits.
- **Settings loading**: `json_load`, `json_save` and `merge_json` in `utils`, with `default_settings` from
  `settings`. `Settings.__init__` reads the fixed `SETTINGS_PATH`, so a test calls
  `json_load(path, default_settings)` with a temporary path. For example, a saved file with
  `"refresh_interval": "five"` and an unknown key loads back with `refresh_interval` set to 5, the unknown key
  removed, `exclude` as a `set` and `proxy` as a `URL`.
- **Logic inside `Twitch._run`**: the wanted games ranking in the `State.GAMES_UPDATE` branch and the channel
  order in the `State.CHANNELS_FETCH` branch need no I/O, but they cannot be called on their own. Moving them
  into functions ([005](005-modules-over-the-line-cap.md)) makes them testable, and
  [001](001-offline-acl-channels-trimmed-first.md) is a defect in the second one.

## Cost

- **The runner.** AGENTS.md names pytest, and item 5 of the same section allows a new dependency only when the
  standard library cannot do the job. `unittest` needs nothing. pytest is a development dependency, kept in
  its own file such as `requirements-dev.txt`, because `requirements.txt` is installed into every build. The
  task includes stating that choice.
- **Imports.** `gamelib` imports only the standard library, so its tests need no install. `utils` imports
  `tkinter`, `PIL.ImageTk` and `yarl` when it loads, so tests of `utils` and `settings` need
  `requirements.txt` installed and a Python with `tkinter`, but no display.
- **Location.** The tests go in a folder such as `tests/`. `appimage/AppImageBuilder.yml` copies every
  top-level `*.py` file into the AppImage, so a top-level test file would ship. The `py_compile` command in
  AGENTS.md covers `*.py gamelib/*.py` only, so the folder is added to it.
- **CI.** A job or a step in `.github/workflows/ci.yml` runs the suite on Python 3.10, the `PYTHON_VERSION`
  there. AGENTS.md's "What every change must pass" section then names the command.
- **Twitch requests:** none.

## History

- 2026-10-18: Opened. Found while the docs were written, from the AGENTS.md line that welcomes a pytest suite.
  Calling `match_games` with real names while listing the candidates found the `™` case.
