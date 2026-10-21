import pytest

from mousewheel import Scroll, wheel_events, wheel_scroll

SHIFT = 0x1
NUM_LOCK = 0x10
# tkinter sets `num` to "??" for a <MouseWheel> event and `delta` to 0 for a button press
NO_BUTTON = "??"


def test_wheel_events_of_tk_8_on_x11_include_the_wheel_buttons():
    assert set(wheel_events("x11", 8.6)) == {"<MouseWheel>", "<Button-4>", "<Button-5>"}


def test_wheel_events_of_tk_9_on_x11_are_mousewheel_only():
    assert wheel_events("x11", 9.0) == ("<MouseWheel>",)


@pytest.mark.parametrize("tk_version", [8.6, 9.0])
@pytest.mark.parametrize("windowing_system", ["win32", "aqua"])
def test_wheel_events_on_windows_and_macos_are_mousewheel_only(windowing_system: str, tk_version: float):
    assert wheel_events(windowing_system, tk_version) == ("<MouseWheel>",)


@pytest.mark.parametrize(
    ("num", "state", "expected"),
    [
        (4, 0, Scroll("y", -1)),
        (5, 0, Scroll("y", 1)),
        (4, SHIFT, Scroll("x", -1)),
        (5, SHIFT, Scroll("x", 1)),
        (4, NUM_LOCK, Scroll("y", -1)),
        (5, NUM_LOCK | SHIFT, Scroll("x", 1)),
    ],
)
def test_wheel_scroll_reads_the_x11_wheel_buttons(num: int, state: int, expected: Scroll):
    assert wheel_scroll(0, num, state) == expected


@pytest.mark.parametrize(
    ("delta", "state", "expected"),
    [
        (120, 0, Scroll("y", -1)),
        (-120, 0, Scroll("y", 1)),
        (240, 0, Scroll("y", -1)),
        (1, 0, Scroll("y", -1)),
        (-3, 0, Scroll("y", 1)),
        (120, SHIFT, Scroll("x", -1)),
        (-120, SHIFT, Scroll("x", 1)),
    ],
)
def test_wheel_scroll_reads_the_delta_of_a_mousewheel_event(delta: int, state: int, expected: Scroll):
    assert wheel_scroll(delta, NO_BUTTON, state) == expected


def test_wheel_scroll_without_a_state_number_scrolls_along_y():
    assert wheel_scroll(0, 5, "??") == Scroll("y", 1)
