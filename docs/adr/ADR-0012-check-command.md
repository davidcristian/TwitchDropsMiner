# ADR-0012: One check command

**Status:** Accepted (2026-10-22)

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
   - `langcheck.py`: every `lang/*.json` file is a JSON object, has no key that the app does not read, and has
     no string with a `str.format` field that the English string at the same keys lacks. A key the app does not
     read is one that `merge_json` in `utils/jsonfile.py` removes or replaces when the app loads the file, so its text
     never shows. The scan prints how many English strings each file lacks and does not fail on them, because a
     new string may be missing in other languages, which show it in English. It reads `default_translation`
     from `translate/english.py` with `ast`, so that it needs only the standard library, as the other scans do.
   - `linecap.py`: at most 300 lines per Python or markdown file. The two inherited modules over 300 are named
     in `EXCEPTIONS`, and an entry fails once its module is under the limit, so the list only shrinks as
     [task 005](../refinements/tasks/005-modules-over-the-line-cap.md) splits them.
   - `dashcheck.py`: no em dash, en dash or other Unicode dash in any text file, and no spaced `--` in prose:
     markdown outside code, Python comments and docstrings, and `.txt` files. In a shell script or a recipe,
     `--` ends the options. `DASHES` in `sources.py` lists the Unicode dashes for this scan and `commitlint.py`.
     The minus sign U+2212 passes, because a formula uses it. A hyphen with a space on each side passes too:
     a comment such as `n - 1` uses it as a minus sign, and inherited comments and English strings that use it
     as a dash keep it, so that upstream fixes still apply. The reader checks it.
   - `prosecheck.py`: no word of the banned table in AGENTS.md in docs, comments, docstrings, the strings of
     `translate/english.py` or the other text files, and no comment block or docstring over three lines. It reads the
     table from AGENTS.md, so the list is written in one place. It reads a block quote without its `>`
     markers, so a phrase split across two quoted lines is found.
   - `docscheck.py`: every relative link between markdown files resolves to a file in the repo, with its
     heading anchor formed as GitHub forms it; no doc cites a source line by number; `docs/index.md` links every
     ADR and module doc, and the backlog index every task, with the record's title as the link text; every ADR
     and task file is named and written in its format.
   - `rostercheck.py`: the module map in AGENTS.md lists every top-level module and package, every module has a
     doc in `docs/modules/`, the settings keys agree between `SettingsFile`, `default_settings`, `Settings`, the
     key table in [settings.md](../modules/settings.md) and the preview mock, and the scans in AGENTS.md and the
     `justfile` are the scripts in `scripts/`.
3. **ruff checks the rules ruff 0.6 enabled by default** (`E4`, `E7`, `E9`, `F`), set in `pyproject.toml`. They
   find mistakes such as an unused import or an undefined name.
4. **Two commit-msg hooks check each commit message**: conventional-pre-commit for the type and format, and
   `scripts/commitlint.py` for the subject length and case, the body's width and word count, the banned words,
   the dashes, and numbered references and commit hashes. They run on the machine that commits, not in CI.
   `.pre-commit-config.yaml` names conventional-pre-commit by the commit of its `v4.4.0` tag, with the tag in a
   `# frozen:` comment, so a tag moved to other code does not change what runs.
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
   - `rust-just` is a build of `just` by another person, from `github.com/gnpaone/rust-just`. The Validate job
     removes it and runs the official release of the same version from `github.com/casey/just`, checked against
     the SHA-256 that the release's `SHA256SUMS` file lists for each runner, written in `ci.yml`.
   - Developers keep `rust-just`, because the pre-commit hook needs `just` on every machine and one
     `pip install` sets it up on every OS.
