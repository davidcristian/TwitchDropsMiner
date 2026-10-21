# ADR-0013: Tests assert behavior, with an 80% coverage floor

**Status:** Accepted (2026-10-21)

## Context

The repo had no tests ([task 003](../refinements/tasks/003-test-suite.md)). A change to logic was checked by
calling it by hand, and nothing repeated that check on the next change.

Cortex, another of the maintainer's repos, requires 100% line and branch coverage. On 2026-10-18 the maintainer
rejected that number for this repo as an antipattern, because a test written to reach a line asserts nothing a
caller depends on, and chose rules about what tests assert plus a floor of 80% branch coverage.

The modules that need Twitch or a display import aiohttp, Pillow, pystray and `tkinter`, and the Validate job
installed none of these packages, so a fix in one of them was checked by a script outside the suite. On
2026-10-21 the maintainer asked for suite tests of these modules too.

## Decision

1. **pytest runs the suite in `tests/`,** one file per module under test, and `just check` runs it with
   coverage ([ADR-0012](ADR-0012-check-command.md)). `tests/` is not at the top level, so no build includes it.
2. **What the tests assert:**
   - A bug fix adds a test that fails without the fix.
   - A module that needs neither Twitch nor a display has a test of each public function, with its error and
     edge cases: empty input, a missing or malformed file, case and accent differences, and the like.
   - A module that needs Twitch or a display, such as `twitch.py` or `gui.py`, needs no test of each public
     function, but a bug fix in it adds a suite test as above. The test passes fakes, such as a fake `Twitch` or
     a session whose requests raise, and creates no Tk window, because the Validate job has no display.
     `tests/fakes.py` has a fake `Twitch`, which records each request and returns the responses a test gives it.
   - A test written only to reach a line is not allowed.
   - A known defect that is not fixed yet is a test of the correct behavior marked
     `pytest.mark.xfail(strict=True)`, whose reason names the task file. When the fix makes it pass, the strict
     mark fails the suite until the mark is removed.
3. **Fakes rather than mocks.** A test writes real files to `tmp_path` and builds real values. `monkeypatch`
   only points a path lookup or a module constant at a test value, or picks a platform branch. No test uses
   `unittest.mock`, because a mock asserts which calls the code makes rather than what it returns.
4. **The suite fails below 80% branch coverage** of the modules listed under `[tool.coverage.run]` in
   `pyproject.toml`: the modules that need neither Twitch nor a display, today `redact`, `reconnect`, `gamelib`,
   `gqldata`, `imagedata`, `savefiles`, `settingsdata`, `ratelimit`, `instancelock`, `mousewheel`, `constants`
   and the `scripts/` folder. The floor applies to their total. A new such module is added to the list. The
   modules that need Twitch or a display are not listed.
5. **Tests do not read the machine they run on.** A test that looks for launchers, the registry or a home folder
   points that lookup at a temporary folder, so the suite gives the same result on every machine and in CI.
   An autouse fixture in `tests/conftest.py` calls `isolate_git` from `tests/gitrepo.py` for each test:
   - It removes every `GIT_` environment variable. The pre-commit hook runs the suite with `GIT_DIR` and
     `GIT_INDEX_FILE` set to the repo being committed, and git would then send a test's `init`, `add` and
     `commit` to that repo instead of the test's temporary one.
   - It sets `HOME` and `XDG_CONFIG_HOME` to an empty folder and sets `GIT_CONFIG_NOSYSTEM`, so git reads no
     global or system config and no global ignore file. A user's ignore file would hide a test repo's files from
     `git ls-files`. The check scripts still follow the user's ignore files when `just check` runs them on the
     repo, as git does.

## Consequences

- The modules that need Twitch or a display, such as `twitch.py` and `gui.py`, are outside the floor, so
  nothing reports a fix in them without a test; the reviewer checks it. What a test cannot reach, such as a real
  login or the window, is checked as AGENTS.md says: in the GUI, or with stubbed inputs. The
  [code rules](ADR-0014-code-rules.md) put new logic where a test can reach it.
- The floor finds a listed module whose tests were forgotten. It does not find a missing edge case, which the
  rules in decision 2 cover.
- A fixture with a scope wider than a function runs before the autouse fixture, so one that runs git calls
  `isolate_git` from `tests/gitrepo.py` itself first.
- A branch that runs only on another OS, or only when a launcher is installed, counts as missed. The 20% margin
  leaves room for such branches without a test that fakes the OS.
- The Validate job installs the app's packages except PyGObject and pywin32
  ([ADR-0012](ADR-0012-check-command.md)), and `tests/conftest.py` sets `PYSTRAY_BACKEND=dummy`, so that
  importing `gui.py` loads no tray backend. A test can import every module except `registry.py`, which needs
  Windows, and `tests/test_imports.py` imports each module that imports the app's packages. The logic of
  `utils.py` and `settings.py` has no tests yet
  ([task 031](../refinements/tasks/031-tests-for-utils-and-settings.md)).

## Alternatives rejected

- **100% coverage, as in Cortex.** It rewards tests that reach a line without asserting a result, and needs
  fakes for Twitch, aiohttp and tkinter before `twitch.py` and `gui.py` could pass.
- **Rules with no number.** Nothing would then find a listed module with no tests.
- **The modules that need Twitch or a display in the coverage list.** With them the total was 44% on
  2026-10-21, so the floor would fail until most of `twitch.py` and `gui.py` had tests.
- **`unittest` from the standard library.** pytest is a development tool that no build installs, and its
  fixtures (`tmp_path`, `monkeypatch`, `capsys`) are what the fakes above need.

## Related

- [AGENTS.md](../../AGENTS.md#what-every-change-must-pass), check 1 of the hand checks.
- [ADR-0012](ADR-0012-check-command.md) (the command that runs the suite) and
  [ADR-0014](ADR-0014-code-rules.md) (logic apart from I/O).
- Tasks [003](../refinements/tasks/003-test-suite.md) (closed by this record),
  [031](../refinements/tasks/031-tests-for-utils-and-settings.md) (the modules not yet tested) and
  [009](../refinements/tasks/009-trademark-symbols-in-game-names.md) (a defect whose strict `xfail` tests became
  plain tests with its fix).
