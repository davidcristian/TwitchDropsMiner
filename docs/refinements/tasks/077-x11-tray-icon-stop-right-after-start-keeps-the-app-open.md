# A stop of the X11 tray icon right after it starts leaves a thread that keeps the app open

**Status:** open
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

## History

- 2026-10-23: Opened. A failed assertion placed in a tray test showed the waiting setup thread.
