# `main.py`

**Purpose.** The entry point. It parses the command line, loads the settings, takes the single instance lock,
sets up logging, runs `Twitch` and sets the exit code. Apart from its imports, `log_file_handler` and `Parser`,
all of the file is inside `if __name__ == "__main__":`, so importing `main` runs nothing. `settings.py` imports `ParsedArgs`
from it for type checking only.

## Startup order

1. `freeze_support()` from `multiprocessing`. In a PyInstaller build, the child process of the folder dialog
   runs the app's executable again, and this call runs the child's work and exits
   ([folderpicker.md](folderpicker.md#the-child-process)).
2. The version check, which raises `RuntimeError("Python 3.10 or higher is required")` on an older Python. The
   `__main__` block imports only `sys` before it, because `truststore` and `utils`, which imports
   `typing.ParamSpec`, need 3.10.
3. `end_with_runtime` ([parentexit.md](parentexit.md)). When an AppImage without FUSE started the app as a child
   of its runtime, the kernel sends the app SIGTERM when the runtime ends. It runs before the slower imports,
   because the app does not notice a runtime that ends before this call.
4. `truststore.inject_into_ssl()`, so that TLS connections check certificates against the operating system's
   certificate store. It runs before `twitch` imports `aiohttp`, because `aiohttp/connector.py` creates its
   default SSL context when it is imported.
5. The imports, then, in a run from source, `save_template()`, which rewrites `lang/English.json`
   ([translate.md](translate.md#why-langenglishjson-is-rewritten-on-every-run-from-source)).
6. `warnings.simplefilter("default", ResourceWarning)`, which shows the `ResourceWarning` for an unclosed
   resource, hidden by default, once per code location.
7. On Linux, when `XMODIFIERS` is not set, it is set to `@im=none`. This turns off the X input method, which the
   code comment names as the cause of XWayland and Mutter lockups during large Tk layout updates.
8. A hidden `tk.Tk` root with the app icon, as the parent of the message boxes in steps 9, 10 and 12.
9. `Parser.parse_args` into a `ParsedArgs` namespace.
10. `Settings(args)` ([settings.md](settings.md)). Any exception shows the "Settings error" message box with the
    traceback and exits with code 4.
11. `_.set_language(settings.language)`, so the window and the message box of step 12 use the chosen language.
    A `ValueError` for an unknown language keeps English.
12. `lock_file(LOCK_PATH)` takes the lock on `lock.file` in the app's folder ([instancelock.md](instancelock.md)).
    When the file cannot be opened or written, for example in a read only folder, the "Cannot start" message box
    shows the error and the app exits with code 5. When another process holds the lock, the app exits with code
    3 and shows nothing. The hidden root is then destroyed.
13. `asyncio.run(main())` in a `with` block on the lock file, which closes the file after the run.

## Public contract

The interface of `main.py` is its command line flags and its exit codes, both below. `Settings` reads the flags
from `ParsedArgs`. `SettingsPanel` writes `-v` and `--tray` into the autostart command
([gui.md](gui.md)), so a renamed flag breaks an autostart entry that is already saved.

`log_file_handler(path, formatter)` returns a `logging.FileHandler` that appends to the file at `path` in UTF-8
and formats each record with `formatter` ([Logging](#logging)). It and `Parser` are the names a test can import.

## Command line flags

`Parser(*args, boxes, title, error_title, **kwargs)` subclasses `argparse.ArgumentParser`. It collects
argparse's output in a `StringIO` and shows it in a message box when argparse exits. For status 0, after
`--help` and `--version`, it calls `boxes.showinfo` with `title`. For any other status, such as 2 for an unknown
flag, it calls `boxes.showerror` with `error_title`. `boxes` is a `MessageBoxes`, an object with those two
methods: `tkinter.messagebox` in the app, a fake in a test. The app passes the strings `arguments.title`
("Twitch Drops Miner") and `arguments.error_title` ("Argument Parser Error") from `translate/`. They show in
English, because the language is set after the settings load, which need the parsed flags. The flags for users
are also in [troubleshooting.md](../troubleshooting.md#command-line-flags).

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

- When the level is above DEBUG, a `logging.NullHandler` is added to the root logger. Records from other
  libraries' loggers then end there instead of in Python's last resort handler, which prints to stderr.
- The `TwitchDrops` logger gets the level from `-v`, and with `--log` the handler that
  `log_file_handler(LOG_PATH, FILE_FORMATTER)` returns, which writes `log.txt` in UTF-8. Without an encoding it
  would write the code page of the locale, such as cp1252 on a Western Windows, and a line with a character
  outside it, such as a Korean channel name, would be lost.
- `TwitchDrops.gql` and `TwitchDrops.websocket` are set to DEBUG by their debug flag, to INFO at `-vvvv` or more
  so that the raw requests and messages stay hidden, and otherwise to NOTSET, which uses the `TwitchDrops` level.
- `GUIManager` adds the handler that writes each record to the Output box from the event loop thread, also a
  record that another thread logs ([ui.md](ui.md#log-records-in-the-output-box)).

## The run and the exit

1. `Twitch(settings)` creates the client and its window. On Linux, SIGINT and SIGTERM call `client.gui.close()`.
   In an AppImage without FUSE, the end of the runtime sends that SIGTERM
   ([Startup order](#startup-order), step 3).
2. `await client.run()`. `Twitch.run` starts the client again after a `ReloadRequest` and returns after an
   `ExitRequest`. While the "Restart after a crash after" setting is not "Never", it also starts again after any
   other exception ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)), the error of a failed critical
   task such as `_watch_loop` included. An exception reaches `main()` only when `restart_delay` is 0, or when
   `Twitch._await_restart` raises itself.
3. An exception sets the exit code to 1, prints "Fatal error encountered:" and the traceback, and calls
   `client.prevent_close()`, so the window stays open.
4. In `finally`, the SIGINT handler is removed, "Exiting..." is printed and `client.shutdown()` runs. The
   SIGTERM handler stays until `asyncio.run` closes the loop, so a SIGTERM during the shutdown, or while the
   window shows a fatal error, also closes the window and the files are saved. A SIGTERM that `timeout` sends
   to its process group, or systemd to every process of a service, reaches an AppImage without FUSE twice: once
   directly and once from the kernel at the end of the runtime.
5. When the user did not close the window, the tray icon changes to `error`, the Output box shows "Application
   Terminated. Close the window to exit the application.", the status shows "Terminated", and
   `grab_attention(sound=True)` shows the window and rings the bell.
6. `await client.gui.wait_until_closed()` waits until the user closes the window.
7. `client.save(force=True)` writes the settings and the image cache. It runs after the wait, because the user
   can still change settings in the window after the run ends. An `OSError` from it passes up out of `main()`,
   so the calls below do not run: Python prints the traceback and exits with code 1.
8. `client.gui.stop()`, `client.gui.close_window()` and `sys.exit` with the exit code.

A fatal error during the run shows no dialog. The traceback is in the Output box, and the window stays open with
the error tray icon. Only the argument, settings and lock file errors before the window exists use a message
box.

## Exit codes

| Code | When |
| --- | --- |
| 0 | The user closed the window, `--dump` finished, or `--help` or `--version` ran. |
| 1 | `client.run()` raised an exception. With the default `restart_delay` of 10, the app starts again after an exception instead ([The run and the exit](#the-run-and-the-exit), step 2). |
| 2 | argparse found an error in the command line, such as an unknown flag. |
| 3 | Another process holds `lock.file`. |
| 4 | `Settings(args)` raised, for example because `settings.json` is not valid JSON. |
| 5 | `lock.file` cannot be opened or written, for example because the app's folder is read only. |

[`manual.txt`](../../manual.txt), which is shipped with each release, lists the same six codes.

## Invariants

- The version check stays before every import that needs Python 3.10, so that an older Python shows its
  message ([Startup order](#startup-order), step 2).
- `end_with_runtime` stays before the slower imports, for the reason in [Startup order](#startup-order), step 3.
- `truststore.inject_into_ssl()` stays before the first import of `aiohttp`, for the reason in
  [Startup order](#startup-order), step 4.
- `freeze_support()` stays the first call in the `__main__` block, where the `multiprocessing` documentation
  requires it for a frozen executable.
- Everything except `log_file_handler`, `Parser` with its `MessageBoxes` protocol and the imports of standard
  library modules stays under `if __name__ == "__main__":`. In a run from source, the child process of the folder dialog imports `main.py`
  as `__mp_main__` and must not run the app. An older Python runs the code outside that block before the version
  check, so that code imports nothing that needs Python 3.10.
- `client.save(force=True)` stays after `wait_until_closed()`, for the reason in
  [The run and the exit](#the-run-and-the-exit), step 7.
- A new flag gets an attribute on `ParsedArgs`, a line in `manual.txt` and a row in the flag table of
  [troubleshooting.md](../troubleshooting.md#command-line-flags).
- A flag with the name of a `SettingsFile` key hides that key, because `Settings` reads `ParsedArgs` attributes
  before the settings file ([settings.md](settings.md)).

**Dependencies.** Repo modules: `translate`, `twitch`, `settings`, `version`, `exceptions`, `instancelock`,
`parentexit`, `utils`, `constants`. Third-party: `truststore`. Standard library: `argparse`, `asyncio`, `logging`, `pathlib`, `signal`,
`tkinter`.
