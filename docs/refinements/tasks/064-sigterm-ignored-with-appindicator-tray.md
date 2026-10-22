# A SIGTERM leaves the app running while its AppIndicator tray icon is shown without a session bus

**Status:** open
**Area:** gui, main
**Origin:** Found on 2026-10-22 while the x86_64 build of the `linux-pyinstaller` job was started with `--tray`
in an Ubuntu 22.04 container with the GTK libraries it needs and no DBus session bus
**Verified:** 2026-10-22

On Linux, `main.py` handles SIGTERM with `GUIManager.close`, and the app then saves its files and ends. On
2026-10-22, the x86_64 PyInstaller build ran under Xvfb with no network in an Ubuntu 22.04 container with
`libwayland-client0`, `libwayland-cursor0`, `libwayland-egl1` and `libxcb-render0`, in which pystray's
AppIndicator backend loads. The container ran no DBus session bus. A SIGTERM went to the app 20 seconds after
the start:

| Start | Tray backend | Result |
| --- | --- | --- |
| no flag | AppIndicator | ended 2 seconds after the SIGTERM, status 0 |
| `--tray` | AppIndicator | still running 30 seconds after the SIGTERM |
| `--tray`, without the four libraries | X11 (`xorg`) | ended 2 seconds after the SIGTERM, status 0 |

The build of the commit before `traybackend.py` was added gave the same first two results. In the second case,
`/proc/<pid>/maps` listed `libayatana-appindicator3.so.1`, standard error was empty, and no icon appeared in
the tray host `stalonetray`, because the AppIndicator library shows its icon through the session bus.

Not checked: whether a desktop with a session bus has the same problem, and where the app waits. An assumption
is that `asyncio.run` waits at exit for the thread of the default executor that runs `pystray.Icon.run`, whose
GTK main loop does not end.

## What a fix involves

Find where the app waits after the SIGTERM, for example with `py-spy dump` in a run from source, then end the
tray icon's main loop before the event loop closes. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the tray backend fallback that closed
  [task 061](061-linux-build-needs-wayland-libraries.md) was checked in the Linux builds.
