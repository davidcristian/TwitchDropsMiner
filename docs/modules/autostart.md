# `autostart.py`

**Purpose.** The entry that starts the app when the user logs in: the command it runs, and where Windows, Linux
and macOS keep it. `SettingsPanel` in `ui/` shows the `Autostart:` and `Autostart into tray:` checkboxes and
calls this module; macOS shows only the first. The module takes the platform, the environment and the home folder
as arguments, so `tests/test_autostart.py` runs the Linux and macOS entries on real files in a temporary folder
on any system.

## Public contract

- `autostart_entry(platform, environ, home)` returns the entry for the system that `platform` names, as
  `sys.platform` does: a `RegistryValue` for `win32`, a `LaunchAgent` for `darwin`, and a `DesktopFile` for any
  other value. It reads no file and no registry key.
- Each entry has `contains(self_path)`, which returns True when the entry exists and starts the app at
  `self_path`, `write(command)`, which creates or replaces it, and `remove()`, which deletes it when it exists.
  `write` and `remove` raise the `OSError` of a failed write or removal. `contains` returns False for a missing
  entry and for a path with a file in place of a folder. It raises the error of an entry that exists and cannot
  be read, such as `PermissionError`.
- `autostart_command(self_path, logging_level, tray, python)` returns the command: the quoted `self_path`, then
  one flag of `-` and as many `v` letters as the index of `logging_level` in `LOGGING_LEVELS` (such as `-vv`,
  none at index 0 or for a level not in the table), then `--tray` when `tray` is true. When `python` is set, the
  quoted `python` comes first.
- `source_python(scripts_path, platform)` returns the Python that starts a run from source: `pythonw` in the
  `env/` scripts folder on Windows, which starts the app without a console window, and `python` elsewhere,
  because a virtual environment has `pythonw` only on Windows.
- `xdg_autostart_folder(environ, home)` returns `$XDG_CONFIG_HOME/autostart` when `XDG_CONFIG_HOME` is an
  absolute path, and `<home>/.config/autostart` when it is unset, empty or relative. The XDG Base Directory
  specification ignores a relative path, and the XDG Autostart specification names this folder whether or not
  it exists.

## Autostart on each platform

When the panel is built, it calls `autostart_entry` with `sys.platform`, `os.environ` and `Path.home()`, and
sets the Autostart checkbox from `contains(SELF_PATH)`. A click on either checkbox calls
`SettingsPanel.update_autostart`, which stores the `autostart_tray` setting and writes the entry with the
command, or removes it. A packaged build runs `SELF_PATH`. A run from source runs `main.py` with
`source_python(SCRIPTS_PATH, sys.platform)` ([constants.md](constants.md#working-directory-and-paths)).

| Platform | Where the entry is | What it contains |
| --- | --- | --- |
| Windows | The value `TwitchDropsMiner` (`AUTOSTART_NAME`) under `HKCU/Software/Microsoft/Windows/CurrentVersion/Run` (`AUTOSTART_KEY`), as `REG_SZ`, through [registry.py](registry.md) | The command |
| Linux | `TwitchDropsMiner.desktop` in `xdg_autostart_folder`. `write` creates the folder when it is missing | A `[Desktop Entry]` with `Exec=sh -c '<command>'` |
| macOS | `~/Library/LaunchAgents/com.devilxd.twitchdropsminer.plist`. `write` creates `LaunchAgents` when it is missing | A plist with `Label`, `ProgramArguments` (the command split by `shlex.split`) and `RunAtLoad` set to true |

`contains` looks for the quoted `self_path` in the registry value or the desktop file, and for the path without
quotes in the plist; on Windows the value must also be `REG_SZ`. A copy of the app at another path therefore
shows the checkbox off, even when another copy has an entry. The plist label keeps the `com.devilxd` prefix
([ADR-0007](../adr/ADR-0007-kept-identifiers.md)).

When `write` or `remove` raises `OSError`, `update_autostart` logs "Could not change the autostart entry:" with
the error, which the Output box shows, and sets the checkbox from `contains` again. The registry raises
`OSError` too, from `winreg`.

## Entries written by older versions

- From source on Linux and macOS, an older version wrote a command that starts `env/bin/pythonw`, which does not
  exist, so the entry starts nothing. `contains` still finds the path of the app in it and shows the checkbox on.
  Unchecking and checking it again writes the `python` command; the app does not rewrite the entry by itself.
- On Linux, an older version used `$XDG_CONFIG_HOME/autostart` only when that folder existed, and otherwise
  wrote to `~/.config/autostart`. An entry it wrote there while `XDG_CONFIG_HOME` named another folder is no
  longer found, and a desktop that follows the XDG Autostart specification does not run it either.

## Invariants

- No test writes the real autostart entry. The `window` fixture in `tests/conftest.py` replaces
  `autostart_entry` in `ui/settingstab.py` with the `DesktopFile` of a temporary `XDG_CONFIG_HOME` on every system.
- `RegistryValue` is the only class that uses `registry`, which the module imports only on Windows, so its
  methods run only there. The tests do not cover them on Linux or macOS.
- A change to `AUTOSTART_NAME`, `AUTOSTART_KEY`, `LAUNCH_AGENT_LABEL` or the folders leaves existing entries in
  place: the app no longer finds them, and they still start it at login
  ([ADR-0007](../adr/ADR-0007-kept-identifiers.md)).

**Dependencies.** Repo modules: `constants` (`LOGGING_LEVELS`), and `registry` on Windows. The standard library
otherwise.
