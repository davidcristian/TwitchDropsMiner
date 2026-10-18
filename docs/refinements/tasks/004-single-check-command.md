# No single command runs the repo checks

**Status:** done 2026-10-18
**Area:** repo checks, ci
**Origin:** [AGENTS.md](../../../AGENTS.md#what-every-change-must-pass)
**Verified:** 2026-10-18

AGENTS.md lists the checks every change must pass and says there is no single check command yet. Three of them
are commands or rules that a script can run, and each one runs by hand:

1. `python -m py_compile *.py gamelib/*.py`.
2. `python -m json.tool` on every `lang/*.json` file.
3. The banned words and the dash rule of the [Prose](../../../AGENTS.md#prose) section, which AGENTS.md says
   no script checks.

CI runs only the second one. The Validate job in `.github/workflows/ci.yml` has one check step, "Validate
language files", which runs `python -m json.tool` on each language file. The Windows, macOS and Linux jobs
wait for Validate and then build and package the app, with no check step of their own.

The Prose section of AGENTS.md limits every markdown file to 250 lines, and `docs/adr/README.md` states the
same limit for a decision record. Nothing measures any of them. Nothing checks either that the relative links
between the docs resolve, or that `docs/refinements/index.md` lists every task file.

## What closes it

One standard-library Python script and one step in the Validate job that runs it. The script runs:

- `py_compile` on every tracked `.py` file. On Python 3.10, the `PYTHON_VERSION` in `ci.yml`, this finds
  syntax that 3.10 rejects, such as `except*`. It does not find `typing.Self` or `tomllib`, which fail only
  when a module is imported.
- `json.loads` on every `lang/*.json` file, in place of the shell loop in the Validate step.
- The banned words and the dash rule over `README.md`, `AGENTS.md` and `docs/**/*.md`. The script reads the
  banned table from AGENTS.md, so the list stays in one place. It skips text in backticks, link targets, URLs
  and the rows of the table itself.
- The 250-line limit that AGENTS.md sets on every markdown file.
- Every relative link in the same markdown files: the file it names exists, and its `#anchor`, when it has
  one, matches a heading in that file, as GitHub forms heading anchors.
- Every file in `docs/refinements/tasks/` has a row in the task list of `docs/refinements/index.md`, and every
  row links a file that exists.

`py_compile` compiles without importing, so the step needs no `requirements.txt` install. The script does not
go at the top level, because `appimage/AppImageBuilder.yml` copies every top-level `*.py` file into the
AppImage. The 300-line module cap is soft, so the script can list the modules over it without failing
([005](005-modules-over-the-line-cap.md)). The Prose rules also cover comments, docstrings and commit
messages: the standard `tokenize` module can extract comments and docstrings if the check is extended to code.

AGENTS.md's "What every change must pass" section then names the one command. As its working agreement
requires, the script is shown to fail on a banned word, a dash, an invalid language file, a broken link and a
task file missing from the index, each added for the test, before it is trusted.

Cost: no Twitch requests and a few seconds of CI time.

## How it was closed

`just check` is the one command ([ADR-0012](../../adr/ADR-0012-check-command.md)). The pre-commit hook and the
Validate job in CI run it. It differs from the proposal above in four ways:

- A `justfile` runs one standard-library script per rule from `scripts/`, in place of one script.
- `syntaxcheck.py` parses each file with `ast.parse(feature_version=(3, 10))`, which rejects `except*` on any
  Python, in place of `py_compile`, which rejects it only on 3.10.
- The line limit covers modules too. The eight inherited modules over 300 lines are named exceptions
  ([005](005-modules-over-the-line-cap.md)).
- It also runs ruff, `rostercheck.py` (the module map, the module docs and the settings keys against the code)
  and the test suite ([003](003-test-suite.md)), and two commit-msg hooks check commit messages.

Each scan was shown to fail on a broken copy of the repo: a banned word, a phrase split by a line break, an em
dash, an invalid language file, a broken link and heading, a task missing from the index, a module missing from
the map, and a settings key missing from each place that lists it.

## History

- 2026-10-18: Opened. Found while the docs were written, from the AGENTS.md lines that say no single check command
  exists and no script checks the banned words.
- 2026-10-18: Closed. `just check` runs the scans, ruff and the tests, locally and in CI.
