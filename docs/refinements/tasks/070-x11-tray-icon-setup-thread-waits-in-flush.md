# The setup thread of a new X11 tray icon sometimes waits forever in `flush`

**Status:** open
**Area:** traybackend, gui
**Origin:** Found on 2026-10-22 while a version that stops the X11 tray icon at each restore and creates a new one
at each `Minimize to Tray` was checked from source under Xvfb in the tray hosts stalonetray, tint2, trayer and
xfce4-panel
**Verified:** 2026-10-22

When pystray's `xorg` icon starts ([traybackend.md](../../modules/traybackend.md)), its setup thread sets `visible`
to True, and pystray's dispatch runs `_update_icon` and then `_show` in the icon thread. For each, the setup thread
sends a client message, which the subclass that `icon_class` returns sends on a new connection, then calls `flush`
on the icon's connection and waits on a queue. Once, the setup thread never returned from the `flush` for `_show`.
The stack that `faulthandler` wrote at exit showed it in `send_and_recv` of python-xlib 0.33, at
`self.request_queue_lock.acquire()`, and the only other thread was the main thread, which waited for it. The icon
docked, showed its image, and a left click on it restored the window. But pystray's `Icon.stop` waits up to 5
seconds (`SETUP_THREAD_TIMEOUT`) for the setup thread, so the window appeared 5 seconds after that click instead
of within 0.1 seconds, and at exit Python waited for the thread forever: the app was still running 30 seconds
after SIGTERM.

On 2026-10-22, this happened to 1 of 248 new icons in 40 runs of six restores each, with python-xlib 0.33 and
pystray 0.19.5 on Ubuntu 22.04: the first icon of a run in xfce4-panel 4.16.3 without a window manager. The
current version starts one icon per run, at the first `Minimize to Tray` or at a start with `--tray`, through the
same setup thread. It showed no such wait in 32 runs of the same check, so how often it waits is not known.

## What a fix involves

Not known yet. One way: find what holds `request_queue_lock`, with a copy of python-xlib that records the thread
that takes it. Another: send pystray's dispatch messages from other threads without the `flush` on the icon's
connection, which the new connection already makes unnecessary; this replaces pystray's private
`_rewrite_implementation`. A test needs a way to reproduce the wait. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while stopping the icon at each restore was checked for
  [task 069](069-tint2-shows-hidden-x11-tray-icon.md).
