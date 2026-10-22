# A SIGTERM to an AppImage that runs without FUSE leaves the app running

**Status:** open
**Area:** appimage
**Origin:** Found on 2026-10-22 while each AppImage of the `linux-appimage` job was started with
`APPIMAGE_EXTRACT_AND_RUN=1`: the `timeout` that ended the start left no `settings.json` next to the AppImage
**Verified:** 2026-10-22

Without FUSE, an AppImage started with `--appimage-extract-and-run` or `APPIMAGE_EXTRACT_AND_RUN=1` extracts its
files into `/tmp` and starts the app as a child process. A SIGTERM to the process that was started, which
`kill`, `pkill` with the file name or `timeout` sends, ends only the AppImage runtime. The runtime does not send
the signal on to the app, which keeps running with PID 1 as its parent. So the SIGTERM handler in `main.py` does
not run, and the app writes no `settings.json` or `cookies.jar` until it is closed in another way. Through FUSE,
the started process is the app itself, and a SIGTERM closes it.

On 2026-10-22, the `x86_64` AppImage, with the type2-runtime release `20251108`, ran under Xvfb with no network
in an Ubuntu 22.04 container
([runbook](../../runbooks/linux-ci-with-act.md#start-an-appimage)). A SIGTERM went to the started process 20
seconds after the start:

- With `APPIMAGE_EXTRACT_AND_RUN=1`, the runtime ended. Its child `usr/bin/python3 usr/src/main.py` was still
  running 15 seconds later, and the folder had no `settings.json`.
- Through FUSE, with `fuse3` installed and the container started with `--device /dev/fuse --cap-add SYS_ADMIN`,
  the started process was `usr/bin/python3 usr/src/main.py`. It ended within 15 seconds and wrote
  `settings.json` and `cookies.jar`.

The `continuous` runtime was not checked. A system without FUSE needs the extract mode, and the README and
[troubleshooting.md](../../troubleshooting.md) do not mention it.

## What a fix involves

One of:

- Write in troubleshooting.md that without FUSE the app is closed from its window or tray icon, or with a signal
  to its Python process.
- Move to a runtime release that sends the signal on to the app, if type2-runtime publishes one. Its source
  shows whether a release does.

None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while each AppImage of the `linux-appimage` job was started under act with no
  network.
