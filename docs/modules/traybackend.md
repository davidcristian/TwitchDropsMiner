# `traybackend.py`

**Purpose.** Imports pystray, the tray icon library, for `gui.py`. pystray chooses its tray backend when it is
imported. Outside Windows and macOS it tries the AppIndicator backend, then GTK, then X11 (`xorg`), but it moves
on only after an `ImportError`. A GTK library that fails to load makes PyGObject raise `AssertionError` or
`ValueError` instead, so a plain `import pystray` fails and the app stops before its window opens. In the Linux
builds this happens on an X11 system without the Wayland client libraries, which PyInstaller and
appimage-builder leave to the system ([task 061](../refinements/tasks/061-linux-build-needs-wayland-libraries.md)).
`import_pystray` tries the three
backends in pystray's order and moves on after any of these errors, so the window opens and the tray icon uses
the X11 backend, which needs only python-xlib and Pillow.

The AppIndicator and GTK backends also need a DBus session bus. Their icon thread connects to it before it marks
the icon ready, and pystray's setup thread waits for that mark. Without a bus, the connection fails, no icon
appears, the setup thread waits forever, and Python waits for that thread at exit, so the app saves its files but does not end
([task 064](../refinements/tasks/064-sigterm-ignored-with-appindicator-tray.md)). `import_pystray` checks the bus
first and uses the X11 backend when it cannot connect.

The X11 backend runs the default menu item, "Show", on a left click on its icon. But it creates the icon window
without `ButtonPressMask`, the X11 event mask with which a client receives the clicks on a window, so the X
server does not send the click to pystray. `icon_class` adds that mask, so a left click on the icon restores the
window.

## Public contract

- `import_pystray(load, environ, platform, bus_error)` returns the pystray module that `load` returns. `gui.py`
  passes `load_pystray`, `os.environ`, `sys.platform` and `session_bus_error`.
  - On `win32` and `darwin`, and when `environ` sets `PYSTRAY_BACKEND` to a name, it calls `load` once, so
    pystray makes its own choice and an error propagates. It does not call `bus_error`.
  - Otherwise it calls `bus_error` once. When that returns a reason, it logs a warning and tries `xorg` alone.
  - It then sets `PYSTRAY_BACKEND` to each name in `BACKENDS` in turn, `appindicator`, `gtk` and `xorg`, and
    calls `load`. An error in `BACKEND_ERRORS` (`ImportError`, `ValueError`, `AssertionError`) from the
    first two logs a warning and tries the next. An error from `xorg`, and any other error, propagates.
  - Before it returns or raises, it sets `PYSTRAY_BACKEND` back to its earlier value, or removes it.
- `icon_class(base)` returns `base`, the `Icon` class of the loaded pystray, unless its module is `pystray._xorg`.
  Then it returns a subclass whose `_create_window` calls pystray's and adds `ButtonPressMask` to the events that
  the new window selects, keeping the others. `gui.py` creates its icon from `icon_class(pystray.Icon)`.
  `_create_window` is private to pystray, and `constraints.txt` keeps it stable by setting the pystray version
  exactly. A suite test docks a real X11 icon under Xvfb and sends it a click, so a pystray release that renames
  the method fails `just check`.
- `load_pystray()` imports pystray with an `import` statement, so that PyInstaller finds the package and bundles
  it, and returns the module.
- `session_bus_error()` opens the DBus session bus with `Gio.bus_get_sync`, the call that pystray's icon thread
  makes, and returns the message of the `GLib.Error` it raises, or None when the bus opens. It returns None when
  PyGObject or its Gio introspection data does not load, because the AppIndicator and GTK backends then fail to
  load on their own. GLib keeps the connection and gives pystray the same one. Without a bus address, GLib
  starts a bus with `dbus-launch` on X11 where it can, at this check rather than at the first tray icon.
- The warning names the backend and the last line of the error's traceback, such as
  `Tray icon: the appindicator backend failed to load (AssertionError), so the app tries the gtk backend`. The
  warning for the bus names GLib's message, such as `Tray icon: the app cannot connect to the DBus session bus
  (Cannot autolaunch D-Bus without X11 $DISPLAY), which the appindicator and gtk backends need, so it uses the
  xorg backend`.

## Invariants

- Where the AppIndicator backend loads, pystray is imported once and nothing is logged.
- A failed import leaves no `pystray` module in `sys.modules`, so the next `load` runs pystray's backend choice
  again. Modules that loaded before the error, such as `gi`, stay loaded.
- `gui.py` imports this module before `main.py` sets up logging, so Python prints the warning to standard error,
  and neither `log.txt` nor the Output box shows it. PyGObject prints its own warning before it, which names the
  library that failed to load.
- The X11 backend has no menu and shows no notifications. Its icon needs a tray that supports the XEmbed system
  tray protocol. A left click on it runs "Show", which restores the window and hides the icon. In the tray host
  stalonetray the icon stays on the screen instead
  ([task 065](../refinements/tasks/065-x11-tray-icon-left-on-screen-in-stalonetray.md)).
- A right or middle click and the mouse wheel on the X11 icon do nothing, as pystray runs the default item for
  the left button only. A right click opens the menu of the other backends, and the X11 icon has none. Running
  "Show" on it too would need a second private method of pystray, and the window that a left click restores has
  every action of the menu.
- "Quit" cannot be reached from the X11 icon, because it has no menu. The window's close button quits the app
  once a left click has restored the window.

**Dependencies.** None: the standard library only. `load_pystray` imports pystray, and `session_bus_error`
imports PyGObject.
