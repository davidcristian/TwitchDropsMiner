# The Windows and macOS checks in CI have never run and are not required

**Status:** open
**Area:** ci, repo checks
**Origin:** Found on 2026-10-21: the Validate job in `.github/workflows/ci.yml` has one runner and one Python
**Verified:** 2026-10-21

The Validate job in `.github/workflows/ci.yml` runs `just check` four times
([ADR-0012](../../adr/ADR-0012-check-command.md)): on `ubuntu-latest` with `PYTHON_VERSION` (3.10) and with
`BUILD_PYTHON_VERSION` (3.14), which must pass, and on `windows-latest` and `macos-latest` with `PYTHON_VERSION`,
whose matrix entries set `required: false`, so that the job sets `continue-on-error` for them. The Windows and
macOS runs were added without a run, because neither system was available where they were written. So no check
has passed yet with:

- the `cmd.exe` shell that the `justfile` sets with `windows-shell`, and its `python` in place of `python3`;
- the tests and scans on Windows paths and the macOS file system;
- the code that differs by platform on the platform it is written for, such as `launcher_indexes` in
  `gamelib/epic.py`, the lock in `instancelock.py`, and the WndProc hook and the macOS appearance in `gui.py`;
- the tests of the window on Tk without X11.

## What a fix involves

Set `required: true` on the Windows and macOS entries when a pull request run shows, for each:

- that `pip install -c constraints.txt -r requirements-dev.txt` installs every package at its set version. On
  2026-10-22, pip 26.2.1 resolved the app's packages in `constraints.txt` for Python 3.10 with a wheel of each for
  `win_amd64` and `macosx_11_0_arm64`. On 2026-10-21,
  `pip download --only-binary=:all:` for Python 3.10 found a wheel of each package for `win_amd64` and for
  `macosx_14_0_arm64`, with `rust-just` 1.58.0, ruff 0.16.10, pywin32 and the pyobjc packages that pystray
  needs on macOS. The `rust-just` wheels install `just.exe` and `just` as scripts.
- that the Python 3.10 of `actions/setup-python` has `tkinter` and a Tk that opens a window. Without `tkinter`,
  pytest fails to collect `tests/test_gui.py`; with a Tk that opens no window, the `display` fixture fails,
  because the `CI` variable is set.
- that the step that installs the official `just` release passes in Git Bash on Windows and on macOS, with
  its `sha256sum` or `shasum` check and its unpacking with Python, and that the next step, which runs in
  PowerShell on Windows, finds `just.exe` in the folder that step adds to `GITHUB_PATH`.
- whether checkout on Windows converts line endings to CRLF (`core.autocrlf`). On 2026-10-21, a checkout made
  with `core.autocrlf=true` on Linux passed every scan and the suite. The suite also passed with every text
  write ending its lines with CRLF, as Python does on Windows, except the two tests of a shell script hook,
  which skip on Windows.
- which tests fail. Two in `test_scripts_commitlint_editor.py`, two in `test_gamelib_scan.py` and those of the
  `unreadable` fixture skip on Windows, one in `test_instancelock.py` runs only on Linux, and the tests of the
  X11 wheel buttons skip on other windowing systems. Reading the other tests found three that may fail:
  - `test_an_appimage_reached_through_a_symlink_keeps_its_files_next_to_the_appimage_file` in
    `tests/test_constants.py` creates a symbolic link, which Windows allows only with the symlink privilege or
    Developer Mode.
  - The tests in `tests/test_instancelock.py` that start a second process. Windows locks are mandatory, and
    `lock_file` opens the file with truncation and writes to it before it locks it. Only a run shows that the
    second `lock_file` still returns `(None, None)` there.
  - The tests of the window that set a window size or compare positions, in `tests/test_gui.py`,
    `tests/test_gui_window.py` and `tests/test_scrollarea.py`, run for the first time outside Xvfb.

  A test that fails needs a fix or a skip with its reason.
- that the 80% branch coverage floor holds on each runner. A branch for another system counts as missed, so
  the total differs by runner.
- that a failing Windows or macOS run leaves the workflow passed and still starts the build jobs, which wait
  for all four runs.

When they are required, choose whether Windows and macOS also run on `BUILD_PYTHON_VERSION`, the Python that
their releases bundle ([ADR-0015](../../adr/ADR-0015-release-build-python.md)).

**Node 20.** The log of the last CI run on `master` before 2026-10-21 warns that `actions/checkout` v4,
`actions/setup-python` v5 and `actions/upload-artifact` v4 run on Node 20, which GitHub has deprecated. It is a
warning, and no step failed, so the versions stay with Dependabot, which opens a pull request for each newer
major ([building.md](../../building.md#release-builds)). Read each major's release notes before merging it: the
release job's `artifacts/*/*` depends on the folders that `actions/download-artifact` creates.
`actions/download-artifact` v4 and `ncipollo/release-action` v1 were not checked.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the workflow's permissions, release conditions and action references were
  changed. The Windows and macOS runners and Python 3.13 could not be run there.
- 2026-10-21: The release builds moved to Python 3.14, so the newer Python to check is 3.14 in place of
  3.13. `just check` passed on 3.14 locally.
- 2026-10-21: The Validate job became a matrix: Ubuntu with Python 3.10 and 3.14, both required, and Windows
  and macOS with 3.10, not required. `requirements-dev.txt` installs pywin32 on Windows, because `gui.py`
  imports it there. The title was "CI runs `just check` only on Linux with Python 3.10". On CPython 3.14.7,
  `just check` passed under `xvfb-run` (1212 passed, 6 skipped, 1 xfailed, 98% branch coverage) and without a
  display (1194 passed, 25 skipped), and `scripts/sources.py` read the same comments, docstrings and line
  numbers from every repo file as on 3.10.20 and 3.12.3. The task stays open until Windows and macOS are
  required.
- 2026-10-21: The Validate job installs the official `just` release in place of `rust-just`
  ([task 049](049-check-tools-from-third-party-sources.md)), so its first Windows and macOS run also shows
  that step.
- 2026-10-22: The Validate job installs `requirements-dev.txt` with `-c constraints.txt`
  ([ADR-0016](../../adr/ADR-0016-exact-dependency-versions.md)), so the Windows and macOS runs install the
  versions that the file sets.
- 2026-10-22: The two Ubuntu entries ran under act 0.2.89, as
  [runbooks/linux-ci-with-act.md](../../runbooks/linux-ci-with-act.md) describes, and passed. On Python
  3.10.22 and 3.14.9, `just check` reported 1650 passed and 10 skipped, with 98.08% and 98.15% branch
  coverage. Eight of the skips need a user other than root, which act uses. The Windows and macOS entries still
  have no run.
