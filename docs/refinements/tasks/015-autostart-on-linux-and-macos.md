# Autostart fails on Linux without an autostart folder, and from source outside Windows

**Status:** done 2026-10-23
**Area:** gui (`SettingsPanel` autostart)
**Origin:** Found on 2026-10-18 while the docs were written, [autostart.md](../../modules/autostart.md#autostart-on-each-platform)
**Verified:** 2026-10-23

The Autostart and "Autostart into tray" checkboxes call `SettingsPanel.update_autostart` in `gui.py`. It has two
defects outside Windows.

## The Linux branch does not create its folder

`_get_linux_autostart_filepath` returns `~/.config/autostart/TwitchDropsMiner.desktop`, or the same file name in
`$XDG_CONFIG_HOME/autostart` when that folder exists. `update_autostart` opens the file with `open('w')` and
creates no folder. The macOS branch calls `plist_file.parent.mkdir(parents=True, exist_ok=True)` before it
writes. So on a Linux system where `~/.config/autostart` does not exist yet, checking Autostart raises
`FileNotFoundError`.

Confirmed with a call: `update_autostart` ran on a stand-in for the panel, with `HOME` set to an empty temporary
folder and `XDG_CONFIG_HOME` unset. It raised `FileNotFoundError: [Errno 2] No such file or directory:
'<HOME>/.config/autostart/TwitchDropsMiner.desktop'`, and `_query_autostart` then returned False. After the
folder was created, the same call wrote the file.

What the user sees: the checkbox runs `update_autostart` as its Tk `command`, and the app does not replace
`report_callback_exception`. Tk then prints `Exception in Tkinter callback` and the traceback to standard error,
and the Output box shows nothing. A `tk.Checkbutton` whose command raised the same error showed this under Xvfb,
and its value stayed 1, so the box stays checked. The app does not start at login. At the next start,
`_query_autostart` finds no file and shows the box unchecked.

When `XDG_CONFIG_HOME` is set and its `autostart` folder does not exist, the code writes to `~/.config/autostart`
instead. The XDG Autostart specification names `$XDG_CONFIG_HOME/autostart` as the user folder whenever the
variable is set.

## From source, the command starts `pythonw`

When `IS_PACKAGED` is False, `_get_autostart_path` returns `"<SCRIPTS_PATH>/pythonw" "<SELF_PATH>" <flags>`.
`SCRIPTS_PATH` is `env/bin` outside Windows (`SYS_SCRIPTS` in `constants.py`). Python's `venv` creates `pythonw`
only on Windows: on other systems `venv.EnvBuilder.setup_python` creates `python`, `python3` and `python3.X`. An
`env/` made with `python3 -m venv`, as `setup_env.sh` makes it, has `python`, `python3` and `python3.12` in
`env/bin` on Linux with Python 3.12, and no `pythonw`.

Confirmed with the same stand-in, after the folder was created. `update_autostart` wrote:

```
[Desktop Entry]
Type=Application
Name=Twitch Drops Miner
Description=Mine timed drops on Twitch
Exec=sh -c '"<folder>/env/bin/pythonw" "<SELF_PATH>" --tray'
```

Running the `Exec` command with `sh` exited with code 127 and `pythonw: not found`. `_query_autostart` returned
True, because it checks only that the file contains the quoted `SELF_PATH`.

On macOS, the plist's `ProgramArguments` starts with the same path, because the branch splits the same command
with `shlex.split`. So launchd finds no program to start. This is an assumption from the code and the `venv`
source: it was not run on macOS.

What the user sees: the Autostart box is checked, and the app does not start at login. Nothing reports it,
because the desktop or launchd runs the entry without a window. A packaged build (PyInstaller or AppImage) is not
affected, because its command is the quoted `SELF_PATH`. On Windows from source, `env/Scripts/pythonw.exe`
exists.

## What a fix involves

- On Linux, create the folder with `mkdir(parents=True, exist_ok=True)` before writing, and use
  `$XDG_CONFIG_HOME/autostart` whenever the variable is set.
- Outside Windows, start a source run with `env/bin/python`, and keep `pythonw` for Windows, where it starts the
  app without a console window.
- Catch `OSError` in `update_autostart`, print a translated message to the Output box and set the checkbox from
  `_query_autostart` again.
- An entry already written with `pythonw` stays wrong, because `_query_autostart` reports it as on. The user
  unchecks and checks the box again, or the fix rewrites an entry that contains `SELF_PATH` but differs from the
  current command.
- `gui.py` is over the line cap ([task 005](005-modules-over-the-line-cap.md)), so the fix can move the autostart
  code to a module of its own, with the path logic callable without a display.

Cost: no Twitch requests. The change is a GUI change, so it is run in `python gui.py` or `python main.py` on
Linux.

How it came about: the Linux branch came with "Implement autostart querying upon application start"
(2024-07-01) and the `pythonw` command with "Support autostart when running from source" (2024-10-27), both in
the original project. The macOS branch came with the macOS port (2026-03-07), which added the `mkdir` for its own
folder only.

## History

- 2026-10-18: Opened while the docs were written. `update_autostart` and `_query_autostart` were called with a
  temporary `HOME`, and the written `Exec` command was run with `sh`.
- 2026-10-23: Done. Both claims held under Xvfb: checking Autostart with no autostart folder raised
  `FileNotFoundError`, and with the folder the `Exec` command named `env/bin/pythonw`, which this `env/bin` lacks. The entry code moved
  to `autostart.py` ([autostart.md](../../modules/autostart.md)), which creates the folder, uses
  `$XDG_CONFIG_HOME/autostart` whenever that variable is an absolute path, and starts a source run with
  `env/bin/python` outside Windows. `update_autostart` catches `OSError`, logs "Could not change the autostart
  entry:" and sets the checkbox again. An entry written with `pythonw` is not rewritten by the app: unchecking
  and checking the box writes it again, as [troubleshooting.md](../../troubleshooting.md#autostart) says.
  `tests/test_autostart.py` and `tests/test_gui_settings.py` cover it on files in a temporary folder. Not run on
  macOS: launchd starting the plist's `env/bin/python` command. Not run on Windows: `RegistryValue` and an
  `OSError` from the registry.
