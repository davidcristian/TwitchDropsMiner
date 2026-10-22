# The GUI preview often crashes at start under the window manager openbox

**Status:** done 2026-10-22
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
- 2026-10-22: Closed. The crash comes from libXft 2.3.4 and the color emoji font Noto Color Emoji, not from
  openbox or from a Tk call on another thread: at the crash, the only other thread was Tcl's notifier, in
  `select`. gdb with Ubuntu's debug symbols showed a segmentation fault in `_XReply` of libX11 1.7.5, on a freed
  pending request, called from `XSync` in `Tk_DeleteErrorHandler`, from `Tk_MeasureChars` for 🎁 in a
  `ttk::treeview` heading. Every X error before it was `BadLength` for `RenderAddGlyphs`, each for a 136 by 128
  glyph of Noto Color Emoji, six per start for ❌, ⏳, ➕, 🎁, 📋 and 🌐; Tk draws these blank. The same
  `BadLength` error for color emoji with libXft before 2.3.5 is
  [python/cpython#86391](https://github.com/python/cpython/issues/86391). The fix in `colorfonts.py` makes
  fontconfig leave out color fonts before Tk starts when libXft is older than 2.3.5
  ([colorfonts.md](../../modules/colorfonts.md)), so the symbols show as boxes or come from a font without
  color. Starts under Xvfb with no network, 20 seconds each, in counts of 30: `python3 gui.py` under openbox
  crashed in 22 before and 0 after, without a window manager in 4 before and 0 after; `python3 main.py` without
  `--tray` under openbox in 1 before and 0 after, and under gdb its six `BadLength` errors per start were gone
  after the fix. The preview did not crash with libXft 2.3.9 or without the emoji font. The x86_64 PyInstaller
  build, built under act and started without `--tray` under openbox, crashed in 0 of 30 before and 0 of 30
  after, because it loads the libXft 2.3.9 that CI builds, and after the fix it still shows the symbols in
  color. So a run from source with libXft before 2.3.5, such as on Ubuntu 22.04, was affected when a color font
  is the first font with these symbols; the release builds were not.
