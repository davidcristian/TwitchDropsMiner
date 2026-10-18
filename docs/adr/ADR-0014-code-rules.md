# ADR-0014: Code rules for new code

**Status:** Accepted (2026-10-18)

## Context

Most of the code is inherited. Logic and I/O are mixed in it: the wanted games ranking and the channel order are
branches of `Twitch._run`, between GQL requests, so no test can call them
([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)). Platform differences are inline checks: on
2026-10-18, 26 lines check `sys.platform` or `os.name`, 18 in `gui.py`, 3 in `main.py`, 3 in `utils.py` and 2 in
`constants.py`.

Cortex, another of the maintainer's repos, puts logic in a core with no I/O behind ports, with one adapter per
platform. On 2026-10-18 the maintainer chose three of its rules for this repo, for new code: logic apart from I/O,
platform differences in one place, and the typing rules.

## Decision

1. **Logic apart from I/O.** New logic that calls Twitch, the disk or the OS receives that call as an argument,
   a `Protocol` or a plain function, rather than making it. A test passes a fake, and the 80% floor of
   [ADR-0013](ADR-0013-test-standard.md) can then reach the logic. The code that makes the real call holds no
   decisions.
2. **Platform differences in one place.** New behavior that differs between Windows, Linux and macOS is one
   function per concern, which the rest of the code calls. The function is the only place that checks
   `sys.platform`, so a change for one OS has one place to go and a test picks the branch.
3. **Types.** Public functions are fully typed. `Any` is used only where any value is accepted, as in
   `redact(value)`. An error is raised as a specific exception class, a subclass of `MinerException` for the
   app's own errors ([exceptions.md](../modules/exceptions.md)). Code catches the classes a call raises: never a
   bare `except:`, and `except Exception` only where a task must keep running, which then logs the error.
4. **New code only.** Inherited code follows these rules where a change rewrites it for another reason. It is
   not rewritten for the rules alone, because fixes taken from upstream then stop applying cleanly.

## Consequences

- A new module is easier to test than the inherited code next to it. The splits of task 005 are the time to
  apply these rules to the inherited logic.
- The 26 lines of inline platform checks stay until a change rewrites the code around them.
- No script checks these rules. ruff's rules find unused names and syntax errors, not missing types or a broad
  `except` ([ADR-0012](ADR-0012-check-command.md)), so the reader and the reviewer check them.

## Alternatives rejected

- **Cortex's full hexagonal layout**, with a core, ports and adapters for every capability, and a contract test
  that the fake and the real adapter both pass. This app has one process and no swappable backends, and
  rewriting the inherited code into that layout would end cherry-picks from upstream.
- **pyright in strict mode to check the types.** The maintainer chose ruff's lint rules alone. pyright was not
  run on this code.

## Related

- [AGENTS.md](../../AGENTS.md#code-rules): the rules as every change reads them.
- [ADR-0013](ADR-0013-test-standard.md): the tests these rules make possible.
- [ARCHITECTURE.md](../ARCHITECTURE.md#platform-differences): the platform code today.
- [Task 005](../refinements/tasks/005-modules-over-the-line-cap.md): the splits of the inherited modules.
