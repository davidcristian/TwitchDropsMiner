# ADR-0015: The release builds use a newer Python than the checks

**Status:** Accepted (2026-10-21)

## Context

The app supports Python 3.10 and newer ([AGENTS.md](../../AGENTS.md#what-this-is)). Until this record, one
variable in `.github/workflows/ci.yml`, `PYTHON_VERSION`, set Python 3.10 for the Validate job and for the
Windows, macOS and Linux PyInstaller builds.

PyInstaller bundles the Python that runs it into the executable, with its `ssl` module and the OpenSSL that
module uses. On Windows and macOS, `actions/setup-python` installs the python.org builds. python.org publishes
Windows and macOS builds of a version only during its bugfix phase; the later security releases are source
only. So the Windows and macOS releases had Python 3.10.11 from April 2023, which bundles OpenSSL 1.1.1t.
OpenSSL 1.1.1 has had no public fixes since September 2023, and Python 3.10 reaches its end of life in October
2026. Every TLS connection the app makes to Twitch from those releases goes through that OpenSSL.

## Decision

1. **Two variables in `ci.yml`.** `PYTHON_VERSION`, `"3.10"`, is the oldest version the app supports. The
   Validate job runs on it on every runner, so a test or the import of a module that needs a newer Python fails
   there. `BUILD_PYTHON_VERSION`, `"3.14"`, is the Python of the Windows, macOS and Linux PyInstaller builds, and
   the Validate job also runs on it on Ubuntu ([ADR-0012](ADR-0012-check-command.md)). The Linux build follows
   the other two, so that the three releases run on one Python with one set of packages.
2. **The build version is 3.14.** Its bugfix phase lasts until October 2027 (PEP 745), so python.org still
   publishes Windows and macOS builds of each release, with the OpenSSL updates they include. The bugfix phase
   of 3.13 ends in October 2026 (PEP 719), and 3.12 and 3.11 get source releases only. 3.15 is due in October
   2026 (PEP 790), and neither it nor the packages in `requirements.txt` were checked on it.
3. **The build version moves before its bugfix phase ends,** to the newest version in its bugfix phase that
   PyInstaller and every package in `requirements.txt` support. Before the change, `just check` and the GUI
   preview run on that version. Raising the supported floor, `PYTHON_VERSION`, is a separate decision.

## Consequences

- The Validate job runs on the build Python on Ubuntu only, so no check runs it on Windows or macOS, where two
  of the releases bundle it.
- On 2026-10-21 the checks, the GUI preview and `main.py` ran on a local CPython 3.14.7 with `requirements.txt`
  and `requirements-dev.txt` installed: `just check` passed (1039 tests passed, 98% branch coverage), the GUI
  preview showed every tab, and `main.py` started and retried its connection with the network blocked. That
  Python was a uv build with Tk 9.0 and no Xft, so it drew some button symbols as other characters; the Tk of
  the release builds was not run.
- On that machine, PyGObject 3.50.2 compiled for 3.14, and Pillow, aiohttp, pystray and truststore installed.
  PyInstaller, pywin32 and the macOS packages were not installed there. Only a CI run shows that the three
  builds succeed, and only a start of each release shows that it runs.
- On 3.14, `Path.is_dir` returns `False` for a path inside a folder the user may not open, so the releases
  report such a game folder as holding no games, without the error
  ([gamelib.md](../modules/gamelib.md#the-scan)). The four tests of that error skip on 3.14.
- An assumption, not checked: the python.org 3.14 builds bundle OpenSSL 3.5, which gets fixes until April
  2030. After a CI run, the Windows log names the CPython release, and the release binaries contain the
  OpenSSL version as text.
- The AppImage does not change. Its recipe installs Python 3.10 and its libraries from the Ubuntu 22.04
  archives, which Ubuntu patches, and does not read the `PYTHON_VERSION` that the job passes to it.
- [Task 046](../refinements/tasks/046-checks-run-only-on-linux-and-python-3-10.md) lists what the Windows and
  macOS runs of the Validate job must show before they are required.

## Alternatives rejected

- **Raise the floor to 3.14 everywhere.** It ends support for running from source on 3.10 to 3.13, which is a
  decision of its own, and the releases do not need it.
- **Build on 3.12 or 3.13.** Their python.org Windows and macOS builds have stopped or stop in October 2026, so
  the releases would keep an OpenSSL that no longer gets updates, as 3.10 did.

## Related

- [building.md](../building.md#release-builds): the release builds and their Python.
- [ADR-0012](ADR-0012-check-command.md): the Validate job and `just check`.
- [Task 046](../refinements/tasks/046-checks-run-only-on-linux-and-python-3-10.md): the checks on Windows and
  macOS.
