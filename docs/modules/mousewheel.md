# `mousewheel.py`

**Purpose.** The Inventory and Settings tabs scroll a plain `tk.Canvas`, which has no wheel bindings of its
own, so `ScrollArea` binds the wheel itself ([scrollarea.md](scrollarea.md)). Each windowing system and Tk
version reports a wheel turn as a different event, and this module holds that difference. It imports no other
module of the app and no tkinter, so `tests/test_mousewheel.py` runs it with plain values.

## Public contract

- `wheel_events(windowing_system, tk_version)` takes the result of the Tcl command `tk windowingsystem` and
  `tkinter.TkVersion`, and returns the event sequences to bind:

  | Windowing system | Tk | Sequences |
  | --- | --- | --- |
  | `x11`, which Tk uses on Linux | 8 | `<MouseWheel>`, `<Button-4>`, `<Button-5>` |
  | `x11` | 9 | `<MouseWheel>` |
  | `win32` (Windows), `aqua` (macOS) or any other | any | `<MouseWheel>` |

  Tk 8.6 on X11 sends a wheel turn as a press of button 4 (up) or 5 (down), and a sideways tilt as button 4
  or 5 with Shift. Tk's own scripts for `Text`, `Listbox` and the ttk widgets bind buttons 4 and 5 to scrolling
  only on `x11`, so on the other systems the module leaves those buttons alone. Tk 9 on X11 sends a wheel turn
  as `<MouseWheel>`, and a tilt as `<MouseWheel>` with Shift. It reports the back and forward buttons, which X
  numbers 8 and 9, as buttons 4 and 5, so a binding of those buttons would scroll on a press of either.
- `wheel_scroll(delta, num, state)` takes those attributes of a `tk.Event` and returns a `Scroll` named tuple of
  `axis` (`"x"` or `"y"`) and `units` (`-1` or `1`). A negative number scrolls up or left.
  - Button 4 gives `-1` and button 5 gives `1`. tkinter sets `delta` to 0 for a button press.
  - Any other `num`, such as the `"??"` of a `<MouseWheel>` event, gives `-1` for a positive `delta` and `1`
    otherwise. Windows sends multiples of 120 and macOS sends small numbers, so only the sign is read.
  - Shift, bit `0x1` of `state`, gives the x axis. Other modifier bits, such as Num Lock, are ignored. A `state`
    that is not a number gives the y axis.

**Dependencies.** None: the standard library only.
