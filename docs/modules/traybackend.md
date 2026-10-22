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

The X11 backend hides its icon by unmapping its window, which removes it from the screen, and moving it from the
tray to the root window. The tray host stalonetray maps a docked icon window again when its client unmaps it, and
maps an icon window on the root window when it leaves the tray. So the hidden icon stayed at the top left corner
of the screen, and a window manager showed it as a window of its own. Moving the window out of the tray before the
unmap leaves it on the screen too. The subclass that `icon_class` returns keeps the window docked and hides it
by clearing the mapped flag of its `_XEMBED_INFO` property, which an XEmbed tray reads to show or hide a docked
window. stalonetray, trayer and xfce4-panel hide the icon then; tint2 ignores the flag and keeps showing the icon.

The app keeps one icon for its whole run. Stopping the icon at each restore and creating a new one at each
`Minimize to Tray` hides it in tint2 as well, and
[task 069](../refinements/tasks/069-tint2-shows-hidden-x11-tray-icon.md) records why the app does not do that.
pystray also sends a dock request each
time it shows the icon or changes its image, so two in a row when an icon starts. trayer embeds the window again
for each request, and after two in a row it often leaves the icon out of its tray, so the subclass sends the
request at a show only while the icon is not docked.

pystray sends a dock request only when it shows the icon, changes its image or sees its tray end. With pystray
alone, a tray host that takes the system tray selection `_NET_SYSTEM_TRAY_S0` after that never receives one, so
after a start with `--tray` no icon appears and nothing can show the window again. tint2 17.0.1 takes the
selection only after it has waited up to 15 seconds for a window manager to set `_NET_NUMBER_OF_DESKTOPS`, and a
desktop may start its panel after an app that starts with it. A tray announces itself with a `MANAGER` client
message to the root window, so the subclass receives the structure events of the root window, which include that
message, and then docks an undocked icon.

pystray's icon thread reads the X events of the icon's connection to the X server. pystray runs each change, such
as a show, a hide, a new image, a new title or a stop, in that thread: another thread sends a client message to
the icon window, flushes the icon's connection and waits until the icon thread has run the change. The first
change comes from pystray's setup thread, which shows the icon as it starts. python-xlib 0.33 fails in two ways
when two threads use one connection at once. In its `send_and_recv`, a thread that sends but does not read
returns when data arrives, and that return does not wake a thread that started to wait for a reply in the
meantime. With pystray alone, the icon thread then sometimes waits forever for the reply to `get_geometry` as it
draws the icon, most often as the icon starts: the icon shows no image and ignores clicks. And a `flush` ends only
while the bytes sent stay at most the count it noted at its start, so when the icon thread sends a request during
a flush from another thread, the flush loops forever
([task 070](../refinements/tasks/070-x11-tray-icon-setup-thread-waits-in-flush.md)). `Icon.stop` waits up to 5
seconds for the setup thread, and Python waits for it at exit, so the app then does not end after SIGTERM. The
subclass replaces pystray's dispatch: another thread sends the client message on a new connection and then only
waits, and the icon thread runs the change and passes back its error, if any. So once the icon has started, only
the icon thread uses the icon's connection. A new connection for each message needs no lock and nothing to close
at exit, and the app sends a few such messages a minute at most.

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
  Then it returns a subclass, which `gui.py` creates its icon from:
  - `__init__` calls pystray's, selects `StructureNotifyMask` on the root window and wraps pystray's handler of
    client messages. A `MANAGER` message that names `_NET_SYSTEM_TRAY_S0` while `_systray_manager` is None
    calls `_update_icon`, which docks the icon and draws it. Any other client message goes to the handler that
    `_rewrite_implementation` sets.
  - `_rewrite_implementation(*methods)` replaces pystray's, which pystray's `__init__` calls with `_show`,
    `_hide`, `_update_icon`, `_update_title` and `_stop`. For each method it sets an attribute of the same name.
    In the icon thread, that attribute calls the method. In another thread, it sends the icon window a client
    message with `_send_message`, of an atom named after the method, such as `_PYSTRAY__SHOW` for `_show`. It then
    waits until the icon thread has run the method, and raises the `Exception` that the method raised. pystray's
    `_run` sets `_thread` only after it lets the setup thread go on, so until then every thread counts as another
    thread, and its message waits until the icon thread reads it. The handler of client messages that it sets runs
    the method of such an atom and ignores any other message. It does not flush the icon's connection from the
    calling thread, as pystray's does: the new connection sends the message, and the icon thread sends its own
    requests when it reads its next event.
  - `_send_message` calls pystray's in the icon thread. In another thread, it opens a new connection of the
    class of `_display`, sends the message on it with pystray's `_send_message`, then calls `sync`, without which
    Xvfb dropped the message, and closes it.
  - `_create_window` calls pystray's and adds `ButtonPressMask` to the events that the new window selects,
    keeping the others.
  - `_hide` clears the mapped flag of the window's `_XEMBED_INFO` property, and `_show` sets it. `_show` then
    calls pystray's `_show`, which sends the dock request, only while `_systray_manager` is None.

  These names, and `_window`, `_display`, `_thread`, `_message_handlers`, `_net_system_tray_sx`, `_xembed_info`
  and the `_XEMBED_` constants that the subclass reads, are private to pystray, and `constraints.txt` keeps them
  stable by setting the pystray and python-xlib versions exactly. Suite tests run a real X11 icon under Xvfb: one
  sends it a click, one hides and shows it in a window that acts as stalonetray does and counts its dock
  requests, one takes the tray selection after the icon has started and waits for the dock request, one
  counts the requests on the icon's connection at a title change from another thread, and one records the thread
  of each use of the icon's connection from the start of the icon to its stop. A pystray release that
  renames one of these names fails `just check`.
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
- Once the X11 icon has started, only the icon thread uses its connection: no other thread sends a request on
  it, flushes it or reads from it. The thread that creates the icon uses it before the icon thread starts, and
  pystray closes it when the icon is freed, after the icon thread has ended.
- The X11 backend has no menu and shows no notifications. Its icon needs a tray that supports the XEmbed system
  tray protocol. A left click on it runs "Show", which restores the window and hides the icon. The icon stays
  docked while it is hidden, so tint2, which ignores the XEmbed mapped flag, keeps showing it.
- A right or middle click and the mouse wheel on the X11 icon do nothing, as pystray runs the default item for
  the left button only. A right click opens the menu of the other backends, and the X11 icon has none. Running
  "Show" on it too would need a second private method of pystray, and the window that a left click restores has
  every action of the menu.
- "Quit" cannot be reached from the X11 icon, because it has no menu. The window's close button quits the app
  once a left click has restored the window.

**Dependencies.** None: the standard library only. `load_pystray` imports pystray, and `session_bus_error`
imports PyGObject.
