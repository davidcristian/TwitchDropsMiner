# `main.py`

**Purpose.** The entry point. It parses the command line, loads the settings, takes the single instance lock,
sets up logging, runs `Twitch` and sets the exit code. Apart from two imports, all of the file is inside
`if __name__ == "__main__":`, so importing `main` runs nothing. `settings.py` imports `ParsedArgs` from it for
type checking only.

## Startup order

1. `freeze_support()` from `multiprocessing`, which a PyInstaller build needs to start.
2. `truststore.inject_into_ssl()`, so that TLS connections check certificates against the operating system's
   certificate store. It runs before `twitch` imports `aiohttp`, because `aiohttp/connector.py` creates its
   default SSL context when it is imported.
3. The imports. Importing `translate` rewrites `lang/English.json` in a run from source
   ([translate.md](translate.md)).
4. `warnings.simplefilter("default", ResourceWarning)`, which shows the `ResourceWarning` for an unclosed
   resource, hidden by default, once per code location.
5. The version check, which raises `RuntimeError("Python 3.10 or higher is required")`. It runs after the
   imports, so on Python 3.9 it is never reached: `import truststore` in step 2 already raises `ImportError`,
   and `utils.py` imports `typing.ParamSpec`, which 3.9 does not have.
6. On Linux, when `XMODIFIERS` is not set, it is set to `@im=none`. This turns off the X input method, which the
   code comment names as the cause of XWayland and Mutter lockups during large Tk layout updates.
7. A hidden `tk.Tk` root with the app icon, as the parent of the message boxes in steps 8 and 9.
8. `Parser.parse_args` into a `ParsedArgs` namespace.
9. `Settings(args)` ([settings.md](settings.md)). Any exception shows the "Settings error" message box with the
   traceback and exits with code 4. The hidden root is then destroyed.
10. `lock_file(LOCK_PATH)`. When another process holds the lock, the app exits with code 3.
11. `asyncio.run(main())`. The lock file is closed in a `finally` block after it.

## Public contract

The interface of `main.py` is its command line flags and its exit codes, both below. `Settings` reads the flags
from `ParsedArgs`. `SettingsPanel` writes `-v` and `--tray` into the autostart command
([gui.md](gui.md)), so a renamed flag breaks an autostart entry that is already saved.

## Command line flags