6. **`requirements-dev.txt` also installs the app's packages that the tests import**: the lines of
   `requirements.txt` without PyGObject, with the same version ranges and platform markers. The Validate job
   installs it with `-c constraints.txt`, so that the tests get the versions that a build installs
   ([ADR-0016](ADR-0016-exact-dependency-versions.md)).
   - PyGObject is left out because pip builds it from source on Linux, which needs the system packages in
     [building.md](../building.md#requirements), and no test needs it: `tests/conftest.py` sets
     `PYSTRAY_BACKEND=dummy`, so pystray loads no tray backend.
   - pywin32 installs only on Windows. `gui.py` imports `win32api`, `win32con` and `win32gui` there, so every
     test that imports `gui.py` needs it on Windows.
   - The Validate job therefore installs no system package, and a virtual environment with
     `requirements-dev.txt` alone runs `just check` as the Validate job does
     ([building.md](../building.md#run-the-checks)). On Linux, the test recipe runs pytest under `xvfb-run`,
     which the runner's Ubuntu image has, for the tests that open the window
     ([ADR-0013](ADR-0013-test-standard.md)).
7. **The Validate job runs `just check` four times**, from a `strategy.matrix` in `ci.yml`:
   - Ubuntu with `PYTHON_VERSION`, 3.10, the oldest Python the app supports. There `syntaxcheck.py` finds
     nested f-string quotes, and a test that imports or calls a name 3.10 lacks fails.
   - Ubuntu with `BUILD_PYTHON_VERSION`, 3.14, the Python of the release builds
     ([ADR-0015](ADR-0015-release-build-python.md)).
   - Windows and macOS with `PYTHON_VERSION`. These run the `cmd.exe` recipes, the code for those two systems,
     and the tests of the window on Tk without X11.

   A failure in either Ubuntu run fails the workflow, and the build jobs wait for all four runs. Until each has
   passed once, the Windows and macOS runs set `continue-on-error`, so a failure there does not fail the
   workflow. [Task 046](../refinements/tasks/046-checks-run-only-on-linux-and-python-3-10.md) lists what that run
   must show.

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
- The four builds wait for the slowest of the four Validate runs.
- Each Validate run is a check named `Validate (<runner>, <variable>)`, such as
  `Validate (ubuntu-latest, PYTHON_VERSION)`. A branch rule on GitHub that requires a check names these.
- A change that fails only on Windows or macOS can be merged while those runs are not required.
- Nothing checks that the app's packages in `requirements-dev.txt` match `requirements.txt`, so a change to one
  of those lines is made in both files.
- Commits from upstream keep their own messages, and a commit made without the hooks is not checked.
- On a developer's machine, `just` comes from `rust-just` on PyPI, whose metadata names `github.com/casey/just`
  as the home page and `github.com/gnpaone/rust-just` as the repository. pip checks no hash, so a file replaced
  on PyPI under the same version is installed by the next `pip install`, and its binary runs on every commit
  with the rights of the person who commits. CI does not run it.
- The Validate job reads the `just` version from the `rust-just` line of `requirements-dev.txt`, so a new
  version there fails the job until `ci.yml` has the hashes of that `just` release.
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
- **The official `just` binary for developers too.** It removes the other person's build from every machine,
  but needs a download and a hash check for each OS in [building.md](../building.md#run-the-checks) in place
  of one `pip install`. It replaces `rust-just` there when that package stops following the `just` releases or
  changes owner.
- **`rust-just` with a hash in `requirements-dev.txt`.** pip's hash mode needs a hash for every package the
  file installs, for each OS and Python; [ADR-0016](ADR-0016-exact-dependency-versions.md) says why the builds
  use no hashes either.
- **Every Python from 3.10 to 3.14 on every runner.** That is fifteen runs for each push. 3.10 is the oldest
  Python the app supports and 3.14 the Python of the releases; 3.11 to 3.13 are neither.
- **Windows and macOS required from their first run.** They had never run, and a test written for Linux that
  fails there would stop every build until it was fixed or skipped.

## Related

- [AGENTS.md](../../AGENTS.md#what-every-change-must-pass) and [building.md](../building.md#run-the-checks).
- [ADR-0013](ADR-0013-test-standard.md): the tests that `just check` runs.
- [ADR-0015](ADR-0015-release-build-python.md): the two Python versions in `ci.yml`.
- [ADR-0008](ADR-0008-docs-layout.md): the docs layout that `docscheck.py` checks.
- Tasks [004](../refinements/tasks/004-single-check-command.md) (closed by this record),
  [005](../refinements/tasks/005-modules-over-the-line-cap.md) (the modules over the limit),
  [046](../refinements/tasks/046-checks-run-only-on-linux-and-python-3-10.md) (the Windows and macOS runs) and
  [049](../refinements/tasks/049-check-tools-from-third-party-sources.md) (the sources of `just` and a hook,
  closed by the official `just` in CI and the hook's commit).
