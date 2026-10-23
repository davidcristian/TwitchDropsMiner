# At `-vvvv`, a log record from the game scan thread makes the scan fail

**Status:** done 2026-10-22
**Area:** gui (`_TKOutputHandler`), gamelib, twitch (game detection)
**Origin:** Found on 2026-10-18 while the docs were written, [gui.md](../../modules/gui.md#invariants)
**Verified:** 2026-10-22

`Twitch.detect_games` in `twitch.py` runs `gamelib.scan_directories` in a worker thread with
`asyncio.to_thread`. Two places in `gamelib` log at `DEBUG` from that thread:

- `read_text` in `gamelib/common.py`, when reading a file raises `OSError`;
- `_scan_epic_manifests` in `gamelib/epic.py`, when a `.item` manifest is not valid JSON.

Both modules log to `logging.getLogger("TwitchDrops")`, the logger that `GUIManager.__init__` adds
`_TKOutputHandler` to. `main.py` sets that logger's level from the `-v` flags, and only `-vvvv` sets `DEBUG`
(`LOGGING_LEVELS[4]`). Below that level the records are dropped before any handler runs.

`_TKOutputHandler.emit` calls `GUIManager.print`, which calls `ConsoleOutput.print`, which calls `Text.config`
and `Text.insert` on the thread that logged. Nothing passes the record to the event loop thread.

## What Tk does with the call

With a Tcl built with thread support (Tcl 8.6 builds it by default), `_tkinter` sends a call from another thread
to the interpreter's thread only while that thread runs `mainloop`. The app never calls `mainloop`:
`GUIManager._poll` runs the Tk events with `dooneevent`. So `_tkinter` waits about one second and raises
`RuntimeError: main thread is not in main loop`. `_TKOutputHandler.emit` does not catch it, and `logging` does
not catch it for a handler, so it reaches the `logger.log` call in `gamelib` and ends `scan_directories`. The
record never reaches the Output box. The docs that say the records reach the Output box from that thread
describe the attempt, not the result.

## How it was confirmed

The check used a Tk root and a `Text` widget under Xvfb (Tcl 8.6.14, `tcl_platform(threaded)` 1), the real
`_TKOutputHandler` and `ConsoleOutput.print`, a task that runs `dooneevent` like `GUIManager._poll`, and a folder
with a `Manifests` subfolder that holds two `.item` files that are not JSON. `HOME` pointed at an empty folder.
`await asyncio.to_thread(gamelib.scan_directories, [folder])` gave:

| Logger level | Result | Time | Thread that ran `emit` | Output box |
| --- | --- | --- | --- | --- |
| `ERROR` (no `-v`) | returned, no errors | 0.1 s | none | empty |
| `CALL` (`-vvv`) | returned, no errors | 0.1 s | none | empty |
| `DEBUG` (`-vvvv`) | raised `RuntimeError: main thread is not in main loop` | 1.0 s | `asyncio_0` | empty |

A second check ran `Twitch.detect_games` on a stand-in object at `DEBUG` with the same folder. Its
`except Exception` caught the error and logged it from the event loop thread. It called `set_scanning(False)`
and left `detected_games` unchanged. The Output box showed `ERROR: Game folder scan failed`, then the traceback,
ending with `RuntimeError: main thread is not in main loop`.

## Effect on a user

It happens only at `-vvvv`, and only while a scanned folder holds a file that cannot be read or an Epic manifest
that is not valid JSON. Then every scan fails: at each reload, at each `Rescan` and after each folder change. The
Detected Games list keeps its last result, so a newly installed game is not detected, and the Output box shows
the traceback each time. With `--log`, the record still reaches `log.txt`, because `main.py` adds the file
handler before `GUIManager` adds its own, and the logger calls its handlers in that order. With a Tcl built
without thread support, the same call would run on the worker thread with no check, which Tk does not support.

## What a fix involves

Either of the first two changes, together with the third:

- `_TKOutputHandler` stores the event loop when it is created on the main thread. `emit` prints directly on the
  main thread and otherwise passes the text with `loop.call_soon_threadsafe`, as the tray menu does.
- `gamelib` collects these messages in `ScanResult`, and `detect_games` logs them after the thread ends. Then no
  code logs from the thread.
- `emit` catches its own errors and calls `self.handleError(record)`, as `logging.StreamHandler`
  does, so a failure in the handler no longer ends the code that logged.

Cost: no Twitch requests. A test of the second option needs no display: it calls `scan_directories` on a broken
manifest and reads `ScanResult`.

How it came about: `_TKOutputHandler` dates from 2022 in the original project ("Small GUI internals cleanup").
The scan thread and the two `DEBUG` records came with installed game detection on 2026-08-24.

## History

- 2026-10-18: Opened while the docs were written. The claim was that the handler writes the records into the
  Tk widget from the scan thread. Calls with the real handler showed that the write raises `RuntimeError`
  instead, which ends the scan.
- 2026-10-22: Done. The claim still held: with the real window under Xvfb, a log call on another thread raised
  `RuntimeError: main thread is not in main loop` after one second. `_TKOutputHandler` now queues a record of
  another thread, and the event loop thread writes it in `GUIManager._poll` or before its own next record
  ([ui.md](../../modules/ui.md#log-records-in-the-output-box)). A queue needs no running event loop when the
  window is built, which `loop.call_soon_threadsafe` needs, and the tests build it without one. The third
  option, an `emit` that catches its own errors, was left out, because no Tk call on another thread is left to
  fail. The game scan thread is the only one that logs to `TwitchDrops`: pystray logs to its own logger, and the
  folder dialog runs in a child process. Two tests in `tests/test_gui.py` log from another thread and failed
  with that `RuntimeError` before the change. A scan at `DEBUG` of a folder with two malformed Epic manifests
  returned at once, where it had raised after one second, and the Output box showed both records.
