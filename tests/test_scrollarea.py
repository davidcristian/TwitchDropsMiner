from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pytest

from scrollarea import MinimumSize, ScrollArea, Size, fitted_size, needed_bars

BARS = Size(15, 15)
CONTENT = Size(400, 300)


@pytest.mark.parametrize(
    ("space", "expected"),
    [
        (Size(400, 300), (False, False)),
        (Size(500, 400), (False, False)),
        (Size(399, 400), (True, False)),
        (Size(500, 299), (False, True)),
        # the horizontal bar leaves 295 pixels of height, and the vertical one 395 of width
        (Size(399, 310), (True, True)),
        (Size(410, 299), (True, True)),
        (Size(399, 299), (True, True)),
    ],
)
def test_a_bar_is_needed_when_the_content_is_larger_than_the_space_beside_the_other_bar(space, expected):
    assert needed_bars(CONTENT, space, BARS) == expected


@pytest.mark.parametrize(
    ("wanted", "expected"),
    [
        (Size(800, 600), Size(800, 600)),
        (Size(1500, 600), Size(1300, 600)),
        (Size(800, 900), Size(800, 700)),
        (Size(1500, 900), Size(1300, 700)),
    ],
)
def test_fitted_size_cuts_the_wanted_size_to_the_largest_size(wanted, expected):
    assert fitted_size(wanted, Size(500, 400), Size(1300, 700)) == expected


def test_fitted_size_is_never_below_the_smallest_size():
    assert fitted_size(Size(1500, 900), Size(1400, 800), Size(1300, 700)) == Size(1400, 800)


@pytest.fixture
def root(display):
    root = tk.Tk()
    yield root
    root.destroy()


def fitted_area(root: tk.Tk, window: Size | None = None) -> ScrollArea:
    """Return a fitted area with content of the CONTENT size, in a window of the `window` size or its own size."""
    area = ScrollArea(root, row=0, fit=True)
    ttk.Frame(area.inner, width=CONTENT.width, height=CONTENT.height).grid()
    if window is not None:
        root.geometry(f"{window.width}x{window.height}")
    root.update()
    return area


def shown_bars(area: ScrollArea) -> tuple[bool, bool]:
    return bool(area._xscroll.winfo_ismapped()), bool(area._yscroll.winfo_ismapped())


def test_a_fitted_area_in_a_window_of_its_own_size_shows_all_its_content_and_no_bar(root):
    area = fitted_area(root)

    assert (area.canvas.winfo_width(), area.canvas.winfo_height()) == CONTENT
    assert shown_bars(area) == (False, False)


@pytest.mark.parametrize(
    ("window", "bars"),
    [(Size(300, 340), (True, False)), (Size(440, 200), (False, True)), (Size(300, 200), (True, True))],
)
def test_a_fitted_area_in_a_smaller_window_shows_the_bars_it_needs_and_scrolls_to_the_content_end(root, window, bars):
    area = fitted_area(root, window)
    canvas = area.canvas
    view = Size(canvas.winfo_width(), canvas.winfo_height())
    # the theme sets the size of a bar, such as 15 pixels on X11 and 17 on Windows
    shown = Size(area._yscroll.winfo_width() * bars[1], area._xscroll.winfo_height() * bars[0])
    canvas.xview_moveto(1)
    canvas.yview_moveto(1)

    assert shown_bars(area) == bars
    assert view == (window.width - shown.width, window.height - shown.height)
    assert (canvas.canvasx(view.width), canvas.canvasy(view.height)) == (
        max(CONTENT.width, view.width),
        max(CONTENT.height, view.height),
    )


def test_a_fitted_area_centers_content_smaller_than_the_window(root):
    area = fitted_area(root, Size(600, 500))

    assert shown_bars(area) == (False, False)
    assert (area.inner.winfo_x(), area.inner.winfo_y()) == (100, 100)


def test_a_collapsed_area_leaves_its_content_out_of_the_requested_size(root):
    area = fitted_area(root)
    with area.collapsed():
        root.update_idletasks()
        collapsed = (root.winfo_reqwidth(), root.winfo_reqheight())
    root.update_idletasks()

    assert collapsed == (1, 1)
    assert (root.winfo_reqwidth(), root.winfo_reqheight()) == CONTENT


def test_the_wheel_scrolls_the_area_but_not_over_a_list_inside_it(root):
    area = ScrollArea(root, row=0, fit=True)
    listbox = tk.Listbox(area.inner)
    listbox.grid()
    ttk.Frame(area.inner, width=100, height=2000).grid()
    root.geometry("300x200")
    root.update()
    area.canvas.event_generate("<Enter>")
    tops = []
    for widget in (listbox, area.canvas):
        widget.event_generate("<MouseWheel>", delta=-120)
        tops.append(area.canvas.yview()[0])

    assert tops[0] == 0 < tops[1]


def minimum_window(root: tk.Tk) -> tuple[MinimumSize, ttk.Frame]:
    """Return the minimum size of a window that holds a fitted area of the CONTENT size and a frame of 200 by 100."""
    content = ttk.Frame(root)
    content.grid(sticky="nsew")
    pane = ttk.Frame(content)
    pane.grid(column=0, row=0, sticky="nsew")
    area = ScrollArea(pane, row=0, fit=True)
    ttk.Frame(area.inner, width=CONTENT.width, height=CONTENT.height).grid()
    watched = ttk.Frame(content, width=200, height=100)
    watched.grid(column=1, row=0)
    minimum = MinimumSize(root, content, [watched], [area.collapsed])
    minimum.measure()
    root.update()
    return minimum, watched


def test_the_minimum_size_is_the_requested_size_with_the_area_collapsed(root):
    minimum_window(root)

    assert root.minsize() == (1 + 200, 100)
    assert (root.winfo_width(), root.winfo_height()) == (CONTENT.width + 200, CONTENT.height)


def test_measuring_the_minimum_size_does_not_resize_a_window_that_follows_its_requested_size(root):
    minimum, _watched = minimum_window(root)
    resizes = []
    # a binding on the window also receives the events of the widgets inside it
    root.bind("<Configure>", lambda event: event.widget is root and resizes.append((event.width, event.height)))
    minimum.measure()
    root.update()

    assert resizes == []


def test_the_minimum_size_follows_a_watched_widget_that_requests_a_new_size(root):
    minimum, watched = minimum_window(root)
    watched.configure(width=300, height=50)
    root.update_idletasks()
    minimum.follow()

    assert root.minsize() == (1 + 300, 50)


def test_a_resized_window_is_not_measured_again(root):
    minimum, _watched = minimum_window(root)
    root.geometry("700x400")
    root.update()
    root.minsize(1, 1)
    # Tk on Windows and macOS reports at least the smallest size that the window manager allows
    smallest = root.minsize()
    minimum.follow()

    assert root.minsize() == smallest
