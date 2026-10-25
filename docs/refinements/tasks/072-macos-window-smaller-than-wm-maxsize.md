# On macOS the window opens 20 pixels smaller than `wm maxsize`

**Status:** done 2026-10-25
**Area:** gui
**Origin:** Found on 2026-10-22: the first macOS run of the Validate job in CI
**Verified:** 2026-10-25

`GUIManager.__init__` calls `_fit_to_screen` while the window is still withdrawn. When the window requests more
than `wm maxsize`, `_fit_to_screen` sets the window size to `fitted_size` of the two
([gui.md](../../modules/gui.md#the-theme-and-dark-mode)). In the tests under Xvfb the window requests 1543 by
704 pixels, so a screen 1024 pixels wide cuts at least its width.

On the `macos-26-arm64` runner image, with Python 3.10.11 from python.org, the window was 1004 by 629 pixels
after it opened, and the smaller of its requested size and `wm maxsize` was 1024 by 649. On X11 and Windows the
two are equal. `test_the_window_opens_at_its_requested_size_cut_to_the_largest_size_tk_allows` in
`tests/test_gui_window.py` checks that, and it is a strict `xfail` test on macOS until this is fixed. The window
fits the screen, but it is 20 pixels narrower and lower than it can be, and the Output box shows fewer lines.

The cause is not known, and the log does not show the requested size. On macOS, Tk 8.6.12 computes
`wm maxsize` from the visible frame of the screens less the offsets of the window's frame (`GetMaxSize` in
`macosx/tkMacOSXWm.c`). It reads those offsets when it creates the macOS window, so the value can differ between
the withdrawn window that `_fit_to_screen` measures and the shown window that the test measures. The window
manager can also make a window smaller when it shows it.

## What a fix involves

On a Mac, print `wm maxsize` while the window is withdrawn and after it shows, the requested size, and the
window size after it shows. If `wm maxsize` grows when the window shows, `_fit_to_screen` can run again on the
first `<Map>` event of the window. Then remove the `xfail` mark. Twitch requests: none.

## History

- 2026-10-22: Opened. The first macOS run of the Validate job failed the test of the window size at start. The
  same test passed on Windows.
- 2026-10-25: Closed. Runs on macOS in CI with Tk 8.6.12 and 9.0.4 showed the cause: Tk reports the state
  `zoomed` after `_fit_to_screen` sets the size to `wm maxsize` while the window is withdrawn, and at the first
  `<Map>` event the state becomes `normal` and the window shrinks by 20 pixels on each axis. On macOS,
  `GUIManager` now calls `_fit_to_screen` again through `after_idle` from the first `<Map>` event, which gave
  the full size in those runs, and the test of the window size at start has no `xfail` mark. The change
  itself ran only on Linux, with `refits_after_first_map` replaced to return true.
