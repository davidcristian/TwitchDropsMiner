# A SIGTERM to an AppImage that runs without FUSE leaves the app running

**Status:** done 2026-10-22
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
- 2026-10-22: Closed. In the type2-runtime source, `20251108` and the `continuous` build of 2026-10-19, the only
  other release, differ only in the mode of the folders they create. In the extract mode both fork, start
  AppRun in the child and wait in `waitpid` with no signal handler. No release passes a signal on, so
  [parentexit.py](../../modules/parentexit.md) has the kernel send the app SIGTERM when its parent, the
  runtime, ends. `timeout` signals its whole process group, so under `timeout` the app also gets the SIGTERM
  directly: the build without the change wrote both files, and one with only `parentexit.py` wrote no
  `settings.json` in 3 of 3 starts, because the second SIGTERM came after `main.py` had removed its handler.
  `main.py` now keeps that handler until the loop closes. Built under act, the x86_64 AppImage with
  `APPIMAGE_EXTRACT_AND_RUN=1` ended 2 seconds after a SIGTERM to the started process and wrote
  `settings.json` and `cookies.jar`, where the build without the change still ran 30 seconds later. It wrote
  both under `timeout` in 3 of 3 starts, and through FUSE it ended after 1 second with both files. The start in
  the [act runbook](../../runbooks/linux-ci-with-act.md) left no `settings.json` because its container ended
  with the runtime; it now waits for the app. Under QEMU, the aarch64 AppImage requests nothing, because
  `/proc/<pid>/exe` names `qemu-aarch64`; a native arm64 system was not checked.
  [troubleshooting.md](../../troubleshooting.md) names the extract mode.
