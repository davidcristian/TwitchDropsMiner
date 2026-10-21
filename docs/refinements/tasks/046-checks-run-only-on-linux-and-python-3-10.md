# CI runs `just check` only on Linux with Python 3.10

**Status:** open
**Area:** ci, repo checks
**Origin:** Found on 2026-10-21: the Validate job in `.github/workflows/ci.yml` has one runner and one Python
**Verified:** 2026-10-21

The Validate job runs `just check` on `ubuntu-latest` with `PYTHON_VERSION`, which is `"3.10"`. The release
builds run on Windows and macOS, but no check runs there, and no check runs on a Python newer than 3.10. So
nothing in CI runs:

- the `cmd.exe` shell that the `justfile` sets with `windows-shell`, and its `python` in place of `python3`;
- the tests and scans on Windows paths, Windows line endings and the macOS file system;
- the code that differs by platform, such as `launcher_indexes` in `gamelib/epic.py` and the lock in
  `instancelock.py`, on the platform it is written for;
- the suite on 3.11, 3.12 or 3.13. A local run uses the Python of `env/`, which was 3.12 where this task was
  written.

## What a fix involves

**Python 3.13 on Linux.** Give the Validate job a `strategy.matrix` of `"3.10"` and `"3.13"`. The 3.10 run stays:
on 3.12 and later `syntaxcheck.py` does not find nested f-string quotes, which the 3.10 run finds
([ADR-0012](../../adr/ADR-0012-check-command.md)). It was not added because no Python 3.13 with pytest was
installed where this task was written, and installing one needs the network. To check it, install 3.13 and
`requirements-dev.txt` into a new environment, run `just check`, and read the skipped tests and the coverage total.
Check also that `ast` and `tokenize` on 3.13 give the scripts in `scripts/` the same docstrings, comments and line
numbers, since `sources.py` reads both.

**Windows and macOS.** Add a Validate job for `windows-latest` and one for `macos-latest`. Neither was added,
because neither could run where this task was written, and either may fail on its first run. Before the build
jobs wait for them, a pull request run must show:

- that every tool in `requirements-dev.txt`, `rust-just` included, installs at its set version on both;
- whether checkout on the Windows runner converts line endings to CRLF (`core.autocrlf`), which changes the
  text that `linecap.py`, `dashcheck.py`, `prosecheck.py` and the line number tests read;
- that `repo_files` in `sources.py` and the tests that create files under `tmp_path` handle `\` in paths;
- which tests fail on Windows or macOS. Two in `test_scripts_commitlint_editor.py` and two in
  `test_gamelib_scan.py` already skip on Windows, and one in `test_instancelock.py` runs only on Linux. A test
  that fails needs a fix or a skip with its reason;
- that the 80% branch coverage floor holds on each runner.

**Node 20.** The log of the last CI run on `master` before 2026-10-21 warns that `actions/checkout` v4,
`actions/setup-python` v5 and `actions/upload-artifact` v4 run on Node 20, which GitHub has deprecated.
`actions/download-artifact` v4 and `ncipollo/release-action` v1 were not checked. Dependabot opens a pull request
for each newer major. Read each major's release notes before merging it: the release job's `artifacts/*/*` depends
on the folders that `actions/download-artifact` creates.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the workflow's permissions, release conditions and action references were
  changed. The Windows and macOS runners and Python 3.13 could not be run there.
