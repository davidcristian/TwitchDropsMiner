# The tray host tint2 shows no X11 tray icon when the app starts with `--tray`

**Status:** done 2026-10-22
**Area:** traybackend, gui
**Origin:** Found on 2026-10-22 while the x86_64 Linux builds were started with `--tray` under Xvfb with the tray
host tint2 and no DBus session bus
**Verified:** 2026-10-22

With pystray's `xorg` backend ([traybackend.md](../../modules/traybackend.md)), the x86_64 PyInstaller build
started with `--tray` under tint2 17.0.1 creates its icon window, but tint2 never embeds it: the window stays
unmapped at -1,-1 with a size of 1 by 1, and tint2's log has no `add_icon` line. The app window stays hidden, so
nothing can show it again. Started without `--tray`, the same build docks its icon in tint2 at the first
`Minimize to Tray`, and stalonetray docks the icon of a start with `--tray`.

On 2026-10-22 this happened in each of 8 starts in an Ubuntu 22.04 container with no window manager, with tint2
started 3 or 10 seconds before the app: 3 of the build with the fix that closed
[task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md), 3 of a build that stopped the icon at each
restore instead, and 2 of the build of the commit before. The AppImage and window managers were not tried.

## What a fix involves

Find out why tint2 does not embed the icon: whether pystray sends its dock request before tint2 manages the
system tray selection, or tint2 drops the request. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed
  [task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md) was checked in the Linux builds.
- 2026-10-22: Closed. pystray sent its dock request before tint2 owned the system tray selection
  `_NET_SYSTEM_TRAY_S0`: under xtrace, the app's two `GetSelectionOwner` requests got the reply `None`, pystray
  logged `Failed to dock icon` twice, and the selection got its owner 12 seconds after the app started. tint2 17.0.1
  takes the selection only after `get_desktops` has waited up to 15 seconds for a window manager to set
  `_NET_NUMBER_OF_DESKTOPS`, so without one its tray started 15 seconds after tint2 did. Under openbox the same
  start docked the icon. pystray sends a dock request only when it shows the icon or changes its image, so it sent
  none later. The subclass that `icon_class` returns now docks an undocked icon when a tray announces itself with a
  `MANAGER` message ([traybackend.md](../../modules/traybackend.md)). From source under Xvfb with tint2 and no
  window manager, started 3 or 10 seconds before `main.py --tray`, the icon stayed undocked in 8 of 8 starts before.
  After the fix it docked in 8 of 8, and in each start three left clicks showed the window and three
  `Minimize to Tray` showed the icon again. A start with `--tray` docked the icon in stalonetray, tint2, trayer and
  xfce4-panel, with and without openbox. The x86_64 PyInstaller build made under act, started with `--tray`, no
  session bus and no network, docked the icon in tint2 and in stalonetray, with and without openbox, and in each
  start three left clicks showed the window and three `Minimize to Tray` showed the icon with its image.
