# ADR-0007: Identifiers kept from the original project

**Status:** Accepted (2026-10-18)

## Context

The app is named "Twitch Drops Miner" and does not present itself as DevilXD's work
([ADR-0001](ADR-0001-independent-project.md)). The window title (`WINDOW_TITLE` in `constants.py`),
`app_name` in `build.spec` and the header of `manual.txt` use that name with no byline, so the builds are
`Twitch Drops Miner.exe` and `Twitch Drops Miner.app`. The About box links this repository and credits the
original project.

Some names from the original project are not shown in the app but are stored on the user's machine: the
autostart entry the app writes, and the names the AppImage gives its desktop integration. The app finds its
autostart entry only by its name, so a rename has effects on machines that already have the app installed.

## Decision

1. **Keep the autostart names.** `SettingsPanel.AUTOSTART_NAME` in `gui.py` is `"TwitchDropsMiner"`, and it
   forms the name of the autostart entry on every platform:

   - **Windows:** the registry value `TwitchDropsMiner` under the key
     `HKCU/Software/Microsoft/Windows/CurrentVersion/Run` (`AUTOSTART_KEY`).
   - **Linux:** the file `TwitchDropsMiner.desktop` in `$XDG_CONFIG_HOME/autostart` when that folder exists,
     otherwise in `~/.config/autostart` (`_get_linux_autostart_filepath`).
   - **macOS:** the LaunchAgent `~/Library/LaunchAgents/com.devilxd.twitchdropsminer.plist`, whose `Label` is
     `com.devilxd.twitchdropsminer` (`_get_mac_autostart_filepath` and `update_autostart`).

   `_query_autostart` looks for the entry under this name only, and `update_autostart` writes and deletes it
   under this name only. With a new name, the app would not find or remove an entry that an older build
   wrote.

2. **Keep the AppImage id `io.github.devilxd.twitchdropsminer`.** `appimage/AppImageBuilder.yml` sets it as
   `app_info.id` and `app_info.icon`, and copies the icon to
   `usr/share/icons/hicolor/128x128/apps/io.github.devilxd.twitchdropsminer.png`. A desktop entry made for an
   older AppImage refers to this id. The app writes no desktop entry of its own besides the autostart file, so
   it has no code that could remove an entry made under an old id.

3. **Credits are not identifiers and stay.** The README with its translator credits, `LICENSE`,
   `LICENSE.MIT` and the About box's "Based on:" row keep naming DevilXD.

## Consequences

- A rename leaves the entry under the old name on the machine. The app no longer finds it, so the `Autostart`
  checkbox shows off, and turning the option off does not remove it. The old entry still runs the command it
  holds at each login.
- The Windows registry value, the Linux autostart file and the macOS plist each contain the path of the app,
  and `_query_autostart` checks for the app's own path. A new build at a different path, such as
  `Twitch Drops Miner.exe` in place of `Twitch Drops Miner (by DevilXD).exe`, therefore shows the checkbox as
  off. Turning it on again writes the entry under the same name, which replaces the old one. The README's
  [Windows notes](../../README.md#notes-about-the-windows-build) give the same step for an app moved to another
  folder.
- Renaming any autostart name needs a migration: on start, the app looks for the entry under the old name,
  removes it, and writes it again under the new name when the old entry holds this app's path.
  `_query_autostart` marks the place with `TODO: Consider deleting the old value to avoid autostart errors`.
  The app cannot do the same for a new AppImage id (decision 2).
- `git grep -i devilxd` outside `lang/`, `LICENSE*`, `AGENTS.md` and `docs/` finds only these identifiers, the
  About box credit with its English string in `translate.py`, and the README's credits, links and mentions of
  the original project.

## Alternatives rejected

- **Rename every identifier with the app.** Each machine that updates would keep an autostart entry under the
  old name, which the app cannot see or remove (decision 1).

## Related

- [ADR-0001](ADR-0001-independent-project.md): why the app does not present itself as DevilXD's work.
- [gui.md](../modules/gui.md) (`SettingsPanel` and autostart), [registry.md](../modules/registry.md) (Windows
  registry access).
- [building.md](../building.md): building the AppImage from `appimage/AppImageBuilder.yml`.
- [Notes about the Windows build](../../README.md#notes-about-the-windows-build) in the README: autostart and a
  moved app.
