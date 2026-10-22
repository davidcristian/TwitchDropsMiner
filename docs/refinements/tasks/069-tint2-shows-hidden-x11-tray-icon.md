# The tray host tint2 shows the X11 tray icon while the window is open

**Status:** declined 2026-10-22
**Area:** traybackend, gui
**Origin:** Found on 2026-10-22 while the X11 tray icon was restored and minimized many times from source under
Xvfb in the tray hosts stalonetray, tint2, trayer and xfce4-panel
**Verified:** 2026-10-22

The subclass that `icon_class` in `traybackend.py` returns hides the X11 icon by clearing the mapped flag of its
`_XEMBED_INFO` property, and keeps the window docked ([traybackend.md](../../modules/traybackend.md)). tint2
17.0.1 ignores that flag, so after a left click on the icon restores the window, the icon stays in tint2's tray,
and a click on it shows the window that is already open. On 2026-10-22, from source under Xvfb with and without
the window manager openbox, the icon was viewable in tint2's tray after 36 of 36 restores. After 36 of 36
restores each, stalonetray unmapped the window that holds the icon, trayer shrank the icon to a width of 1 pixel
and xfce4-panel moved it off the screen.

## What a fix involves

With the X11 backend, stop the icon in `TrayIcon.restore` and create a new one in `minimize`: pystray's
`Icon._stop` destroys the icon window, and in the checks that closed
[task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md) this hid the icon in all four hosts. That choice
was set aside while the thread of a new icon could wait forever as it started, which the fix that closed
[task 066](066-x11-tray-icon-thread-waits-forever-at-start.md) prevents. Each new icon opens an X connection and
sends a dock request, so the check covers the four hosts and the dock requests that trayer receives. None of this
sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed
  [task 066](066-x11-tray-icon-thread-waits-forever-at-start.md) was checked in four tray hosts.
- 2026-10-22: Declined. A version that stopped the X11 icon in `TrayIcon.restore` and created a new one in
  `minimize` was checked from source under Xvfb in stalonetray, tint2, trayer and xfce4-panel, each with and
  without openbox, in 10 runs per host of six restores each, two of them started with `--tray`. After 240 of 240
  restores, no icon window was left and the tray looked as before the app started. 248 of 248 new icons docked
  and showed their image, with no window outside a tray and no lost click, and under xtrace trayer received one
  dock request for each of 19 new icons. But the setup thread of one new icon waited forever
  ([task 070](070-x11-tray-icon-setup-thread-waits-in-flush.md)): the next restore took 5 seconds and the app did
  not end after SIGTERM. A new icon at each `Minimize to Tray` gives that wait a chance at each minimize, so the
  app keeps one icon. The same check of the current version, 8 runs per host, kept the icon shown in tint2 after
  48 of 48 restores and hid it after 48 of 48 in each other host, and no run waited. In tint2, 24 left clicks on
  the icon while the window was open left the window open, and each next `Minimize to Tray` worked.
