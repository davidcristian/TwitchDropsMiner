"""A canvas that scrolls a frame with scroll bars and the mouse wheel, and the size of a window that holds one."""
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from tkinter import ttk
from typing import NamedTuple

from mousewheel import wheel_events, wheel_scroll

# Tk's own bindings scroll these widgets or change their value on a wheel turn, so the area does not scroll then.
OWN_WHEEL_CLASSES = frozenset({"Listbox", "Text", "Treeview", "TCombobox"})


class Size(NamedTuple):
    width: int
    height: int


def needed_bars(content: Size, space: Size, bars: Size) -> tuple[bool, bool]:
    """Return whether the horizontal and the vertical bar are needed to show `content` in `space`.

    `space` is the size with no bar shown. `bars` is the width of the vertical bar and the height of the other.
    """
    horizontal = content.width > space.width
    vertical = content.height > space.height or horizontal and content.height > space.height - bars.height
    horizontal = horizontal or vertical and content.width > space.width - bars.width
    return horizontal, vertical


def fitted_size(wanted: Size, smallest: Size, largest: Size) -> Size:
    """Return `wanted` cut to `largest` on each axis, and never below `smallest`."""
    return Size(
        max(smallest.width, min(wanted.width, largest.width)),
        max(smallest.height, min(wanted.height, largest.height)),
    )


class ScrollArea:
    """A canvas in column 0 and row `row` of `master` that shows the frame `inner`, with a bar below and right of it.

    With `fit`, the canvas requests the size of `inner`, centers it in extra space, and shows a bar only when needed.
    """

    def __init__(self, master: tk.Misc, *, row: int, fit: bool = False) -> None:
        self._fit = fit
        self._collapsed = False
        self.canvas = tk.Canvas(master, scrollregion=(0, 0, 0, 0))
        self.canvas.grid(column=0, row=row, sticky="nsew")
        master.rowconfigure(row, weight=1)
        master.columnconfigure(0, weight=1)
        self._xscroll = ttk.Scrollbar(master, orient="horizontal", command=self.canvas.xview)
        self._xscroll.grid(column=0, row=row + 1, sticky="ew")
        self._yscroll = ttk.Scrollbar(master, orient="vertical", command=self.canvas.yview)
        self._yscroll.grid(column=1, row=row, sticky="ns")
        self.canvas.configure(xscrollcommand=self._xscroll.set, yscrollcommand=self._yscroll.set)
        self.canvas.bind("<Configure>", self.update_region)
        self.inner = ttk.Frame(self.canvas)
        self._item = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)
        self._wheel_events = wheel_events(self.canvas.tk.call("tk", "windowingsystem"), tk.TkVersion)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        if fit:
            self.canvas.configure(borderwidth=0, highlightthickness=0)
            self._xscroll.grid_remove()
            self._yscroll.grid_remove()
            self.inner.bind("<Configure>", self.update_region)
            self.canvas.bind("<Map>", self.update_region)

    def configure_theme(self, *, bg: str) -> None:
        self.canvas.configure(bg=bg)

    def update_region(self, event: tk.Event[tk.Misc] | None = None) -> None:
        """Set the scroll region to the content, and with `fit` the canvas size, the bars and the content position."""
        self.canvas.update_idletasks()
        if not self._fit:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            return
        content = Size(self.inner.winfo_reqwidth(), self.inner.winfo_reqheight())
        request = Size(1, 1) if self._collapsed else content
        self.canvas.configure(width=request.width, height=request.height)
        # before its first layout the canvas has no size to compare with
        if self.canvas.winfo_ismapped() and not self._collapsed:
            self._show_needed_bars(content)
        view = Size(self.canvas.winfo_width(), self.canvas.winfo_height())
        self.canvas.coords(
            self._item, max(0, (view.width - content.width) // 2), max(0, (view.height - content.height) // 2)
        )
        region = (0, 0, max(view.width, content.width), max(view.height, content.height))
        self.canvas.configure(scrollregion=region)

    def _show_needed_bars(self, content: Size) -> None:
        bars = Size(self._yscroll.winfo_reqwidth(), self._xscroll.winfo_reqheight())
        space = Size(
            self.canvas.winfo_width() + (bars.width if self._yscroll.winfo_manager() else 0),
            self.canvas.winfo_height() + (bars.height if self._xscroll.winfo_manager() else 0),
        )
        for bar, needed in zip((self._xscroll, self._yscroll), needed_bars(content, space, bars)):
            if needed:
                bar.grid()
            else:
                bar.grid_remove()

    @contextmanager
    def collapsed(self) -> Iterator[None]:
        """With `fit`, make the canvas request 1 by 1 pixels in the block, so the window's request leaves it out."""
        self._collapsed = True
        self.canvas.configure(width=1, height=1)
        try:
            yield
        finally:
            self._collapsed = False
            self.update_region()

    def _bind_wheel(self, event: tk.Event[tk.Canvas]) -> None:
        for sequence in self._wheel_events:
            self.canvas.bind_all(sequence, self._on_mousewheel)

    def _unbind_wheel(self, event: tk.Event[tk.Canvas]) -> None:
        for sequence in self._wheel_events:
            self.canvas.unbind_all(sequence)

    def _on_mousewheel(self, event: tk.Event[tk.Misc]) -> None:
        if isinstance(event.widget, tk.Misc) and event.widget.winfo_class() in OWN_WHEEL_CLASSES:
            return
        scroll = wheel_scroll(event.delta, event.num, event.state)
        if scroll.axis == "x":
            self.canvas.xview_scroll(scroll.units, "units")
        else:
            self.canvas.yview_scroll(scroll.units, "units")


class MinimumSize:
    """Keep the minimum size of `window` at the size its `content` requests while each of `shrink` is in effect.

    `content` fills `window` through `grid`. `watched` are the widgets whose requested size the minimum includes.
    """

    def __init__(
        self,
        window: tk.Tk,
        content: tk.Misc,
        watched: Sequence[tk.Misc],
        shrink: Sequence[Callable[[], AbstractContextManager[object]]],
    ) -> None:
        self._window = window
        self._content = content
        self._watched = watched
        self._shrink = shrink
        self._sizes: list[Size] = []

    def _watched_sizes(self) -> list[Size]:
        return [Size(widget.winfo_reqwidth(), widget.winfo_reqheight()) for widget in self._watched]

    def measure(self) -> None:
        """Set the minimum size to the size that the content requests inside every context of `shrink`."""
        self._window.update_idletasks()
        self._sizes = self._watched_sizes()
        # without propagation the window keeps its size, so it does not shrink and grow back during the measurement
        self._window.grid_propagate(False)
        try:
            with ExitStack() as stack:
                for shrink in self._shrink:
                    stack.enter_context(shrink())
                self._window.update_idletasks()
                self._window.minsize(self._content.winfo_reqwidth(), self._content.winfo_reqheight())
            # the content requests its full size again before the window follows it
            self._window.update_idletasks()
        finally:
            self._window.grid_propagate(True)

    def follow(self) -> None:
        """Measure again when a watched widget requests a new size, for which Tk sends no event."""
        if self._watched_sizes() != self._sizes:
            self.measure()
