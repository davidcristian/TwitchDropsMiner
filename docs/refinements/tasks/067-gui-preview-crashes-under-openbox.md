# The GUI preview often crashes at start under the window manager openbox

**Status:** open
**Area:** gui
**Origin:** Found on 2026-10-22 while `python gui.py` ran from source with the X11 tray hosts of Ubuntu 22.04 under
Xvfb, with and without the window manager openbox
**Verified:** 2026-10-22

`python3 gui.py`, the preview with mock data ([building.md](../../building.md#preview-the-gui)), ended with a
segmentation fault within 15 seconds of its start in 27 of 57 starts under openbox 3.6.1, and in 1 of 32 starts
without a window manager. It ran on Ubuntu 22.04 with Python 3.10.12 and Tk 8.6.12, under Xvfb with no network.
`faulthandler` named `Tk.update`, called by the preview's `main` in `gui.py` while it adds the mock channels, as
the last Python call. It crashed with `PYSTRAY_BACKEND=dummy` too, in 3 of 3 starts, so the tray icon plays no
part.

The x86_64 PyInstaller build, started with `--tray` under openbox, did not crash in 3 of 3 starts, but its
window stays hidden at start. Not checked: `main.py` from source, the build without `--tray` under openbox,
other window managers, a desktop session and other Tk versions.

## What a fix involves

Find whether the crash is in Tk or in the way the preview calls it, from a core dump with the debug symbols of
Tk, and whether the app outside the preview crashes the same way. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed
  [task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md) was checked with the tray hosts of Ubuntu 22.04.
