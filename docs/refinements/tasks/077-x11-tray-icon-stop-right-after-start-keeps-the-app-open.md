# A stop of the X11 tray icon right after it starts leaves a thread that keeps the app open

**Status:** done 2026-10-23
**Area:** gui, traybackend
**Origin:** Found on 2026-10-23 while the test run that stayed open after its last test was looked into
([075](075-test-run-stays-open-after-the-last-test.md))
**Verified:** 2026-10-23

`TrayIcon.stop` in `gui.py` calls pystray's `Icon.stop`. With the X11 backend, the icon thread that `_start`
runs through `run_in_executor` marks the icon running, and then pystray's setup thread shows the icon through
`_dispatch` of the subclass in `traybackend.py`, which waits for the icon thread to answer. A stop that comes
before the icon shows leaves a thread that never ends:

- A stop before pystray marks the icon running does nothing, and the icon thread then runs until the app ends.
- A stop after that mark destroys the icon window, and the setup thread waits forever in `_dispatch` for the
  answer to its show (`self._results.get()`).

`TrayIcon.restore` stops only an icon that is visible, so it avoids both. `GUIManager.close_window`, which
`main.py` calls before `sys.exit`, and `TrayIcon.__del__` call `stop` without that check. Neither thread is a
daemon thread, so Python's exit waits for it and the app stays open. This happens only when the app closes in
the moment between a `Minimize to Tray` (or a start with `--tray`) and the icon showing.

The test `test_restoring_the_window_removes_the_x11_tray_icon_from_the_tray_and_minimizing_docks_a_new_one` in
`tests/test_gui_tray.py`, with a failed assertion placed right after `gui.tray.minimize()` so that its `finally`
block called `gui.tray.stop()` at once, ended with this report of the thread check in `tests/threadcheck.py`:

```
Thread 'Thread-1 (setup_handler)', ident 131329995028160:
  File ".../pystray/_base.py", line 400, in setup_handler
  File ".../pystray/_base.py", line 184, in visible
  File ".../traybackend.py", line 118, in _dispatch
    if (error := self._results.get()) is not None:
```

A fix makes `TrayIcon.stop` wait a short time for the X11 icon to show before it stops it, as `stop_icon` in
`tests/xorgicon.py` does for the tests. Twitch requests: none.

## How it was closed

The subclass that `icon_class` returns now ends both threads at a stop at any moment
([traybackend.md](../../modules/traybackend.md)). Its `stop` keeps a stop that comes before pystray marks the
icon running, and the icon thread then runs pystray's `_stop` in place of its main loop. When the main loop ends,
each change that still waits returns, and a later change returns at once. Each waiting change has its own
answer, as one queue for all of them could give the answer of a stop to the setup thread and leave the stop
waiting. So `TrayIcon.restore` in `gui.py` now stops the X11 icon also before it shows, and `close_window`, a
SIGTERM and `TrayIcon.__del__` end both threads at any moment.

`tests/test_traybackend_xorg_stop.py` tests each part with the fake icon, and stops a real icon under Xvfb
before its run, as its run starts, between the mark and the show, and after the show. `tests/test_gui_tray.py`
restores and stops right after a minimize. On the code before the fix, 10 of these tests failed and the thread
check named the threads left. A loop that started and stopped real icons, each stop at one of 11 moments from
before the run to 0.1 seconds after the start, left 11 threads in 22 rounds before the fix, and stops waited up
to 5 seconds. After it, 220 rounds on Xvfb and 110 rounds with each of stalonetray, trayer, tint2 and
xfce4-panel left no thread, and no stop took more than 0.02 seconds.

## History

- 2026-10-23: Opened. A failed assertion placed in a tray test showed the waiting setup thread.
- 2026-10-23: Closed. A stop of the X11 icon at any moment ends both of pystray's threads.
