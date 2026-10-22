# ADR-0013: Tests assert behavior, with an 80% coverage floor

**Status:** Accepted (2026-10-23)

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
     a session whose requests raise.
     `tests/fakes.py` has a fake `Twitch`, which records each request and returns the responses a test gives it.
     A test of a fix in `gui.py` takes the `window` fixture of `tests/conftest.py`, which builds the real
     `GUIManager` around a fake `Twitch`, on the display of decision 6.
     A test of `Twitch` itself takes the `live_twitch` fixture of `tests/conftest.py`, which builds a real
     `Twitch` with the window, settings and responses of a fake one. Its session opens each PubSub connection
     with a function the test gives, such as one that returns a `FakePubSub`, which returns the messages the
     test gives it and records the messages the app sends. `run_with_fast_clock` in
     `tests/livetwitch.py` runs a test on an event loop whose clock moves to the next timer when no task can run,
     so a test of code that waits for seconds takes milliseconds.
   - Each function that reads a GQL response has a test that sets each value of a complete response to null in
     turn, as a `server error` does, with `tests/nullpaths.py`. It runs the real reader and asserts the outcome
     that the reader's module doc names for that value.
   - A test written only to reach a line is not allowed.
   - A known defect that is not fixed yet is a test of the correct behavior marked
     `pytest.mark.xfail(strict=True)`, whose reason names the task file. When the fix makes it pass, the strict
     mark fails the suite until the mark is removed.
3. **Fakes rather than mocks.** A test writes real files to `tmp_path` and builds real values. `monkeypatch`
   only points a path lookup or a module constant at a test value, or picks a platform branch. The
   `live_twitch` fixture also points `twitch.GUIManager` at the fake window, because `Twitch.__init__` creates
   the real window, which needs a display. No test uses `unittest.mock`, because a mock asserts which calls the
   code makes rather than what it returns.
4. **The suite fails below 80% branch coverage** of the modules listed under `[tool.coverage.run]` in
   `pyproject.toml`: the modules that need neither Twitch nor a display, today `redact`, `reconnect`, `gamelib`,
   `gqldata`, `streamdata`, `imagedata`, `savefiles`, `settingsdata`, `ratelimit`, `instancelock`, `mousewheel`,
   `folderpicker` (its tests replace the dialog with fakes), `constants` and the `scripts/` folder. The floor
   applies to their total. A new such module is added to the list. The modules that need Twitch or a display
   are not listed.
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
6. **The tests of the window run on a virtual display on Linux.** Tk needs a display to open a window. On
   Linux, `just check` runs pytest under `xvfb-run -a` when `xvfb-run` is installed. It starts Xvfb, an X
   server that draws into memory, so these tests run the same on a desktop, over SSH, in the pre-commit hook
   and in CI, and no window shows on the screen. Tk on Windows and macOS opens its windows without an X server.
   When Tk can open no window, the `display` fixture of `tests/conftest.py` skips these tests and gives the
   reason, except when the `CI` environment variable is set, as in GitHub Actions, where it fails them.
   - On Windows, `tests/conftest.py` has Tcl create its standard channels before any test, while the process
     has no standard handles, so Tcl keeps none. Tcl keeps the handles it finds first for every later Tk in
     the thread, and it finds an open file by its handle. pytest's capture closes those handles between the
     phases of a test, and Windows gives a closed handle's number to the next file opened. When that file was
     `init.tcl`, Tcl found its write-only standard channel under that number and opened no channel, and the Tk
     being created failed with `Can't find a usable init.tcl`. The app is not affected, because no code of it
     closes or replaces a standard handle.
