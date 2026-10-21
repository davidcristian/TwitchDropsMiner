# Running from source and building

This page explains how to run Twitch Drops Miner from source, how to preview the GUI, and how to build the
executables. The release builds come from [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), so that file
is the reference when this page and a build disagree. For problems while running the app, see
[troubleshooting.md](troubleshooting.md).

## Requirements

- Python 3.10 or newer, and `main.py` stops on an older version. CI runs the checks on Python 3.10 and builds
  the PyInstaller releases with Python 3.14 (see [Release builds](#release-builds)).
- On Debian and Ubuntu, `python3 -m venv` needs the `python3-venv` package.
- On Linux, `tkinter` and the tray icon libraries come from system packages. CI installs these on Ubuntu 22.04:

  ```bash
  sudo apt install libgirepository1.0-dev gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1 python3-tk
  ```

  `requirements.txt` installs PyGObject on Linux for the tray icon, and pip compiles it from source with the
  headers from `libgirepository1.0-dev`. If pip fails while it builds PyGObject or pycairo, also install a C
  compiler, `pkg-config` and the cairo development package. Other distributions name these packages differently.

## Set up the environment

Run `setup_env.bat` on Windows or `./setup_env.sh` on Linux and macOS. The script:

1. creates the `env/` virtual environment if it does not exist, with `python` on Windows and `python3` elsewhere;
2. upgrades pip, then installs `wheel` and everything in `requirements.txt` into `env/`.

Run the script again after `requirements.txt` changes. It keeps the existing `env/` and installs the new packages.

## Run from source

On Windows, run `run_dev.bat`. It asks `Start with a console? (y/n)`. With `y` it starts `main.py` with
`env\scripts\python`, which opens a console window. With any other answer it uses `pythonw`, which does not.

On Linux and macOS there is no script. Start the app with the environment's Python:

```bash
env/bin/python main.py
```

The command line flags, such as `-vvv --log`, are listed in
[troubleshooting.md](troubleshooting.md#command-line-flags). A run from source keeps `settings.json`,
`cookies.jar` and the other app files in the repository folder. Git ignores them.

## Preview the GUI

```bash
env/bin/python gui.py
```

This opens the window with mock data, so a GUI change can be checked without logging in. It sends no GQL
request, but it downloads two images for the mock campaign from Twitch's image server, `static-cdn.jtvnw.net`,
and saves them in `cache/`. On Windows, use `env\scripts\python gui.py`. A new setting also needs an entry in
the mock at the end of `gui.py`; see the recipe in [AGENTS.md](../AGENTS.md#recipes). To run it without a
display, see [runbooks/gui-preview-headless.md](runbooks/gui-preview-headless.md).

## Run the checks

`just check` runs every check that a change must pass, as listed in
[AGENTS.md](../AGENTS.md#what-every-change-must-pass). Its tools are in `requirements-dev.txt`, which no build
installs. Install them into `env/` once, then activate the environment so that `just` and the recipes use its
Python:

```bash
env/bin/python -m pip install -r requirements-dev.txt
source env/bin/activate
just check
```

On Windows, run `env\scripts\python -m pip install -r requirements-dev.txt`, then `env\scripts\activate` and
`just check`. The recipes run `python3` on Linux and macOS and `python` on Windows.

`just check` stops at the first check that fails. `just --list` shows each check's own recipe, such as
`just check-tests` for the test suite alone. To run `just check` before each commit and check each commit
message, install the git hooks once, in the activated environment:

```bash
pre-commit install
```

The Validate job in CI installs `requirements-dev.txt` on Python 3.10 and runs `just check`, and the build jobs
start only when it passes. It runs on Ubuntu only. [Task 046](refinements/tasks/046-checks-run-only-on-linux-and-python-3-10.md)
lists what running it on Windows, macOS and Python 3.14 needs.

## Build the executable with PyInstaller

Run `build.bat` on Windows or `./build.sh` on Linux and macOS. The script:

1. stops with `No virtual environment found!` when `env/` does not exist;
2. installs PyInstaller into `env/` the first time. `build.bat` then also runs pywin32's post-install script;
3. runs `pyinstaller build.spec`.

The executable ends up in `dist/`, and PyInstaller keeps its intermediate files in `build/`. PyInstaller creates
both in the current folder, so run the script from the repository folder. Pass `--nopause` to either script to
skip the `Press any key` prompts, for example when another script calls it.

`build.spec` finds `icons/` and `lang/` in its own folder, which PyInstaller passes to it as `SPECPATH`. It
bundles every `lang/*.json` file except `English.json`, and the build fails with `FileNotFoundError` when
`lang/` has no other file.

These settings at the top of `build.spec` change the build:

| Setting | Effect |
| --- | --- |
| `upx` | Compresses the executable with UPX. The file is smaller, but more antivirus engines may report it. |
| `console` | Adds a console window, which helps with debugging. |
| `one_dir` | Builds a folder of files instead of a single executable. |
| `optimize` | `1` removes `assert` statements, `2` also removes docstrings. |

On Linux, `build.spec` bundles `libayatana-appindicator3.so.1` and the `AyatanaAppIndicator3-0.1` typelib from
the first of `/usr/lib/<arch>-linux-gnu`, `/usr/lib64` and `/usr/lib` that has the library, so install the tray
packages above before you build. CI also builds libXft 2.3.9 from source and runs PyInstaller under `xvfb-run`;
the `linux-pyinstaller` job in `ci.yml` shows both steps.

On macOS, `build.spec` also creates a `.app` bundle in `dist/`. CI runs `pyinstaller build.spec --noconfirm`
there instead of `build.sh`.

## Package the Windows build

`pack.bat` copies `dist\*.exe`, `manual.txt`, `LICENSE` and `LICENSE.MIT` into a `Twitch Drops Miner` folder,
puts that folder into `Twitch Drops Miner.zip`, tests the archive and deletes the folder. It needs `7z.exe` in the
current folder and skips the packaging without it. CI does not use `pack.bat`; it creates its zip file with
PowerShell.

## Build the AppImage

The `linux-appimage` job in `ci.yml` builds the AppImage on Ubuntu 22.04 with
[appimage-builder](https://appimage-builder.readthedocs.io/) and the recipe in
[`appimage/AppImageBuilder.yml`](../appimage/AppImageBuilder.yml). The recipe:

- takes its system packages, including `python3-tk` and `gir1.2-ayatanaappindicator3-0.1`, from the Ubuntu 22.04
  archives, and fetches the key that signs them from `keyserver.ubuntu.com` over HTTPS;
- builds libXft 2.3.9, because the app does not start with libXft 2.3.3 when an emoji font is installed. It
  prints the SHA-256 of the downloaded archive but compares it with nothing
  ([task 047](refinements/tasks/047-unchecked-build-downloads.md));
- copies the top-level `*.py` files, `gamelib/`, `lang/` and `icons/` into `usr/src` inside the image, starts
  `usr/src/main.py`, and installs `requirements.txt`. The app counts as an AppImage only when `constants.py` is
  inside the image ([constants.md](modules/constants.md#working-directory-and-paths));
- sets no update information and no signing key, so the AppImage has neither.

The job installs appimage-builder from a fixed commit, sets the `ARCH`, `ARCH_APT` and `APP_VERSION` environment
variables, and runs:

```bash
appimage-builder --recipe appimage/AppImageBuilder.yml
```

A new package folder must be added to the recipe's `cp` and `compileall` lines, as the recipe in
[AGENTS.md](../AGENTS.md#recipes) explains.

## Release builds

CI runs on every push to `master`, on every pull request and when it is started by hand. It builds for
Windows, macOS, Linux with PyInstaller and Linux as an AppImage, both Linux builds for `x86_64` and `aarch64`,
and appends the short commit hash to the version in `version.py`. Each build's zip file contains a
`Twitch Drops Miner` folder with the build, `manual.txt`, `LICENSE` and `LICENSE.MIT`. After a run on `master`,
from a push or started by hand, CI replaces the `dev-build` pre-release on the
[Releases page](https://github.com/davidcristian/TwitchDropsMiner/releases) with the new builds and sets the
`dev-build` tag to the commit it built. A run for a pull request, or started by hand on another branch, builds
but publishes nothing.

Two variables in `ci.yml` set the Python versions. The Validate job uses `PYTHON_VERSION`, 3.10, the oldest
version the app supports. The Windows, macOS and Linux PyInstaller builds use `BUILD_PYTHON_VERSION`, 3.14,
because each executable bundles that Python and its OpenSSL, and python.org publishes Windows and macOS builds
of a version only during its bugfix phase. The AppImage takes Python 3.10 from the Ubuntu 22.04 archives.
[ADR-0015](adr/ADR-0015-release-build-python.md) says why and when the build version changes.

GitHub runs one run at a time in each concurrency group, and the workflow's `concurrency` key sets one group
per branch or pull request. A new run on a branch or pull request cancels the one in progress. A new run on
`master` waits for it instead, because a cancelled release job can stop after it deletes the pre-release and
before it creates the new one. GitHub keeps only the newest waiting run of a group, so the pre-release ends up
with the builds of the newest commit. The release job also has its own `dev-build` group, which never cancels,
so two release jobs never replace the pre-release at the same time.

The workflow sets `permissions: contents: read`, so its token can read the repository and nothing more,
whatever default the repository settings give the token. Only the release job, `update_releases_page`, sets
`contents: write`, which it needs to replace the pre-release.

Each `uses:` line in `ci.yml` names an action by the full commit SHA of a release, with the release tag in a
comment, so that a tag moved to other code does not change what a job runs.
[`.github/dependabot.yml`](../.github/dependabot.yml) has Dependabot check the actions once a week and open a
pull request that updates a SHA and its comment. Its commit subjects start with `ci:`, but its commit bodies list
links and commit hashes, which the [commit rules](../AGENTS.md#commits) do not allow, so rewrite the message
when you merge such a pull request.

Before you open a pull request, run the checks in [AGENTS.md](../AGENTS.md#what-every-change-must-pass).
