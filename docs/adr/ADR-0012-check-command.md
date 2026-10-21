# ADR-0012: One check command

**Status:** Accepted (2026-10-21)

## Context

Until this record, AGENTS.md listed the checks a change must pass as commands to run by hand: `py_compile`, a
`json.tool` loop over `lang/`, and the prose rules, which nothing checked. CI ran only the language file check.
[Task 004](../refinements/tasks/004-single-check-command.md) recorded the gap.

On 2026-10-18 the maintainer compared AGENTS.md with the one in Cortex, another of the maintainer's repos, and
chose which of its checks this repo adopts: one `just check` command, the line limits as a check with the
inherited modules named as exceptions, the prose, docs and roster scans, the two commit message hooks, and ruff's
lint rules without its formatter or pyright.

## Decision

1. **`just check` runs every check, and the pre-commit hook and the Validate job in CI run the same command.** A
   commit is checked the same way on every machine and in CI. The recipes are in the `justfile`; each one runs
   one command, so the Windows shell (`cmd.exe`) runs them too.
2. **The scans are standard-library Python scripts in `scripts/`,** one per rule, each with a `check(root)` that
   returns its problems and a `main()` that prints them and returns 1 when there are any. They read the files git
   tracks, and untracked files that `.gitignore` does not exclude, so a new file is checked before `git add`.
   `linecap.py`, `dashcheck.py`, `prosecheck.py` and `docscheck.py` report a file they read that is not UTF-8
   text, and skip a file with a NUL byte as a binary file, such as an icon. `syntaxcheck.py` and `langcheck.py`
   report both. `scripts/` is not at the top level, so the AppImage, which copies the top-level `*.py` files,
   leaves it out.
   - `syntaxcheck.py`: every Python file parses with `ast.parse(feature_version=(3, 10))`, and has no starred
     item in a subscript (`a[*b]`) or starred `*args` annotation, which that call accepts on Python 3.11 and
     later. Run on Python 3.12, it does not find nested f-string quotes, which the Validate job on 3.10 finds.
   - `langcheck.py`: every `lang/*.json` file is a JSON object, and no string in it has a `str.format` field
     that the English string at the same keys lacks. It reads `default_translation` from `translate.py` with
     `ast`, so that it needs only the standard library, as the other scans do.
   - `linecap.py`: at most 300 lines per Python file and in AGENTS.md, and 250 per other markdown file. The eight
     inherited modules over 300 are named in `EXCEPTIONS`, and an entry fails once its module is under the limit,
     so the list only shrinks as [task 005](../refinements/tasks/005-modules-over-the-line-cap.md) splits them.
   - `dashcheck.py`: no em dash, en dash or other Unicode dash in any text file, and no spaced `--` in prose:
     markdown outside code, Python comments and docstrings, and `.txt` files. In a shell script or a recipe,
     `--` ends the options. `DASHES` in `sources.py` lists the Unicode dashes for this scan and `commitlint.py`.
     The minus sign U+2212 passes, because a formula uses it. A hyphen with a space on each side passes too:
     a comment such as `n - 1` uses it as a minus sign, and inherited comments and English strings that use it
     as a dash keep it, so that upstream fixes still apply. The reader checks it.
   - `prosecheck.py`: no word of the banned table in AGENTS.md in docs, comments, docstrings, the strings of
     `translate.py` or the other text files, and no comment block or docstring over three lines. It reads the
     table from AGENTS.md, so the list is written in one place. It reads a block quote without its `>`
     markers, so a phrase split across two quoted lines is found.
   - `docscheck.py`: every relative link between markdown files resolves to a file in the repo, with its
     heading anchor formed as GitHub forms it; no doc cites a source line by number; `docs/index.md` links every
     ADR and module doc, and the backlog index every task, with the record's title as the link text; every ADR
     and task file is named and written in its format.
   - `rostercheck.py`: the module map in AGENTS.md lists every top-level module and package, every module has a
     doc in `docs/modules/`, the settings keys agree between `SettingsFile`, `default_settings`, `Settings`, the
     key table in [settings.md](../modules/settings.md) and the `gui.py` mock, and the scans in AGENTS.md and the
     `justfile` are the scripts in `scripts/`.
3. **ruff checks the rules ruff 0.6 enabled by default** (`E4`, `E7`, `E9`, `F`), set in `pyproject.toml`. They
   find mistakes such as an unused import or an undefined name.
4. **Two commit-msg hooks check each commit message**: conventional-pre-commit for the type and format, and
   `scripts/commitlint.py` for the subject length and case, the body's width and word count, the banned words,
   the dashes, and numbered references and commit hashes. They run on the machine that commits, not in CI.
   - A paste is read for the banned words and the references, as AGENTS.md says, and not for the width, the
     word count or the dashes.
   - A last paragraph of trailers is not counted as body words when each key is one that git, GitHub or
     Conventional Commits writes, such as `BREAKING CHANGE` or `Co-authored-by`. Other `Key: value` lines are.
   - `decision 7`, `item 4`, `rule 4` and `section 2` are numbered references wherever they stand. `check 3`
     and `step 2` are only after `as` or `see`, or before `in` or `of` and a doc name, so that a count such as
     `check 20 channels` passes. `line 4` is only before `in` or `of` and a file name.
   - git runs the hook with `GIT_EDITOR=:` when no editor opens, as for `git commit -m`, and then keeps a line
     that starts with `#`, so the hook reads it. After an editor, git removes those lines and everything below
     the scissors line, and the hook skips them.
