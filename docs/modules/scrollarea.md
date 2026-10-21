# `scrollarea.py`

**Purpose.** The Inventory and Settings tabs show content that can be larger than the window, on a `tk.Canvas`
with two scroll bars. `ScrollArea` holds that canvas, its bars and its mouse wheel binding, so both tabs share
one implementation ([gui.md](gui.md#the-window)). The module also holds the two size calculations behind it as
functions of plain numbers, which `tests/test_scrollarea.py` runs without a display. Its other tests open
windows, so `just check` runs them under `xvfb-run` on Linux.

## Public contract

- `Size(width, height)` is a named tuple of pixels.
- `needed_bars(content, space, bars)` returns whether the horizontal and the vertical bar are needed, as a
  tuple of two booleans. `space` is the size with no bar shown, and `bars` is the width of the vertical bar and
  the height of the horizontal one. A bar is needed when the content is larger than the space along its axis,
  or larger than the space that the other bar leaves.
- `fitted_size(wanted, smallest, largest)` returns `wanted` cut to `largest` on each axis, and never below
  `smallest`. `GUIManager._fit_to_screen` uses it for the window size at start.
- `ScrollArea(master, *, row, fit=False)` grids the canvas in column 0 and row `row` of `master`, the
  horizontal bar below it and the vertical bar to its right, and gives that row and column the weight 1. The
  caller builds the content inside the frame `inner`.
  - `update_region()` sets the scroll region. It runs when the canvas changes size. The Inventory tab also
    calls it after it adds or filters campaigns.
  - `configure_theme(bg=...)` sets the canvas background, which ttk styles do not reach.
  - While the pointer is over the canvas, the area binds the events that `wheel_events` returns with
    `bind_all`, and `wheel_scroll` gives the axis and direction ([mousewheel.md](mousewheel.md)). A wheel turn
    over a widget whose class is in `OWN_WHEEL_CLASSES` (`Listbox`, `Text`, `Treeview`, `TCombobox`) does not
    scroll the area, because Tk's own bindings scroll that widget or change its value.
- Without `fit`, as on the Inventory tab, the canvas has Tk's default size and border, the content starts at
  the top left corner, the scroll region is the bounding box of the content, and both bars always show.
- With `fit`, as on the Settings tab:
  - The canvas has no border and requests the size of `inner`, so a window that follows its requested size
    shows all the content and no bar.
  - In a smaller window, each bar shows only when `needed_bars` says so. The area decides when the canvas or
    `inner` changes size and when the canvas is mapped, and not before the canvas is first mapped, because it
    has no size to compare with until then.
  - Content smaller than the canvas is centered in it, and the scroll region is the larger of the canvas and
    the content on each axis.
  - `collapsed()` is a context manager. Inside the `with` block the canvas requests 1 by 1 pixels, so the
    window's requested size leaves the content out. `GUIManager.apply_theme` reads the minimum window size
    inside it ([gui.md](gui.md#the-theme-and-dark-mode)).

**Dependencies.** Repo modules: `mousewheel`. Standard library: `tkinter`.
