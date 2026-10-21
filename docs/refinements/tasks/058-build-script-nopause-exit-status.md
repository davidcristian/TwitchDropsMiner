# `build.sh --nopause` exits with status 1 after a successful build

**Status:** done 2026-10-22
**Area:** build
**Origin:** Found on 2026-10-21 while a local build checked `constraints.txt`: `./build.sh --nopause` printed
`Build completed successfully.` and exited with status 1
**Verified:** 2026-10-22

[building.md](../../building.md#build-the-executable-with-pyinstaller) says to pass `--nopause` to `build.sh`
when another script calls it. The last line of `build.sh` is
`[ "$1" != "--nopause" ] && read -p "Press any key to continue..."`. With `--nopause` the test fails, so that line
returns status 1, and so does the script. A script that checks the status of `./build.sh --nopause` sees a
successful build as a failure. With a stub `pyinstaller` that exits with 0, `build.sh --nopause` printed
`Build completed successfully.` and returned 1.

`build.bat` ends with `if not "%~1"=="--nopause" pause`. Its status on Windows was not checked.

## What a fix involves

End `build.sh` with `exit 0` after the prompt, or write the prompt as an `if` statement, and check the status of
a build with and without `--nopause`. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while a local build with `build.sh` checked the versions in `constraints.txt`.
- 2026-10-22: Done. The last line of `build.sh` set the status: the test of `$1` with `--nopause`, or the `read`
  of the prompt when no input came. `build.sh` and `setup_env.sh`, whose last `read` failed the same way, now end
  with `exit 0`. `tests/test_build_scripts.py` runs a copy of each with stub tools in `env/bin` and no input.
  `build.bat` is unchanged and still unchecked on Windows.
