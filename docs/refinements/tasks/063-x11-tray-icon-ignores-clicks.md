# The X11 tray icon does not respond to a click

**Status:** done 2026-10-22
**Area:** gui, traybackend
**Origin:** Found on 2026-10-22 while each Linux build was started with `--tray` under Xvfb with the tray host
`stalonetray`, on a system where the AppIndicator and GTK backends of pystray fail to load
**Verified:** 2026-10-22

When the AppIndicator and GTK backends fail to load, `import_pystray` in `traybackend.py` starts pystray's
`xorg` backend ([traybackend.md](../../modules/traybackend.md)). That backend creates its icon window in
`Icon._create_window` with the event mask `ExposureMask | StructureNotifyMask`, in pystray 0.19.5 and in its
master branch on 2026-10-22. No client selects `ButtonPress` on the window, so the X server sends a click to no
one, and `Icon._on_button_press`, which runs the default menu item "Show", never runs. So "Minimize to Tray",
`--tray` and "Autostart into tray" hide the window, and the icon cannot restore it. The app runs on until it is
ended from a terminal or a system monitor.

On 2026-10-22, the x86_64 and aarch64 builds of the `linux-pyinstaller` and `linux-appimage` jobs ran with
`--tray` under Xvfb in an Ubuntu 22.04 container without the Wayland client libraries. Each docked its icon
window, named `Twitch Drops Miner` with the class `twitch_minerSystemTrayIcon`, in `stalonetray`, and a click
on the icon with `xdotool` left the main window hidden. For the x86_64 PyInstaller build, `xwininfo -events`
listed only `Exposure`, `StructureNotify` and `PropertyChange` for that window, and a click sent to the window
with `xdotool click --window` left the main window unmapped too. In the
extracted x86_64 AppImage with `Xlib.X.ButtonPressMask` added to that event mask, the same click showed the
main window.

## What a fix involves

One of:

- Select `ButtonPressMask` on the icon window after pystray creates it. This needs pystray's private
  `_create_window` or `_window`, which `constraints.txt` keeps stable by setting the pystray version exactly.
- Hide "Minimize to Tray" and ignore `--tray` and "Autostart into tray" when `pystray.Icon.HAS_MENU` is False,
  as on macOS.
- Report the event mask to pystray's maintainers and use a release that selects it.

None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the tray backend fallback that closed
  [task 061](061-linux-build-needs-wayland-libraries.md) was checked in the Linux builds.
- 2026-10-22: Closed. `icon_class` in `traybackend.py` returns a subclass of pystray's xorg `Icon` whose
  `_create_window` adds `ButtonPressMask` to the events of the icon window, and `gui.py` creates its icon from
  it. A suite test docks a real X11 icon under Xvfb and sends it a right and a left click: the left click runs
  "Show" and the right click nothing. Without the subclass, or with `_create_window` renamed in a copy of
  pystray, the left click runs nothing and the test fails. Under act, the x86_64 and aarch64 builds of both
  Linux jobs ran with `--tray` under Xvfb and `stalonetray` with no session bus, and the x86_64 builds also with
  a bus and without the Wayland libraries. For each, `xwininfo -events` listed `ButtonPress` for the icon
  window, a right click with `xdotool` left the window hidden, and a left click showed it, twice in a row. The
  x86_64 builds of the commit before listed no `ButtonPress`, and a left click left the window hidden. With a
  bus and the libraries, the x86_64 PyInstaller builds of both commits loaded the AppIndicator library,
  printed no `Tray icon:` line, and opened the menu with "Show" and "Quit" on a left click on their icon. A
  right click stays without an action, and "Quit" cannot be reached from the X11 icon
  ([traybackend.md](../../modules/traybackend.md)). The check found
  [task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md).
- 2026-10-22: pystray's maintainers closed a 2023 report that a click on the X11 icon under the tray `tint2`
  did nothing (https://github.com/moses-palmer/pystray/issues/151) without a change, and the missing mask would
  explain it. A new report that names the mask could let a later pystray release make the subclass
  unnecessary. Nothing was reported.
