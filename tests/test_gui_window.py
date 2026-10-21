from __future__ import annotations

import asyncio
import time
from tkinter.font import Font

import pytest

from channel import Channel
from fakes import FakeTwitch
from gui import ConsoleOutput, GUIManager


def output_lines(gui: GUIManager) -> int:
    """Return the number of whole lines that the Output box has room for."""
    text = gui.output._text
    border = sum(text.winfo_pixels(text.cget(option)) for option in ("borderwidth", "highlightthickness", "pady"))
    return (text.winfo_height() - 2 * border) // Font(font=text.cget("font")).metrics("linespace")


def shortened_panels(gui: GUIManager) -> list[str]:
    """Return the label of each panel of the Main tab that is shorter than it requests."""
    main = gui.output._text.master.master
    return [panel.cget("text") for panel in main.grid_slaves() if panel.winfo_height() < panel.winfo_reqheight()]


async def until(condition) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.01)


@pytest.mark.parametrize("dark", [False, True])
def test_the_minimum_window_size_is_the_size_of_the_theme_without_the_settings_tab_and_most_output(window, dark):
    fake = FakeTwitch()
    fake.settings.dark_mode = dark
    gui = window(fake)
    root, notebook, output = gui._root, gui.tabs._nb, gui.output._text

    def minimum_and_requested_without_settings() -> tuple[tuple[int, int], tuple[int, int]]:
        pane, text = notebook.tabs()[2], notebook.tab(2, "text")
        notebook.forget(2)
        output.configure(height=ConsoleOutput.MIN_LINES)
        root.update_idletasks()
        requested = (root.winfo_reqwidth(), root.winfo_reqheight())
        output.configure(height=ConsoleOutput.LINES)
        notebook.insert(2, pane, text=text, sticky="nsew")
        return root.minsize(), requested

    at_start = minimum_and_requested_without_settings()
    gui.apply_theme(not dark)
    after_the_change = minimum_and_requested_without_settings()

    assert at_start[0] == at_start[1]
    assert after_the_change[0] == after_the_change[1]


@pytest.mark.parametrize("dark", [False, True])
def test_a_window_at_its_minimum_height_shortens_only_the_output_box(window, dark):
    fake = FakeTwitch()
    fake.settings.dark_mode = dark
    gui = window(fake)
    root = gui._root
    root.geometry("{}x{}".format(*root.minsize()))
    root.update()

    assert output_lines(gui) == ConsoleOutput.MIN_LINES
    assert shortened_panels(gui) == ["Output"]


def test_a_window_taller_than_the_screen_opens_at_the_largest_height_with_a_shorter_output_box(window, monkeypatch):
    gui = window(FakeTwitch())
    root = gui._root
    root.update()
    largest = (root.maxsize()[0], root.winfo_reqheight() - 40)
    # Tk computes the largest size from the screen. Setting it with maxsize would also make Tk cut the window to it.
    monkeypatch.setattr(root, "maxsize", lambda: largest)
    gui._fit_to_screen()
    root.update()

    assert root.winfo_height() == largest[1]
    assert ConsoleOutput.MIN_LINES <= output_lines(gui) < ConsoleOutput.LINES
    assert shortened_panels(gui) == ["Output"]


def test_the_whole_main_tab_shows_at_the_minimum_window_size_after_a_long_channel_name(window):
    fake = FakeTwitch()
    gui = window(fake)
    root, main = gui._root, gui.tabs._nb.nametowidget(gui.tabs._nb.tabs()[0])
    root.update()
    width = main.winfo_reqwidth()

    async def scenario() -> None:
        gui.start()
        gui.channels.display(Channel(fake, id=1, login="c" * 30), add=True)
        # the poll task lays out the window and checks the minimum size in one step
        await until(lambda: main.winfo_reqwidth() > width)
        gui.stop()

    asyncio.run(scenario())
    root.geometry("{}x{}".format(*root.minsize()))
    root.update()

    assert main.winfo_width() >= main.winfo_reqwidth()


def test_setting_the_theme_again_does_not_resize_a_window_that_follows_its_requested_size(window):
    gui = window(FakeTwitch())
    root = gui._root
    root.geometry("")
    root.update()
    resizes = []
    root.bind("<Configure>", lambda event: event.widget is root and resizes.append((event.width, event.height)))
    gui.apply_theme(False)
    root.update()

    assert resizes == []


def test_the_window_opens_at_its_requested_size_cut_to_the_largest_size_tk_allows(window):
    root = window(FakeTwitch())._root
    root.update()
    largest = root.maxsize()

    assert (root.winfo_width(), root.winfo_height()) == (
        min(root.winfo_reqwidth(), largest[0]),
        min(root.winfo_reqheight(), largest[1]),
    )


def test_the_settings_tab_in_a_small_window_scrolls_to_the_end_of_its_content(window):
    gui = window(FakeTwitch())
    root, area = gui._root, gui.settings._area
    root.minsize(1, 1)
    root.geometry("700x400")
    gui.tabs._nb.select(2)
    root.update()
    canvas, content = area.canvas, (area.inner.winfo_reqwidth(), area.inner.winfo_reqheight())
    canvas.xview_moveto(1)
    canvas.yview_moveto(1)
    root.update()
    button = gui.settings._game_dir_add_button
    corner = (button.winfo_rootx() + button.winfo_width(), button.winfo_rooty() + button.winfo_height())

    assert canvas.cget("scrollregion") == f"0 0 {content[0]} {content[1]}"
    assert (canvas.canvasx(canvas.winfo_width()), canvas.canvasy(canvas.winfo_height())) == content
    assert canvas.winfo_rootx() < corner[0] <= canvas.winfo_rootx() + canvas.winfo_width()
    assert canvas.winfo_rooty() < corner[1] <= canvas.winfo_rooty() + canvas.winfo_height()
