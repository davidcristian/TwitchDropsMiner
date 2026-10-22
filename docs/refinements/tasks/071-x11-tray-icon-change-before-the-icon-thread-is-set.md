# A change to the X11 tray icon fails when it comes before pystray sets the icon thread

**Status:** open
**Area:** traybackend, gui
**Origin:** Found on 2026-10-22 while the X11 tray icon was started and stopped many thousands of times from
source under Xvfb, with a thread of pure Python work and a thread switch interval of 0.1 milliseconds
**Verified:** 2026-10-22

pystray's `Icon.run` starts the setup thread, which waits until the icon is ready and then sets `visible` to True.
The X11 backend's `_run` calls `_mark_ready`, which lets the setup thread go on, and only then sets `_thread` to
the icon thread. The dispatch of the subclass that `icon_class` returns, like pystray's own, compares the calling
thread with `_thread` ([traybackend.md](../../modules/traybackend.md)). When the setup thread gets there first, it
raises `AttributeError: 'XorgIcon' object has no attribute '_thread'` and ends, and the icon never shows. After a
start with `--tray` or a `Minimize to Tray`, nothing can then show the window again. A change from the event loop
in that moment, such as a new title, raises the same error there.

On 2026-10-22, a script started and stopped the icon in stalonetray, tint2, trayer and xfce4-panel, each with and
without openbox. With a busy thread and a switch interval of 0.1 milliseconds, this happened to 2 of 24,373
icons with pystray's dispatch and to 1 of 24,027 with the subclass's. Without them, it happened to none of
48,070 icons. The app keeps Python's switch interval of 5 milliseconds, and no run of the app has shown it.

## What a fix involves

`_dispatch` and `_send_message` of the subclass treat a missing `_thread` as another thread: the client message
then waits in the queue of the icon window's events until the icon thread reads it. A strict `xfail` test in
`tests/test_traybackend_xorg_start.py` checks that behavior. None of this sends a Twitch request.

## History

- 2026-10-22: Opened. Found while the fix that closed
  [task 070](070-x11-tray-icon-setup-thread-waits-in-flush.md) was checked with repeated starts.
