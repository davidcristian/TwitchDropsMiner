# ADR-0020: How a module over the line cap is split

**Status:** Accepted (2026-10-23)

## Context

AGENTS.md allows 300 lines per module, and `scripts/linecap.py` names the inherited modules over the limit as
exceptions ([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)). On 2026-10-23 they were `gui.py`
(3164 lines), `twitch.py` (1734), `translate.py` (612), `channel.py` (528), `inventory.py` (489), `constants.py`
(477), `websocket.py` (414) and `utils.py` (371). Split along the points that task 005 gives, they become more
than 30 modules.

The module map in AGENTS.md has one row for each top-level module and package, and `scripts/rostercheck.py` fails
when one lacks its row or its doc in `docs/modules/`. AGENTS.md has 277 of its 300 lines, so 30 new rows do not
fit. `gamelib/` already has the other form: one row, one doc, several files, and an `__init__.py` that imports
the public names, so that callers import from `gamelib`.

Five classes are over 300 lines by themselves: `Twitch` (1421), `SettingsPanel` (725), `GUIManager` (521),
`Channel` (358) and `Websocket` (300). Two methods are too: `SettingsPanel.__init__` (383) and `Twitch._run`
(356). The methods read and set many attributes of `self`.

Two modules depend on their own file. `constants.py` sets `SELF_PATH` to `main.py` in its own folder when
`sys.argv[0]` is `gui.py` or `pyinstaller`, and sets `IS_APPIMAGE` only when its own file is inside `APPDIR`.
`tests/test_constants.py` copies the file to other folders to check both. `python gui.py` opens the GUI with
mock data and no login. AGENTS.md, [building.md](../building.md#preview-the-gui) and the
[headless runbook](../runbooks/gui-preview-headless.md) name that command, and a folder `gui/` and a file
`gui.py` cannot both be the module `gui`.

## Decision

1. **A split module becomes a package of the same name.** `utils.py` becomes `utils/`, and `websocket.py`,
   `channel.py`, `inventory.py`, `translate.py` and `twitch.py` follow. Each file in a package holds one concern
   and is named for it. A file is never named after its package or after a standard library module, so the
   JSON helpers are in `utils/jsonfile.py`, not `utils/json.py`. The package takes the module's row in the
   module map and keeps its doc, `docs/modules/<name>.md`, as `gamelib/` does.
2. **`constants.py` and `gui.py` stay at the top level**, because their own file path is part of what they do.
   The code that leaves them goes to a package with a name of its own:
   - `constants.py` keeps the paths, the intervals and limits, `State`, `PriorityMode`, the type names and the
     logging values. The client types, the GQL operations and the PubSub topics go to `twitchapi/`: the
     definitions of what the app sends to Twitch, which the [GQL runbook](../runbooks/gql-operations.md)
     updates.
   - `gui.py` keeps the preview under `if __name__ == "__main__":` and imports from `ui/` every name that other
     modules import from `gui`, such as `GUIManager`. The GUI classes go to `ui/`. When `gui.py` would still be
     over the cap, the preview's mock moves to `ui/` as a function that the `__main__` block calls.
3. **Callers keep their imports.** A package's `__init__.py` holds only a docstring, imports and `__all__`. It
   imports every name that another module or a test imports from the old module, so
   `from utils import json_load`, `from twitch import Twitch`, `from gui import GUIManager` and
   `from translate import _` still work. The files of a package import each other with relative imports, as in
   `gamelib/`. A name that leaves `constants.py` is imported from its new package: `constants.py` imports no
   repo module except `version`, and `twitchapi/` imports `constants`, so a re-export there would make an import
   cycle.
4. **A class over 300 lines is split into mixins.** A mixin is a class in the same package whose name ends in
   `Mixin`. It holds a group of the class's methods, moved unchanged, has no `__init__`, and declares as
   annotations without a value the attributes and methods of the class that its methods use. When the class has
   `__slots__`, each mixin sets `__slots__ = ()`, because a base class without it gives every object of the class
   a `__dict__`, which accepts any new attribute. The class lists its mixins as bases and keeps `__init__`, which
   sets every attribute. A helper function that takes the object rewrites every `self` of the moved code, and a
   collaborating class needs new state and new calls, so a reviewer cannot check either as a move. They are the
   better form for code that needs no `self`, such as the wanted games ranking in `Twitch._run_games_update`, or
   that keeps state of its own, as `_AuthState` does. Such a rewrite is a commit of its own, after the split.
5. **A method over 300 lines is split before it moves.** It cannot move whole into a file of 300 lines. A
   `refactor:` commit of its own cuts it into methods, each a run of consecutive lines of the old body, and
   changes nothing else. The tests that run the method pass unchanged, and for `SettingsPanel.__init__` the
   preview shows the same Settings tab. A local variable that several of the new methods use stays a local of
   the old method, which passes it to them as an argument and takes it back as a return value. So the object
   gains no attribute, which `Twitch.shutdown` would have to clear. `Twitch._run` was cut this way: its loop
   calls a method for each state from `INVENTORY_FETCH` to `CHANNEL_SWITCH`, such as `_run_games_update`.
6. **A split commit moves code and changes no behavior.** It is a `refactor:` commit for one module. The moved
   lines keep their text and order, except imports, the bases of a class that gains mixins, and a name the move
   requires. The new lines are the package's `__init__.py`, a one-line docstring for each new file and mixin,
   and the annotations and the empty `__slots__` of decision 4. A function that the preview's mock becomes
   re-indents the mock, which `git diff -w` hides. `git diff -M --stat` shows the moves, and the sorted lines of
   the old file match those of the new files, apart from the lines this decision allows.
7. **Tests follow the code they test.** A test that patches a module global, such as `random` for
   `ExponentialBackoff`, patches the file that now reads it (`utils.backoff`), in the split commit. Such a global is
   read in one file where the split allows it, so one patch reaches every read: `get_session` moves with
   `_AuthState`, because both read `COOKIES_PATH`. When the code that a test runs reads the global in two files, the
   test patches both, as the login test does with `datetime`. A test of code that left `constants.py` or `gui.py`
   moves to the test file of the new package, such as `tests/test_twitchapi.py`. A new test file for a file of a
   package is named `test_<package>_<file>.py`, as the tests of `gamelib/` are.
8. **Docs, checks and packaging change in the same commit.** The package's doc has a table of its files, as
   [gamelib.md](../modules/gamelib.md) has, and keeps the sections of the module's doc. A package that needs
   neither Twitch nor a display is in `source` under `[tool.coverage.run]` in `pyproject.toml`; one that needs
   either is not, as its module was not. Each new package is added to the `cp` and `compileall` lines of
   `appimage/AppImageBuilder.yml`. PyInstaller follows the imports of `main.py`, relative imports included, so
   `build.spec` needs no hidden import for a package. The module leaves `EXCEPTIONS` in `scripts/linecap.py`,
   and task 005 records its new line counts.

| Module | Becomes | Its files hold |
| --- | --- | --- |
| `utils.py` | `utils/` | the JSON files, `ExponentialBackoff`, `Game`, the task helpers, the window and browser helpers, the small helpers |
| `websocket.py` | `websocket/` | `Websocket`, the mixin that receives and sends its messages, `WebsocketPool` |
| `constants.py` | stays; `twitchapi/` | the client types, the GQL operations, the PubSub topics |
| `channel.py` | `channel/` | `Stream`; `Channel` with its mixins |
| `inventory.py` | `inventory/` | `Benefit`; `BaseDrop` and `TimedDrop`; `DropsCampaign` |
| `translate.py` | `translate/` | the `TypedDict` classes; `default_translation`; `Translator` and `_` |
| `twitch.py` | `twitch/` | `_AuthState` with the mixin of the session methods; `Twitch` with mixins for the requests, the inventory fetch, the PubSub handlers, the channel discovery and the state loop |
| `gui.py` | stays; `ui/` | the generic widgets, the Main tab panels, `TrayIcon`, `InventoryOverview`, `HelpTab`, `SettingsPanel` with its mixins, `GUIManager` with its theme |

## Consequences

- The module map gains two rows, `twitchapi/` and `ui/`. Every other split changes the row of its module.
- A name can be imported from the package and from its file. Callers use the package; a test that patches a
  global uses the file. A patch on the package (`monkeypatch.setattr(utils, "random", ...)`) changes nothing
  that the code reads, and the test that made it then fails.
- Importing a package imports all its files. `import utils` imports `tkinter` and Pillow, as `utils.py` did.
- A mixin's methods read attributes that `__init__` sets in another file. Its annotations name them for the
  reader; no type checker runs on the code ([ADR-0014](ADR-0014-code-rules.md)).
- Moved code keeps its inherited comments, names and missing types until a change rewrites it for another
  reason. A split applies none of the code rules of ADR-0014.
- A fix taken from upstream for a moved function no longer applies to the file it names. It conflicts and is
  made by hand in the new file ([upstream-fixes.md](../runbooks/upstream-fixes.md#when-the-pick-conflicts)).
- A script that reads a module's file by its path changes with the split. `rostercheck.py` reads the settings
  mock and the settings reads from `gui.py`, so the split of `gui.py` makes it read `ui/` too.

## Alternatives rejected

- **A flat module for each part**, such as `jsonfile.py` beside `utils.py`: more than 30 new rows in a module
  map that has room for 23.
- **A new name for every package, with the old module left as a file of imports**, such as `utils.py` beside a
  `utilparts/`: two places to look for one concern, and a name to invent for each.
- **A `gui/` package run as `python -m gui`**: it changes a command that three docs name, and `constants.py`
  finds a run of the preview by the file name `gui.py`, so that check changes too.
- **A `constants/` package**: `SELF_PATH` and `IS_APPIMAGE` are computed from the folder of the constants file,
  which a package moves one level down.
- **Callers import from the file**, such as `from utils.jsonfile import json_load`, with an empty
  `__init__.py`: each split then edits the imports of every caller, mixed into the moves.
- **Collaborating classes or helper functions in the split commit**: they rewrite every moved method, so the
  commit cannot be checked as a move.

## Related

- [Task 005](../refinements/tasks/005-modules-over-the-line-cap.md): the split points and the line counts.
- [AGENTS.md](../../AGENTS.md#module-map): the module map and the line cap; its
  [recipes](../../AGENTS.md#recipes) for a new module and a new package.
- [gamelib.md](../modules/gamelib.md): the package form the splits follow.
- [ADR-0014](ADR-0014-code-rules.md): the code rules that a later rewrite of moved code applies.
- [building.md](../building.md#build-the-appimage): the AppImage recipe and its package folders.
