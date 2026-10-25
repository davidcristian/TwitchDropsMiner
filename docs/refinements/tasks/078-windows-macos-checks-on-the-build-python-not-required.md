# The Windows and macOS checks on the build Python have not passed and are not required

**Status:** done 2026-10-25
**Area:** ci, repo checks
**Origin:** The close of [task 046](046-checks-run-only-on-linux-and-python-3-10.md), on 2026-10-25
**Verified:** 2026-10-25

The Validate job in `.github/workflows/ci.yml` runs `just check` on `windows-latest` and `macos-latest` with
`BUILD_PYTHON_VERSION` (3.14), the Python that the Windows and macOS releases bundle
([ADR-0015](../../adr/ADR-0015-release-build-python.md)). The two entries set `required: false`, so the job sets
`continue-on-error` for them and a failure there does not fail the workflow. They were added without a run.
Python 3.14 has behaved differently from the 3.10 of the required Windows and macOS runs before: its
`Path.is_dir` returns `False` where 3.10 raises `PermissionError`, which the Ubuntu run on 3.14 found.

## What a fix involves

Set `required: true` on both entries when a run shows, for each:

- that `pip install -c constraints.txt -r requirements-dev.txt` installs every package. On 2026-10-25,
  `pip download --only-binary=:all:` for CPython 3.14 found a wheel at its set version of each package for
  `win_amd64` and for `macosx_15_0_arm64`, with pywin32 on Windows and the pyobjc packages on macOS.
- that the Python 3.14 of `actions/setup-python` has `tkinter` and a Tk that opens a window.
- that the suite passes, or that a test that fails is fixed or skipped with its reason. On macOS this
  includes the strict `xfail` test of [task 072](072-macos-window-smaller-than-wm-maxsize.md), which fails
  when the window size result does not repeat on this Python.
- that the 80% branch coverage floor holds.

None of this sends a Twitch request.

## History

- 2026-10-25: Opened. The close of task 046 chose to run the Windows and macOS checks on the build Python too,
  not required until each has passed once.
- 2026-10-25: Closed. On Windows with Python 3.14.9, pip installed every package of `constraints.txt`,
  `tkinter` opened a window, and the suite passed with 2035 passed and 40 skipped, at 97.40% branch coverage.
  On macOS with Python 3.14.8, on the runner image of 2026-10-13, the suite passed with 2055 passed and 20
  skipped, at 97.88%, and the test of the window size at start passed with no `xfail` mark
  ([task 072](072-macos-window-smaller-than-wm-maxsize.md)). On the newer image with Python 3.14.9, Tk 9.0.4
  crashed when a test's Tk had been destroyed before it handled an event, and the test of the minimum window
  size failed by 8 pixels. The test fixtures now run `update_idletasks` before they destroy a Tk, and on macOS
  `GUIManager` measures the minimum size again after the window first shows. With both changes the suite passed
  on that image too, with 2055 passed and 20 skipped. Both entries now set `required: true`.
