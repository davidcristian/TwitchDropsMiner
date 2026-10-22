# The tray host tint2 shows no X11 tray icon when the app starts with `--tray`

**Status:** open
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
