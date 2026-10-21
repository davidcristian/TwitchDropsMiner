# The window is taller than a screen of 720 pixels

**Status:** open
**Area:** gui (the Main tab)
**Origin:** Found on 2026-10-21: the preview was measured on screens of 1366 by 768 and 1280 by 720 pixels
**Verified:** 2026-10-21

The Settings tab scrolls ([scrollarea.md](../../modules/scrollarea.md)), so the Main tab sets the height of the
window: the Status, Websocket Status, Login Form, Campaign Progress and Channels sections, and the Output box
below them. `GUIManager.apply_theme` sets the minimum window size from it, and `_fit_to_screen` never opens the
window below that minimum. Under Xvfb with the network blocked, the preview measured:

```text
                   Main tab   window minimum   wm maxsize on 1280 x 720
light mode         911 x 660  867 x 704        1265 x 690
dark mode          922 x 693  880 x 738        1265 x 690
```

On a screen 1280 by 720 pixels the dark mode window is 738 pixels high, so its lower 18 pixels, with half of
the Settings tab's scroll bar, are below the screen. The light mode window fits Xvfb, which draws no title bar,
but not the 690 pixels that `wm maxsize` leaves for it. On Windows a taskbar of about 40 pixels and a title bar
of about 30 leave about 698 pixels of a 768 pixel screen, less than both heights. That is an estimate: Windows
draws other fonts, and the window was not measured there.

## What a fix involves

A shorter Main tab: fewer lines in the Output box or the channel table, or the Main tab in a `ScrollArea` with
`fit` like the Settings tab. Either changes how the Main tab looks on every screen, which the maintainer
chooses and checks on Windows. Twitch requests: none.

## History

- 2026-10-21: Opened. After the Settings tab started to scroll, the preview fitted the width of a 1280 by 720
  screen but not the height in dark mode.
