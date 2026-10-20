# The window is wider than a screen of 1366 pixels

**Status:** open
**Area:** gui (`SettingsPanel`)
**Origin:** Found on 2026-10-21: the minimum window size was measured after the theme was applied
**Verified:** 2026-10-21

The Settings tab places four sections side by side below "Games Being Mined": General with Advanced, Priority,
Exclude and Detected Games. Their widths set the width of the window, because `GUIManager.apply_theme` sets the
minimum window size to the size the window requests. In the preview on Linux that minimum is 1539 by 704 pixels
in light mode and 1564 by 738 in dark mode. On a screen 1366 or 1280 pixels wide, the right side of the window,
with the Detected Games section, is off the screen.

## How it was confirmed

The preview (`python gui.py`) ran under Xvfb with the network blocked, with the English strings. Two other
places for Detected Games were tried by changing the `grid` calls in `SettingsPanel.__init__`. The minimum
size in light mode:

```text
four sections side by side             1539 x 704
Detected Games below the four sections 1231 x 972
Detected Games below Exclude           1238 x 930
```

## What a fix involves

Both other layouts fit a width of 1366 pixels but need more than 768 pixels of height, the height of the
common 1366 by 768 laptop screen, so neither is better there. A fix combines a move with less height
elsewhere, for example a shorter Games Being Mined table or shorter Priority and Exclude lists, or puts
Detected Games on a tab of its own. The General column is 559 pixels wide because of the warning text in
Advanced, so wrapping that text also narrows the window. Each option changes the layout of the Settings tab,
which the maintainer chooses and checks on Windows, where the fonts and widget sizes differ. None of them adds
a Twitch request.

## History

- 2026-10-21: Opened. The minimum window size moved to the end of `apply_theme`, and two other layouts for
  Detected Games were measured and not taken.
