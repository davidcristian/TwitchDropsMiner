# The X11 tray icon stays on the screen after it restores the window in stalonetray

**Status:** open
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