7. **A run fails when a test leaves a thread running.** Python's exit waits for each thread that is not a
   daemon thread, so such a thread keeps a finished run open forever, and the pre-commit hook with it.
   `tests/threadcheck.py`, which `tests/conftest.py` loads, gives such a thread 5 seconds (`GRACE`) after the last
   test to end. Then it prints the name and stack of each one that still runs, sets the exit status to 1 and
   ends the process with `os._exit`. A test that starts a thread or a tray icon stops it in a `finally` block,
   so a failed assertion does not leave it waiting. For this `tests/xorgicon.py` has `stop_icon`, which waits for
   pystray's setup thread to show a real icon before it stops the icon, and `release_caller`, which answers the
   change that a thread waits for on a fake X11 icon.

## Consequences

- The modules that need Twitch or a display, such as `twitch.py` and `gui.py`, are outside the floor, so
  nothing reports a fix in them without a test; the reviewer checks it. What a test cannot reach, such as a real
  login or how the window looks, is checked as AGENTS.md says: in the GUI, or with stubbed inputs. The
  [code rules](ADR-0014-code-rules.md) put new logic where a test can reach it.
- The floor finds a listed module whose tests were forgotten. It does not find a missing edge case, which the
  rules in decision 2 cover.
- A fixture with a scope wider than a function runs before the autouse fixture, so one that runs git calls
  `isolate_git` from `tests/gitrepo.py` itself first.
- A branch that runs only on another OS, or only when a launcher is installed, counts as missed. The 20% margin
  leaves room for such branches without a test that fakes the OS.
- The Validate job installs the app's packages except PyGObject, and pywin32 only on Windows
  ([ADR-0012](ADR-0012-check-command.md)), and `tests/conftest.py` sets `PYSTRAY_BACKEND=dummy`, so that
  importing `gui.py` loads no tray backend. A test can import every module except `registry.py`, which needs
  Windows, and `tests/test_imports.py` imports each module that imports the app's packages. Apart from
  `start_task`, the logic of `utils.py` and `settings.py` has no tests yet
  ([task 031](../refinements/tasks/031-tests-for-utils-and-settings.md)).
- A Linux machine with neither `xvfb-run` nor a display skips the tests of the window, so its result differs
  from that of CI, and the skip reason names `xvfb-run`. The Validate job uses the `xvfb-run` of the runner's
  Ubuntu image ([ADR-0012](ADR-0012-check-command.md)).

## Alternatives rejected

- **100% coverage, as in Cortex.** It rewards tests that reach a line without asserting a result, and needs
  fakes for Twitch, aiohttp and tkinter before `twitch.py` and `gui.py` could pass.
- **Rules with no number.** Nothing would then find a listed module with no tests.
- **The modules that need Twitch or a display in the coverage list.** With them the total was 44% on
  2026-10-21, so the floor would fail until most of `twitch.py` and `gui.py` had tests.
- **`unittest` from the standard library.** pytest is a development tool that no build installs, and its
  fixtures (`tmp_path`, `monkeypatch`, `capsys`) are what the fakes above need.
- **`xvfb-run` in the Validate step only.** A local run without a display, such as over SSH or in an agent's
  shell, would then skip the tests of the window that CI runs.
- **A session fixture that starts Xvfb.** Xvfb's `-displayfd` option, which picks a free display number, did
  not start under WSLg, where `/tmp/.X11-unix` is read only. The fixture would need its own search for a free
  display, which `xvfb-run -a` already does.

## Related

- [AGENTS.md](../../AGENTS.md#what-every-change-must-pass), check 1 of the hand checks.
- [ADR-0012](ADR-0012-check-command.md) (the command that runs the suite) and
  [ADR-0014](ADR-0014-code-rules.md) (logic apart from I/O).
- Tasks [003](../refinements/tasks/003-test-suite.md) (closed by this record),
  [031](../refinements/tasks/031-tests-for-utils-and-settings.md) (the modules not yet tested) and
  [009](../refinements/tasks/009-trademark-symbols-in-game-names.md) (a defect whose strict `xfail` tests became
  plain tests with its fix), and [075](../refinements/tasks/075-test-run-stays-open-after-the-last-test.md) (the
  run that stayed open, which decision 7 answers).
