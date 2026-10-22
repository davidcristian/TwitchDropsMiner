# The X11 tray icon stays on the screen after it restores the window in stalonetray

**Status:** done 2026-10-22
**Area:** gui, traybackend
**Origin:** Found on 2026-10-22 while a left click on the X11 tray icon restored the window of each Linux build,
started with `--tray` under Xvfb with the tray host `stalonetray`
**Verified:** 2026-10-22

`TrayIcon.restore` shows the window and sets `visible` of the pystray icon to False. In pystray's `xorg`
backend ([traybackend.md](../../modules/traybackend.md)), `Icon._undock_window` then unmaps the icon window and
reparents it to the root window. stalonetray maps an icon window back when its client unmaps it while it is
docked (`unmap_notify` in stalonetray's source, which calls this a kludge). The reparent then moves a mapped
window, so the icon stays on the screen as a 48 by 48 window at the top left corner, above the app's window,
until the next `Minimize to Tray` docks it again. `GUIManager.grab_attention` restores the window in the same
way.

On 2026-10-22, the x86_64 and aarch64 builds of both Linux jobs ran in an Ubuntu 22.04 container with
stalonetray 0.8.1 and no window manager. After each left click on the icon, `xwininfo` gave the icon window the
map state `IsViewable` at 0,0, and the screenshot showed the icon over the "Main" tab. Not checked: other tray
hosts, and how a window manager shows the window.

## What a fix involves

One of:

- With the X11 backend, stop the icon in `TrayIcon.restore` and create a new one in `minimize`. pystray's
  `Icon._stop` destroys the icon window, and stalonetray removes a destroyed icon.
- Reparent the window to the root before it is unmapped, in the subclass that `icon_class` returns. stalonetray
  then removes the icon when it reads the reparent, but its map request may still arrive after pystray's unmap.

None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed [task 063](063-x11-tray-icon-ignores-clicks.md) was
  checked in the Linux builds.
- 2026-10-22: Closed. The subclass that `icon_class` in `traybackend.py` returns hides the icon with the mapped
  flag of its `_XEMBED_INFO` property and keeps the window docked, and sends a dock request at a show only while
  the icon is not docked ([traybackend.md](../../modules/traybackend.md)). From source under Xvfb, before the
  fix, the icon window stayed viewable outside the tray after each restore in stalonetray, with and without the
  window manager openbox, which framed it as a window of its own; tint2, trayer and xfce4-panel hid it. Moving the
  window out of the tray before the unmap left it on the screen in stalonetray too. With the fix, stalonetray,
  trayer and xfce4-panel hide the icon, and tint2 keeps it in its tray. Stopping the icon at each restore hid it
  in all four hosts, but the icon thread waited forever for 4 of 39 new icons under openbox
  ([task 066](066-x11-tray-icon-thread-waits-forever-at-start.md)), so the fix keeps one icon. A suite test docks a
  real X11 icon in a window that acts as stalonetray does; without the new `_hide` and `_show`, the icon window
  ends viewable on the root window. Under act, the x86_64 PyInstaller build and AppImage started with `--tray`,
  no session bus and no network in stalonetray, the PyInstaller build also under openbox: three left clicks
  showed the window and hid the icon, and three `Minimize to Tray` showed the icon in the tray again. Both
  builds did the same in tint2 when started without `--tray`, with the icon kept in the tray. The checks found
  [task 066](066-x11-tray-icon-thread-waits-forever-at-start.md),
  [task 067](067-gui-preview-crashes-under-openbox.md) and
  [task 068](068-tint2-shows-no-x11-icon-after-tray-start.md).
