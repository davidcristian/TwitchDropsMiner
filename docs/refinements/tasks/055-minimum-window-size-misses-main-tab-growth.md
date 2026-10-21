# The minimum window size does not follow the Main tab when it grows

**Status:** done 2026-10-22
**Area:** gui (`GUIManager`)
**Origin:** Found on 2026-10-21: the preview window was shrunk to its minimum size after its mock data arrived
**Verified:** 2026-10-22

`GUIManager.apply_theme` sets the minimum window size once, from the size the window requests without the
Settings tab's content ([gui.md](../../modules/gui.md#the-theme-and-dark-mode)). It runs when the window is
built and when the "Dark mode" checkbox changes. The widest tab that cannot scroll, the Main tab, grows later:
`ChannelList._adjust_width` widens a column for a long channel or game name, and the labels of
`CampaignProgress` and `LoginForm` change with their text.

In the preview under Xvfb, the Main tab requested 849 pixels when the minimum was set, so the minimum was 867 by
704 pixels. The mock data then widened it to 911. With the window shrunk to 867 pixels, the Main tab had 849
pixels, and the Viewers and 📋 columns of the channel table were cut off. Before the Settings tab scrolled, the
minimum width was 1543 pixels, wider than the Main tab, so this did not happen. A window that the user has not
resized follows its requested size and shows the whole Main tab.

## What a fix involves

Set the minimum again when a tab that cannot scroll requests a new size. Tk sends no event for a new requested
size, so the window compares the requested sizes of the Main, Inventory and Help tabs with the last ones, for
example in `GUIManager._poll`, and calls the code at the end of `apply_theme` when they differ. That code makes
the Settings canvas request 1 pixel for a moment, so a window that follows its requested size is resized twice
in one update; whether that shows as a flicker needs a check on Windows. Twitch requests: none.

## History

- 2026-10-21: Opened. After the Settings tab started to scroll, the minimum window size came from the Main
  tab, and the preview's Main tab grew after the minimum was set.
- 2026-10-22: Closed. `MinimumSize` in `scrollarea.py` measures the minimum with grid propagation off, so the
  window does not resize during the measurement, and `GUIManager._poll` calls its `follow` after each pass over
  the Tk events. In the preview under Xvfb, the minimum width became 928 pixels after the mock data arrived,
  and a window of that width showed the whole channel table. Windows was not run.