`Parser` subclasses `argparse.ArgumentParser`. It collects argparse's output in a `StringIO` and shows it in a
message box titled "Argument Parser Error" when argparse exits, also for `--help` and `--version`
([task 025](../refinements/tasks/025-version-and-help-shown-as-error.md)). The flags for users are also in
[troubleshooting.md](../troubleshooting.md#command-line-flags).

| Flag | `Settings` attribute | Effect |
| --- | --- | --- |
| `-h`, `--help` | | Added by argparse. Shows the usage and exits with code 0. |
| `--version` | | Shows `v` and `version.__version__`, and exits with code 0. |
| `-v` | `logging_level` | Counted. `LOGGING_LEVELS[min(count, 4)]`: 0 is ERROR, 1 WARNING, 2 INFO, 3 `CALL`, 4 DEBUG. |
| `--tray` | `tray` | Starts with the window hidden in the tray ([gui.md](gui.md#the-tray-icon)). Ignored on macOS. |
| `--log` | `log` | Also writes the `TwitchDrops` log to `log.txt` (`LOG_PATH`) with `FILE_FORMATTER`. The token and other secrets in it show as `<hidden>` ([redact.md](redact.md)). |
| `--dump` | `dump` | `Twitch.run` empties `dump.dat`, `Twitch.fetch_inventory` appends the campaign data to it, and the app closes when `Twitch._run` next reaches `State.IDLE` or `State.CHANNEL_SWITCH`. |
| `--debug-ws` | `debug_ws` | Hidden from the help. Sets the `TwitchDrops.websocket` logger to DEBUG. |
| `--debug-gql` | `debug_gql` | Hidden from the help. Sets the `TwitchDrops.gql` logger to DEBUG. |

`CALL` is a level between DEBUG and INFO that `constants.py` defines.

## Logging

`main()` sets up logging before it creates `Twitch`:

- `_.set_language(settings.language)` comes first, so the window is built in the chosen language. A
  `ValueError` for an unknown language keeps English.
- When the level is above DEBUG, a `logging.NullHandler` is added to the root logger. Records from other
  libraries' loggers then end there instead of in Python's last resort handler, which prints to stderr.
- The `TwitchDrops` logger gets the level from `-v`, and with `--log` a `logging.FileHandler` for `log.txt`.
- `TwitchDrops.gql` and `TwitchDrops.websocket` are set to DEBUG by their debug flag, to INFO at `-vvvv` or more
  so that the raw requests and messages stay hidden, and otherwise to NOTSET, which uses the `TwitchDrops` level.
- `GUIManager` adds the handler that writes each record from the event loop thread to the Output box
  ([gui.md](gui.md), [task 021](../refinements/tasks/021-scan-thread-logs-into-tk.md)).

## The run and the exit

1. `Twitch(settings)` creates the client and its window. On Linux, SIGINT and SIGTERM call `client.gui.close()`.
2. `await client.run()`. `Twitch.run` starts the client again after a `ReloadRequest` and returns after an
   `ExitRequest`. While the "Restart after a crash after" setting is not "Never", it also starts again after any
   other exception ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)). An exception reaches `main()`
   only when `restart_delay` is 0, or when `Twitch._await_restart` raises itself. A failed critical task, such
   as `_watch_loop`, calls `Twitch.close()` instead, and `run` returns without a restart
   ([task 013](../refinements/tasks/013-crashed-task-ends-the-app.md)).
3. An exception sets the exit code to 1, prints "Fatal error encountered:" and the traceback, and calls
   `client.prevent_close()`, so the window stays open.
4. In `finally`, the signal handlers are removed, "Exiting..." is printed and `client.shutdown()` runs.
5. When the user did not close the window, the tray icon changes to `error`, the Output box shows "Application
   Terminated. Close the window to exit the application.", the status shows "Terminated", and
   `grab_attention(sound=True)` shows the window and rings the bell.
6. `await client.gui.wait_until_closed()` waits until the user closes the window.
7. `client.save(force=True)` writes the settings and the image cache. It runs after the wait, because the user
   can still change settings in the window after the run ends.
8. `client.gui.stop()`, `client.gui.close_window()` and `sys.exit` with the exit code.

A fatal error during the run shows no dialog. The traceback is in the Output box, and the window stays open with
the error tray icon. Only the argument and settings errors before the window exists use a message box.

## Exit codes

| Code | When |
| --- | --- |
| 0 | The user closed the window, `--dump` finished, `--help` or `--version` ran, or a critical task failed ([task 013](../refinements/tasks/013-crashed-task-ends-the-app.md)). |
| 1 | `client.run()` raised an exception. With the default `restart_delay` of 10, the app starts again after an exception instead ([The run and the exit](#the-run-and-the-exit), step 2). |
| 2 | argparse found an error in the command line, such as an unknown flag. |
| 3 | Another process holds `lock.file`. |
| 4 | `Settings(args)` raised, for example because `settings.json` is not valid JSON. |

[`manual.txt`](../../manual.txt), which is shipped with each release, lists the same five codes.

## The lock file

`utils.lock_file` opens `lock.file` in the app's folder (`WORKING_DIR`, the folder of the executable, the
`.AppImage` file or `main.py`) for writing, writes one character and locks it without waiting:
`msvcrt.locking` with `LK_NBLCK` on Windows, and `fcntl.lockf` with `LOCK_EX | LOCK_NB` on Linux and macOS. On
any other platform it returns success without a lock. The operating system releases the lock when the process
ends, also after a crash. The lock is per folder: two copies started from different folders both run.

## Invariants

- `truststore.inject_into_ssl()` stays before the first import of `aiohttp`, for the reason in
  [Startup order](#startup-order), step 2.
- `freeze_support()` stays the first call in the `__main__` block, where the `multiprocessing` documentation
  requires it for a frozen executable.
- `client.save(force=True)` stays after `wait_until_closed()`, for the reason in
  [The run and the exit](#the-run-and-the-exit), step 7.
- A new flag gets an attribute on `ParsedArgs`, a line in `manual.txt` and a row in the flag table of
  [troubleshooting.md](../troubleshooting.md#command-line-flags).
- A flag with the name of a `SettingsFile` key hides that key, because `Settings` reads `ParsedArgs` attributes
  before the settings file ([settings.md](settings.md)).

**Dependencies.** Repo modules: `translate`, `twitch`, `settings`, `version`, `exceptions`, `utils`, `constants`.
Third-party: `truststore`. Standard library: `argparse`, `asyncio`, `logging`, `signal`, `tkinter`.
