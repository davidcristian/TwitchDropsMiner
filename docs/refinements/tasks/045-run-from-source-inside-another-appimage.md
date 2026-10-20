# A run from source started from another AppImage keeps its files in that AppImage's folder

**Status:** open
**Area:** constants
**Origin:** Found on 2026-10-21: a run from source with `APPIMAGE` in its environment counted as packaged
**Verified:** 2026-10-21

`IS_APPIMAGE` in `constants.py` is true when the `APPIMAGE` environment variable names an existing file. The
AppImage runtime sets it for the program in the image, and every process that program starts inherits it. So
`python main.py`, run in the terminal of an editor or a terminal app that is itself an AppImage, counts as
packaged: `SELF_PATH` is the other `.AppImage` file, and `WORKING_DIR` is its folder. `cookies.jar`, which holds
the login session, `settings.json`, `lock.file`, `log.txt` and `cache/` then go into the other app's folder.
The strict `xfail` test
`test_a_run_from_source_started_from_another_appimage_keeps_its_files_in_the_repo` in
`tests/test_constants.py` states the correct paths.

## What a fix involves

The AppImage documentation lists `APPDIR`, the folder the image is mounted at, among the variables that the
runtime sets together with `APPIMAGE`. The recipe in `appimage/AppImageBuilder.yml` starts
`${APPDIR}/usr/src/main.py`, so in the AppImage `sys.argv[0]` is inside `APPDIR`, and in a run from source it is
not. This check keeps the current result when `APPDIR` is not set, and makes the test above pass with the other
path tests unchanged:

```text
IS_APPIMAGE = APPIMAGE names a file
    and (APPDIR is not set or the resolved sys.argv[0] is inside the resolved APPDIR)
```

It was not made because it was not run in a real AppImage, and building one needs the network (the apt
packages and the libXft download in the recipe). If the `AppRun` of appimage-builder sets `APPDIR` to a folder
that does not hold the started `main.py`, the AppImage counts as a run from source, tries to write its files
inside the read only image and cannot start. To check a fix, start the AppImage that the `linux-appimage` CI job
builds and see `settings.json` and `lock.file` appear next to the `.AppImage` file, then run `python main.py`
from a terminal that another AppImage started and see them appear in the repo folder. The fix sends no Twitch
request.

## History

- 2026-10-21: Opened. A copy of `constants` loaded with `APPIMAGE` naming another AppImage put `COOKIES_PATH`
  in that AppImage's folder, and the `APPDIR` check above was not made without a real AppImage to run it in.
