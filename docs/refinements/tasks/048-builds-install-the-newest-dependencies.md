# The builds install the newest release of every dependency

**Status:** open
**Area:** build, ci, requirements
**Origin:** Found on 2026-10-21 while the release builds moved to Python 3.14: a new environment got Pillow
13.0.0 from `requirements.txt`, while the last release build had used Pillow 12.3.0
**Verified:** 2026-10-21

`requirements.txt` sets a range for aiohttp (`>=3.9,<4.0`) and an upper limit for PyGObject (`<3.51`), and no
version for Pillow, pystray, pywin32 or truststore. The build jobs in `.github/workflows/ci.yml`, `build.sh` and
`build.bat` install `pyinstaller` with no version. The CI jobs also install wheel, and the AppImage job and
recipe install pip, setuptools, setuptools_scm, meson and ninja, all with no version. So each build installs
the newest release on PyPI that day:

- a broken or malicious release of any of these packages, or of a package they depend on, goes into the next
  build;
- no release can be built again as it was, and nothing records the versions once the CI logs expire. The log of
  the last release build before 2026-10-21 lists Pillow 12.3.0, aiohttp 3.14.5 and PyInstaller 6.22.3.

`yarl` in `requirements-dev.txt` has no version either. An exact version there conflicts with the newest
aiohttp once that one requires a newer yarl: aiohttp 3.14.5 requires yarl 1.25.1 or newer, and `env/` had
yarl 1.24.5 with aiohttp 3.14.3.

## What a fix involves

Exact versions need real version and hash data from PyPI, which needs the network, and a rule for updating
them. The choices, to record in an ADR:

1. **A constraints file**, such as `constraints.txt`, with an exact version of every package that a build or
   the Validate job installs, the indirect ones included. The CI jobs, `setup_env`, `build.sh`, `build.bat` and
   the AppImage recipe pass `-c constraints.txt` to each `pip install`. `requirements.txt` keeps its ranges for
   a run from source, and `yarl` takes its version from the same file. A tool such as `pip-compile` or
   `uv pip compile` writes the file, and that tool goes in `requirements-dev.txt`, not in a build. The file
   covers every build platform (Windows, macOS, Linux `x86_64` and `aarch64`) and both Pythons: 3.14 for the
   PyInstaller builds and Ubuntu's 3.10 for the AppImage.
2. **Hashes with `--require-hashes`.** pip then stops with an error at any file whose hash is not listed, so a
   replaced file on PyPI fails the build. Every package needs an exact version and the hash of each wheel and
   sdist that any platform installs; PyGObject and pycairo are built from their sdists on Linux. Check with the
   pip version the jobs use whether it reads hashes from a constraints file or only from a requirements file.
3. **Dependabot for pip.** A `package-ecosystem: pip` entry in `.github/dependabot.yml`, next to the one for
   the actions, opens a pull request for each new version. Its commit messages need rewriting, as
   [building.md](../../building.md#release-builds) says for the actions. Without it, the versions are updated
   by hand on a fixed schedule.
4. **The update rule.** Each version is a release at least two weeks old when it is chosen, as
   [ADR-0012](../../adr/ADR-0012-check-command.md) sets for the tools, and the pull request that changes it runs
   every build. A security release can skip the two weeks.

Starting points for the first file: Pillow 12.3.0, aiohttp 3.14.5 and PyInstaller 6.22.3, the versions of the
last release build. Check each on Python 3.14 and 3.10 before writing it down.

None of this sends a Twitch request.

## History

- 2026-10-21: Opened. Found while the release builds moved to Python 3.14 and a new environment got a newer
  Pillow than the last release.
