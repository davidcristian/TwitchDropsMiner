# On Tk 9, the back and forward mouse buttons scroll the Inventory tab

**Status:** done 2026-10-22
**Area:** mousewheel, gui
**Origin:** The test of the X11 wheel buttons in `tests/test_gui.py`, run on a Python with Tk 9.0
**Verified:** 2026-10-22

`wheel_events` in `mousewheel.py` returns `<Button-4>` and `<Button-5>` for X11, because Tk 8.6 on X11 sends a
wheel turn as a press of button 4 or 5, and `ScrollArea` in `scrollarea.py` binds them while the pointer is over
the Inventory or the Settings tab. Tk 9 sends a wheel turn as `<MouseWheel>` on X11 too, and gives the numbers 4
and 5 to other mouse buttons. On Tk 9.0 under Xvfb, a `<Button-4>` event from `event_generate` reached the
binding with `num` 8, and a `<Button-5>` one with `num` 9. `wheel_scroll` reads a press whose `num` is not 4 or 5
and whose `delta` is 0 as one unit down.

So on Tk 9 a press of the back or forward button, which X numbers 8 and 9, scrolls the tab down one unit. The
Settings tab moves only when its content is taller than the window. This follows from the event numbers above;
it was not checked with a real mouse. The wheel itself scrolls correctly, through `<MouseWheel>`. The system Python of Ubuntu 24.04 has Tk 8.6, and the Python 3.10.20 of
python-build-standalone has Tk 9.0.

## What a fix involves

`wheel_events` takes the Tk version as well as the windowing system, for example from `tk_version`, and returns
the button sequences only for Tk 8.6 on X11. The strict `xfail` test
`test_the_back_button_does_not_scroll_the_inventory_tab` in `tests/test_gui.py` then passes, and its mark is
removed. It runs only on Tk 9, so a run on Tk 8.6, such as with the system Python of Ubuntu 24.04, skips it.

Twitch requests: none.

## History

- 2026-10-21: Opened. A test of the wheel buttons scrolled the tab down for a `<Button-4>` event on Tk 9.0.
- 2026-10-21: The wheel binding moved to `ScrollArea`, which the Settings tab also uses.
- 2026-10-22: Closed. `wheel_events` takes `TkVersion` and returns `<MouseWheel>` alone for Tk 9, and the test,
  now `test_the_back_and_forward_buttons_do_not_scroll_the_inventory_tab`, passes without its mark. Under Xvfb,
  presses of X buttons 8 and 9 sent through XTest moved the Inventory tab down one unit each on Tk 9.0.3 before
  the change and left it in place after it, on Tk 9.0.3 and 9.0.4. The wheel buttons 4 and 5 scrolled it on
  Tk 8.6.14, 9.0.3 and 9.0.4. A real mouse was not used.
