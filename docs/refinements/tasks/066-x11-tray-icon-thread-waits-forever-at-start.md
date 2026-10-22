# The thread of the X11 tray icon sometimes waits forever as the icon starts

**Status:** done 2026-10-22
**Area:** traybackend, gui
**Origin:** Found on 2026-10-22 while the window was minimized to the X11 tray icon and restored many times from
source under Xvfb with the tray host stalonetray and the window manager openbox
**Verified:** 2026-10-22

When pystray's `xorg` icon starts ([traybackend.md](../../modules/traybackend.md)), its setup thread sets
`visible` to True, which runs `_update_icon` and then `_show` in the icon thread: for each, the setup thread
sends a client message to the icon window, flushes the X connection and waits on a queue. The dock request of
`_update_icon` makes the tray embed and map the window, and the icon thread handles the Expose event with
`_draw`, which waits for the reply to `get_geometry`. Sometimes that wait never ends: python-xlib 0.33 keeps the
icon thread at `wait_lock.acquire()` in `send_and_recv`, and the setup thread waits on the queue for `_show`.
The icon thread then handles no more events. The icon shows no image and a click on it does nothing, so a window
that `--tray` or `Minimize to Tray` hid cannot be shown again. pystray logs nothing, and `main.py` sends the root
logger, which pystray's logger uses, to a `NullHandler`.

On 2026-10-22, `gui.py` from source and the x86_64 PyInstaller build ran on Ubuntu 22.04 with python-xlib 0.33
and pystray 0.19.5, under Xvfb with openbox 3.6.1 and stalonetray 0.8.1. A version that created a new icon at
each `Minimize to Tray` left 4 of 39 new icons blank, the first icon of a run among them. With the fix that closed
[task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md), which keeps one icon, the first icon stayed
blank in 1 of 6 runs, and the 30 `Minimize to Tray` of the other five runs showed the icon each time. The
thread stacks that `faulthandler` wrote for three blank icons were the same. No run without a window manager
showed a blank icon, and a script that started and stopped the icon 60 times without the app showed none.

## What a fix involves

Not known yet. One way: run `_update_icon` and `_show` in the icon thread before its event loop starts, so that
no other thread uses the connection while the tray handles the dock request; this overrides more private methods
of pystray. A test needs a way to reproduce the wait. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed
  [task 065](065-x11-tray-icon-left-on-screen-in-stalonetray.md) was checked with repeated minimizes.
- 2026-10-22: Closed. The cause is in python-xlib 0.33: in `send_and_recv`, a thread that sends on a connection
  while another thread reads it returns when data arrives, and does not wake a thread that started to wait for a
  reply in the meantime. pystray's setup thread sends the show right after the dock request, while the icon thread
  draws for the tray's first events, so the icon thread waited for the reply to `get_geometry` and no thread read
  the connection. A copy of python-xlib that logs that return logged it from the setup thread in 15 of 30 runs; the
  one blank icon of those runs came in the one run where a thread waited for a reply then. The subclass that
  `icon_class` returns now sends a client message from another thread on a new connection
  ([traybackend.md](../../modules/traybackend.md)). Counts from source under Xvfb with stalonetray and openbox, with
  six minimizes and restores per run: the first icon stayed blank in 2 of 30 runs before and 0 of 30 after, and with
  the logging copy in 1 of 30 before and 0 of 30 after, which logged no such return. The 360 minimizes of the runs
  after the fix all showed the icon. A script that hides the icon, changes its image, shows it and changes its title
  from another thread, as the app does, waited forever within 44 cycles in each of 6 runs before, with stalonetray
  and trayer, and in none of 6 runs of 200 cycles after. Docking and showing the first icon in the icon thread would
  have left that script's waits. No report of this wait was found among python-xlib's issues.
