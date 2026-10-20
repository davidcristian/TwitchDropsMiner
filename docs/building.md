# Running from source and building

This page explains how to run Twitch Drops Miner from source, how to preview the GUI, and how to build the
executables. The release builds come from [`.github/workflows/ci.yml`](../.github/workflows/ci.yml), so that file
is the reference when this page and a build disagree. For problems while running the app, see
[troubleshooting.md](troubleshooting.md).

## Requirements

- Python 3.10 or newer. CI builds with Python 3.10, and `main.py` stops on an older version.
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
start only when it passes.

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

`pack.bat` copies `dist\*.exe` and `manual.txt` into a `Twitch Drops Miner` folder, puts that folder into
`Twitch Drops Miner.zip`, tests the archive and deletes the folder. It needs `7z.exe` in the current folder and
skips the packaging without it. CI does not use `pack.bat`; it creates its zip file with PowerShell.

## Build the AppImage

The `linux-appimage` job in `ci.yml` builds the AppImage on Ubuntu 22.04 with
[appimage-builder](https://appimage-builder.readthedocs.io/) and the recipe in
[`appimage/AppImageBuilder.yml`](../appimage/AppImageBuilder.yml). The recipe:

- takes its system packages, including `python3-tk` and `gir1.2-ayatanaappindicator3-0.1`, from the Ubuntu 22.04
  archives;
- builds libXft 2.3.9, because the app does not start with libXft 2.3.3 when an emoji font is installed;
- copies the top-level `*.py` files, `gamelib/`, `lang/` and `icons/`, and installs `requirements.txt`.

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
and appends the short commit hash to the version in `version.py`. After a run that is not for a pull request,
CI replaces the `dev-build` pre-release on the
[Releases page](https://github.com/davidcristian/TwitchDropsMiner/releases) with the new builds. A pull request
builds but publishes nothing.

Before you open a pull request, run the checks in [AGENTS.md](../AGENTS.md#what-every-change-must-pass).