5. **The tool versions are set exactly in `requirements-dev.txt`,** which no build installs: `rust-just` (the `just` binary
   from PyPI, so one `pip install` sets up every tool on every OS), ruff, pytest, pytest-cov and pre-commit, each
   a release at least two weeks old when it was chosen.
6. **`requirements-dev.txt` also installs the app's packages that the tests import**: the lines of
   `requirements.txt` without PyGObject and pywin32, with the same version ranges, so that the tests get the
   newest releases, as a build does. They get exact versions with the build dependencies
   ([task 048](../refinements/tasks/048-builds-install-the-newest-dependencies.md)).
   - PyGObject is left out because pip builds it from source on Linux, which needs the system packages in
     [building.md](../building.md#requirements), and no test needs it: `tests/conftest.py` sets
     `PYSTRAY_BACKEND=dummy`, so pystray loads no tray backend. pywin32 installs only on Windows.
   - The Validate job therefore installs no system package, and a virtual environment with
     `requirements-dev.txt` alone runs `just check` as the Validate job does
     ([building.md](../building.md#run-the-checks)). On Linux, the test recipe runs pytest under `xvfb-run`,
     which the runner's Ubuntu image has, for the tests that open the window
     ([ADR-0013](ADR-0013-test-standard.md)).

## Consequences

- A rule that a script can check is checked on every commit and in CI. The rules no script checks (imperative
  mood, plain words, comments that repeat the code) stay with the reader and the reviewer.
- A banned word inside a hyphenated compound is not found, so that a name such as `ubuntu-22.04-arm` in
  `ci.yml` passes. The reader checks such compounds.
- A new scan is added to `scripts/`, the `justfile` and the list in AGENTS.md together, or `rostercheck.py`
  fails.
- Fixing the scans' first run took edits to inherited comments and docstrings: 17 comment blocks and 17
  docstrings over three lines and 8 banned words. A fix cherry-picked from upstream can conflict on those lines.
- `syntaxcheck.py` does not find names that Python 3.10 lacks, such as `typing.Self`, which fail only when the
  module is imported. The Validate job finds such a name only where a test imports or calls it.
- The Validate job installs `requirements-dev.txt` and runs `just check` on Python 3.10, and the four builds wait
  for it.
- Nothing checks that the app's packages in `requirements-dev.txt` match `requirements.txt`, so a change to one
  of those lines is made in both files.
- Commits from upstream keep their own messages, and a commit made without the hooks is not checked.
- Two tools come from a source that can change what runs under a fixed name, and nothing checks them against
  a hash ([task 049](../refinements/tasks/049-check-tools-from-third-party-sources.md)):
  - `rust-just` on PyPI is a build of `just` by another person: its metadata names `github.com/casey/just` as
    the home page and `github.com/gnpaone/rust-just` as the repository. Its binary runs on every commit, with
    the rights of the person who commits, and in the Validate job, whose token is read only and which passes
    nothing to the builds. The exact version fixes the release, not the file a new upload could replace.
  - `.pre-commit-config.yaml` names `conventional-pre-commit` by its tag, `v4.4.0`. A tag can be moved to other
    code, which a machine that installs the hooks afterwards then runs on every commit message.
- The hook does not see `--cleanup`, `commit.cleanup` or `core.commentChar`. With a cleanup mode other than
  git's default, it can skip a `#` line that git keeps, or read one that git removes.

## Alternatives rejected

- **ruff's own default rules in ruff 0.16.** They report 96 problems in the inherited code, most of them import
  order and code style, and fixing them changes lines that upstream fixes touch.
- **The ruff formatter.** It rewrites 20 of the 22 Python files, after which no upstream fix applies cleanly.
- **pyright in strict mode.** The maintainer chose ruff's lint rules alone, and pyright was not run on this
  code. The typing rules in AGENTS.md apply to new code, checked by reading.
- **Checking commit messages in CI.** Commits taken from upstream keep their original style, so CI would fail on
  them.
- **The official `just` binary with a checked hash, for now.** A release binary from `casey/just` on GitHub,
  with its SHA-256 for each OS written in the repo and checked before it runs, removes the other person's
  build. It needs a download step per OS in CI and in [building.md](../building.md#run-the-checks) in place of
  one `pip install`. It replaces `rust-just` when that package stops following the `just` releases or changes
  owner.

## Related

- [AGENTS.md](../../AGENTS.md#what-every-change-must-pass) and [building.md](../building.md#run-the-checks).
- [ADR-0013](ADR-0013-test-standard.md): the tests that `just check` runs.
- [ADR-0008](ADR-0008-docs-layout.md): the docs layout that `docscheck.py` checks.
- Tasks [004](../refinements/tasks/004-single-check-command.md) (closed by this record),
  [005](../refinements/tasks/005-modules-over-the-line-cap.md) (the modules over the limit) and
  [049](../refinements/tasks/049-check-tools-from-third-party-sources.md) (the sources of `just` and a hook).
