# `registry.py`

**Purpose.** Wraps the standard `winreg` module: it opens one Windows registry key and reads, writes, deletes and
lists its values. The app uses it for one thing, the Autostart setting on Windows. It imports `winreg` at the
top, so it can be imported only on Windows, and `gui.py` imports it only when `sys.platform == "win32"`.

## Public contract

**`RegistryKey(path, *, read_only=False)`** opens the key at `path`, such as
`"HKCU/Software/Microsoft/Windows/CurrentVersion/Run"`. `/` and `\` both separate the parts. The first part
names a `MainKey` member: `HKCU`, `HKLM`, `HKU`, `HKCR` or the full `HKEY_*` names, including
`HKEY_CURRENT_CONFIG` and `HKEY_PERFORMANCE_DATA`. The key opens with `KEY_QUERY_VALUE`, plus `KEY_SET_VALUE`
unless `read_only` is true. The key must exist: errors from `winreg.OpenKey` reach the caller, and the class
creates no keys. Used as a context manager, it closes the key on exit.

| Method | Returns | Raises |
| --- | --- | --- |
| `get(name)` | `(ValueType, value)` | `ValueNotFound` when the key has no value `name` |
| `set(name, value_type, value)` | `True` | errors from `winreg.SetValueEx` |
| `delete(name, *, silent=False)` | `True` when the value was deleted; `False` when it was missing and `silent` is true | `ValueNotFound` when the value is missing and `silent` is false |
| `values()` | a generator of `(name, ValueType, value)` for each value of the key | |

`RegistryError` is the base exception and `ValueNotFound` its only subclass. `Access` (a `Flag`), `MainKey` and
`ValueType` (both `Enum`) give names to the `winreg` constants. `python registry.py` prints the values under
`HKCU/Software/Microsoft/Windows/CurrentVersion/Run`.

## Autostart on each platform

`SettingsPanel` in `gui.py` shows the `Autostart:` and `Autostart into tray:` checkboxes; macOS shows only the
first. When the panel is built, `_query_autostart` sets the Autostart checkbox from the system. A click on either
checkbox calls `update_autostart`, which stores the `autostart_tray` setting and writes or removes the entry.

The command the entry runs comes from `_get_autostart_path`: the quoted `SELF_PATH`, then one flag of `-` and as
many `v` letters as the index of the current logging level in `LOGGING_LEVELS` (such as `-vv`, none at index 0),
then `--tray` when Autostart into tray is checked. From source, the command starts with `pythonw` from the
`env/` scripts folder (`SCRIPTS_PATH`, [constants.md](constants.md#working-directory-and-paths)), which only a
Windows virtual environment has ([task 015](../refinements/tasks/015-autostart-on-linux-and-macos.md)).

| Platform | Where the entry is | What it contains |
| --- | --- | --- |
| Windows | The value `TwitchDropsMiner` (`AUTOSTART_NAME`) under `HKCU/Software/Microsoft/Windows/CurrentVersion/Run` (`AUTOSTART_KEY`), as `REG_SZ` | The command |
| Linux | `~/.config/autostart/TwitchDropsMiner.desktop`, or `$XDG_CONFIG_HOME/autostart/TwitchDropsMiner.desktop` when `XDG_CONFIG_HOME` is set and that `autostart` folder exists | A `[Desktop Entry]` with `Exec=sh -c '<command>'` |
| macOS | `~/Library/LaunchAgents/com.devilxd.twitchdropsminer.plist` | A plist with `Label`, `ProgramArguments` (the command split by `shlex.split`) and `RunAtLoad` set to true |

Autostart counts as on when the entry contains the quoted `SELF_PATH` of the running copy; on macOS the path is
not quoted, and on Windows the value must also be `REG_SZ`. A copy of the app at another path therefore shows
the checkbox off, even when another copy has an entry. The Linux branch does not create the `autostart` folder,
so writing the entry fails when that folder does not exist
([task 015](../refinements/tasks/015-autostart-on-linux-and-macos.md)); the macOS branch creates `LaunchAgents`.
The plist label keeps the `com.devilxd` prefix ([ADR-0007](../adr/ADR-0007-kept-identifiers.md)).

## Invariants

- Every import of `registry` is behind `sys.platform == "win32"`, because `import winreg` fails on other
  systems. The AppImage still copies and compiles `registry.py` with the other top-level files; compiling does not
  import it.
- A read opens the key with `read_only=True`, so it asks Windows for no more access than it uses.
- A change to `AUTOSTART_NAME`, `AUTOSTART_KEY` or the file paths leaves existing entries in place: the app no
  longer finds them, and they still start it at login.

**Dependencies.** The standard library only (`winreg`). It imports no repo module.
