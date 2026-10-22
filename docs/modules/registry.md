# `registry.py`

**Purpose.** Wraps the standard `winreg` module: it opens one Windows registry key and reads, writes, deletes and
lists its values. The app uses it for one thing, the Autostart setting on Windows. It imports `winreg` at the
top, so it can be imported only on Windows, and `autostart.py` imports it only when `sys.platform == "win32"`.

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

## Autostart

`RegistryValue` in [autostart.py](autostart.md) reads, writes and deletes the value `TwitchDropsMiner` under
`HKCU/Software/Microsoft/Windows/CurrentVersion/Run` through this class. [autostart.md](autostart.md) describes
the entry on each platform.

## Invariants

- Every import of `registry` is behind `sys.platform == "win32"`, because `import winreg` fails on other
  systems. The AppImage still copies and compiles `registry.py` with the other top-level files; compiling does not
  import it.
- A read opens the key with `read_only=True`, so it asks Windows for no more access than it uses.

**Dependencies.** The standard library only (`winreg`). It imports no repo module.
