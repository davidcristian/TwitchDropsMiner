"""Read which way a mouse wheel event scrolls, on each windowing system that Tk runs on."""
from __future__ import annotations

from typing import Literal, NamedTuple

SHIFT_MASK = 0x1
WHEEL_UP_BUTTON = 4
WHEEL_DOWN_BUTTON = 5


class Scroll(NamedTuple):
    """The axis to scroll and the number of units; a negative number scrolls up or left."""

    axis: Literal["x", "y"]
    units: int


def wheel_events(windowing_system: str) -> tuple[str, ...]:
    """Return the event sequences that a wheel turn sends, for the result of `tk windowingsystem`."""
    if windowing_system == "x11":
        # Tk 8.6 on X11 sends a wheel turn as a press of button 4 or 5. Tk's own widget scripts bind these
        # buttons to scrolling only on X11, so the other systems keep `<MouseWheel>` alone.
        return ("<MouseWheel>", f"<Button-{WHEEL_UP_BUTTON}>", f"<Button-{WHEEL_DOWN_BUTTON}>")
    return ("<MouseWheel>",)


def wheel_scroll(delta: int, num: int | str, state: int | str) -> Scroll:
    """Return the scroll for a wheel event with these `delta`, `num` and `state` attributes.

    `num` is the button number, or "??" for a `<MouseWheel>` event. Shift in `state` scrolls along x.
    """
    if num == WHEEL_UP_BUTTON:
        units = -1
    elif num == WHEEL_DOWN_BUTTON:
        units = 1
    else:
        units = -1 if delta > 0 else 1
    shift = isinstance(state, int) and bool(state & SHIFT_MASK)
    return Scroll("x" if shift else "y", units)
