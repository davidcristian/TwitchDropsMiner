# ADR-0013: Tests assert behavior, with an 80% coverage floor

**Status:** Accepted (2026-10-18)

## Context

The repo had no tests ([task 003](../refinements/tasks/003-test-suite.md)). A change to logic was checked by
calling it by hand, and nothing repeated that check on the next change.

Cortex, another of the maintainer's repos, requires 100% line and branch coverage. On 2026-10-18 the maintainer
rejected that number for this repo as an antipattern, because a test written to reach a line asserts nothing a
caller depends on, and chose rules about what tests assert plus a floor of 80% branch coverage.

## Decision

1. **pytest runs the suite in `tests/`,** one file per module under test, and `just check` runs it with
   coverage ([ADR-0012](ADR-0012-check-command.md)). `tests/` is not at the top level, so no build includes it.
2. **What the tests assert:**
   - A bug fix adds a test that fails without the fix.
   - A module that needs neither Twitch nor a display has a test of each public function, with its error and
     edge cases: empty input, a missing or malformed file, case and accent differences, and the like.
   - A test written only to reach a line is not allowed.
   - A known defect that is not fixed yet is a test of the correct behavior marked
     `pytest.mark.xfail(strict=True)`, whose reason names the task file. When the fix makes it pass, the strict
     mark fails the suite until the mark is removed.
3. **Fakes rather than mocks.** A test writes real files to `tmp_path` and builds real values. `monkeypatch`
   only points a path lookup or a module constant at a test value, or picks a platform branch. No test uses
   `unittest.mock`, because a mock asserts which calls the code makes rather than what it returns.
4. **The suite fails below 80% branch coverage** of the modules listed under `[tool.coverage.run]` in
   `pyproject.toml`: the modules that need neither Twitch nor a display, today `redact`, `gamelib` and the
   `scripts/` folder. The floor applies to their total. A new such module is added to the list.
5. **Tests do not read the machine they run on.** A test that looks for launchers, the registry or a home folder
   points that lookup at a temporary folder, so the suite gives the same result on every machine and in CI.

## Consequences

- The modules that need Twitch or a display, such as `twitch.py` and `gui.py`, are outside the floor. They are
  checked as AGENTS.md says: in the GUI, or with stubbed inputs. The [code rules](ADR-0014-code-rules.md) put new
  logic where a test can reach it.
- The floor finds a listed module whose tests were forgotten. It does not find a missing edge case, which the
  rules in decision 2 cover.
- A branch that runs only on another OS, or only when a launcher is installed, counts as missed. The 20% margin
  leaves room for such branches without a test that fakes the OS.
- `utils.py` and `settings.py` import `tkinter` and Pillow when they load, so their tests need
  `requirements.txt` installed. They are not in the suite yet
  ([task 031](../refinements/tasks/031-tests-for-utils-and-settings.md)).

## Alternatives rejected

- **100% coverage, as in Cortex.** It rewards tests that reach a line without asserting a result, and needs
  fakes for Twitch, aiohttp and tkinter before `twitch.py` and `gui.py` could pass.
- **Rules with no number.** Nothing would then find a listed module with no tests.
- **`unittest` from the standard library.** pytest is a development tool that no build installs, and its
  fixtures (`tmp_path`, `monkeypatch`, `capsys`) are what the fakes above need.

## Related

- [AGENTS.md](../../AGENTS.md#what-every-change-must-pass), check 1 of the hand checks.
- [ADR-0012](ADR-0012-check-command.md) (the command that runs the suite) and
  [ADR-0014](ADR-0014-code-rules.md) (logic apart from I/O).
- Tasks [003](../refinements/tasks/003-test-suite.md) (closed by this record),
  [031](../refinements/tasks/031-tests-for-utils-and-settings.md) (the modules not yet tested) and
  [009](../refinements/tasks/009-trademark-symbols-in-game-names.md) (a known defect with a strict `xfail` test).
