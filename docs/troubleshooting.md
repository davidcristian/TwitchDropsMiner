# Troubleshooting

This page lists common problems with Twitch Drops Miner and what to do about each one. For running from source
and building, see [building.md](building.md).

## Where the app keeps its files

The app keeps its files in the folder it runs from: the folder of the executable, of the `.AppImage` file, or of
`main.py` when it runs from source. The macOS app keeps them in `Contents/MacOS` inside the app bundle.

| File | What it holds |
| --- | --- |
| `cookies.jar` | The login session. Anyone who has this file can use your Twitch account. |
| `settings.json` | The settings from the Settings tab, including the Priority and Exclude lists and the game folders. |
| `lock.file` | The lock that stops a second copy of the app from starting in the same folder. |
| `log.txt` | The log in UTF-8, written only when the app starts with `--log`. |
| `dump.dat` | Campaign data, written only when the app starts with `--dump`. |
| `cache/` | Game and drop images. |

**"Saving failed, retrying at the next reload"** in the Output box means the app could not write `settings.json`
or `cache/mapping.json`, for example because the disk is full or another program has the file open. The app
keeps running and writes the files again at the next reload and when it closes. Free some disk space or close the
other program, because a setting changed since the last save is lost when the app ends before a save succeeds.

**"Could not save cookies.jar"** or **"Could not save cache/..."** in the Output box means the same for the login
session or an image. The app keeps running. The old `cookies.jar` stays as it was, and the app saves the login
again when it closes or restarts. You log in again at the next start only when no save succeeded and the old
file holds no valid login. An image that could not be saved is downloaded again at the next start.

## Command line flags

Add the flags after the program name, in a terminal or in a shortcut. For example:

```bash
./Twitch.Drops.Miner-x86_64.AppImage -vvv --log
```

From source, the same command is `env/bin/python main.py -vvv --log`.

| Flag | What it does |
| --- | --- |
| `-v` | Shows more messages in the Output box. Repeat it for more detail: `-vv`, `-vvv`, up to `-vvvv`. The Output box keeps the last 5000 lines. |
| `--log` | Also writes the log messages to `log.txt`, with the detail that `-v` sets. These are the Output lines that start with a level, such as `ERROR:`; the other lines are not written. |
| `--dump` | Writes the campaign data to `dump.dat`, without your user ID in the drop IDs, then closes the app. It runs one full reload, so use it once, not on every start. |
| `--tray` | Starts the app hidden in the tray. On macOS it has no effect. |
| `--version` | Shows the version in a dialog, then closes the app. |

[`manual.txt`](../manual.txt), which comes with every release, also lists the exit codes.

## The app does not start

- **Nothing happens when you start the app.** Another copy of the app is running from the same folder,
  maybe hidden in the tray. The second copy exits without a message. Close the first copy, or end it in the task
  manager. You never need to delete `lock.file`: the lock ends when the copy that holds it ends, even after a
  crash.
- **A "Cannot start" dialog.** The app cannot write to the folder it runs from, where it keeps its files, for
  example because the folder is read only or only an administrator can change it. The dialog shows the error.
  Move the app to a folder you can write to, such as one in your home folder.
- **A "Settings error" dialog.** `settings.json` is not valid JSON. Correct the file or delete it. Without it the
  app starts with the default settings, so your lists and game folders are lost. Close the app before you edit
  `settings.json`, because the app writes the file when it closes. Without a message, the app drops a setting
  with an unknown name and resets a value of the wrong type to its default. It removes an entry that is not text,
  such as a number, from the Priority, Exclude and game folder lists, and prints a warning for each to the
  terminal it was started from.
- **The AppImage prints "Cannot mount AppImage, please check your FUSE setup."** The system or container lacks
  FUSE, with which an AppImage mounts its files. Start it with `--appimage-extract-and-run`, or with
  `APPIMAGE_EXTRACT_AND_RUN=1` set: it then extracts its files into a temporary folder and starts the app. A
  SIGTERM to the process you started still closes the app and saves its files
  ([parentexit.md](modules/parentexit.md)).
- **An "Argument Parser Error" dialog.** The app was started with a flag it does not know. Check the shortcut or
  the command against the table above. After `--version`, this dialog shows the version and is not an error
  ([task 025](refinements/tasks/025-version-and-help-shown-as-error.md)).

## Logging in

The app logs in through Twitch's device activation page, not through a password:

1. Press `Login` in the Login Form on the Main tab.
2. The Output box shows a code, and a few seconds later your browser opens the Twitch activation page. If no
   browser opens, go to <https://www.twitch.tv/activate> yourself.
3. Log in to Twitch in the browser with the account the app should mine on, and enter the code.

The app checks every few seconds whether you entered the code. When the code expires first, press `Login` again
for a new one.

**To log out or switch accounts**, press `Invalidate` on the Help tab. It ends the session at Twitch, deletes
`cookies.jar` and starts the login again. Another way is to close the app, delete `cookies.jar` and start the app.
Delete `cookies.jar` the same way when the login keeps failing. When Twitch rejects the saved session, the app
deletes it and asks you to log in again by itself. When `cookies.jar` is damaged, the app asks you to log in
again, and with `-v` the Output box shows "Could not load cookies.jar" with the error.

**"Unexpected content type returned, usually due to being redirected."** Something between the app and Twitch
sent the response instead of Twitch. This happens on networks that need a login page before they allow internet
access. Log in to the network in a browser. If you set a proxy on the Settings tab, check it as well.

## Nothing is mined

- **"No active campaigns to mine drops for."** No campaign is left that the app may mine. Check that:
  - your Twitch account is linked to the game accounts on the
    [campaigns page](https://www.twitch.tv/drops/campaigns);
  - the Priority list or the installed games include the game, when Priority mode is "Priority list only". With
    an empty Priority list and no installed games, that mode mines nothing;
  - the game is not on the Exclude list.
- **"No available channels to watch."** No channel that can give the drop is live. The app checks for new
  streams on the interval set by "Check for new streams every", and starts watching when it finds one.
- **Progress is wrong or stops.** Do not watch streams on the same account while the app runs, as
  the [README](../README.md#notes) explains. Also turn off both options in the Advanced section of the Settings
  tab, because they make the app misbehave.
- **A change to the lists or to Priority mode has no effect.** The app applies these changes on the next reload,
  which runs once an hour. Press `Reload` on the Settings tab to apply them now.

## Priority and Exclude lists

An entry ignores case, accents, punctuation and the `™`, `℠` and `®` signs, so `pokemon go` matches
`Pokémon GO`. `&` counts as `and`.

- `*` matches any run of characters, including none: `Pokemon*` matches `Pokémon Scarlet`.
- `?` matches exactly one character: `FIFA 2?` matches `FIFA 23`, but not `FIFA 2` or `FIFA 234`.
- An entry without a wildcard matches one game only: `Rust` does not match `Rust Console Edition`, but `Rust*`
  does.
- A space next to a wildcard counts: `Battlefield ?` matches `Battlefield 6`, and `Call of Duty *` matches
  `Call of Duty: Warzone` but not `Call of Duty`. `Call of Duty*` matches both.

When you add an entry with a wildcard, the Output box lists the games with a campaign that it matches, or says
that it matches none. The Games Being Mined table on the Settings tab shows, for each game, the Priority entry
that matched it or that it is installed. When a Priority entry never appears in the table, no game is mined
because of it.

An excluded game is never mined, even when a Priority entry or the installed game detection matches it. The
[README](../README.md#usage) explains the three Priority modes.

## Installed games are not detected

Add a Steam or Epic games folder on the Settings tab. The app scans it at once; `Rescan` scans the folders again.

- **Steam:** add the Steam folder, its `steamapps` folder or `steamapps/common`. One folder is enough, because
  the app reads `libraryfolders.vdf` and scans the Steam libraries on other drives as well.
- **Epic Games Launcher:** add the games folder. The app also reads the launcher's own manifest folder when it
  exists: `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests` on Windows, usually in `C:\ProgramData`, and
  `~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests` on macOS.
- **Legendary and Heroic:** the app reads the `installed.json` index of Legendary and of Heroic in their default
  folders, also for Heroic as a Flatpak and when `XDG_CONFIG_HOME` or `LEGENDARY_CONFIG_PATH` is set, so any
  added folder is enough. When the index is in another folder, add that folder.
  [gamelib.md](modules/gamelib.md#launcher-indexes) lists the folders that are read.

The Output box shows `Game scan: No Steam or Epic games found in: ...` when a folder holds neither. When the Epic
launcher's manifests folder holds a game, or a Legendary or Heroic index exists, every folder counts as an Epic
folder, so the line does not appear. A line `Game scan: <path>: <reason>` names a folder, or a Steam library
that `libraryfolders.vdf` lists, that the app could not read, for example because the user may not open it. The
other folders and libraries are still scanned. The Detected Games section lists the games with a campaign that an
installed game matched, each once even when two launchers installed it. The line under the list counts installed
games, so such a game counts twice there. Only games with a campaign can match, and a name that is not a clear match
is left out. A name shown with `≈` was not an exact match; when it is the wrong game, add that game to the Exclude
list. When an installed game is missing, add it to the Priority list by hand.

## The tray icon on Linux

The tray icon uses [pystray](https://pystray.readthedocs.io/). The release builds include the AppIndicator
library it needs. A run from source needs the system packages listed in
[building.md](building.md#requirements).

- **No tray icon appears.** The desktop must show AppIndicator icons. GNOME shows them only with an extension
  such as "AppIndicator and KStatusNotifierItem Support".
- **The window disappears and no icon appears** after `Minimize to Tray`, or at start with `--tray` or "Autostart
  into tray". The app is still running. End it from a terminal or a system monitor, then turn off "Autostart into
  tray" until the tray icon works.
- **The tray icon has no menu.** When the AppIndicator and GTK backends of pystray fail to load, or the app
  cannot connect to a DBus session bus, which these two backends need, the app uses its X11 backend and prints a
  warning that starts with `Tray icon:` to standard error. The release builds do so on an X11 system without
  `libwayland-client0`, `libwayland-cursor0` and `libwayland-egl1`, and the AppImage also without
  `libxcb-render0` (Debian and Ubuntu names). A desktop session starts a session bus, but a bare X server, a
  container or an SSH session may have none. The X11 icon has no menu and shows no notifications. A left click
  on it shows the window, and a right click does nothing. To quit, show the window and close it. When the app
  starts before its tray, the icon appears once the tray has started. Install these libraries, or `libgtk-3-0`,
  which depends on them, and start the app in a session with a bus to get the AppIndicator icon.
- **Another tray backend.** pystray chooses its backend from the `PYSTRAY_BACKEND` environment variable when it
  is set, for example to `gtk` or `xorg`.

## Symbols show as empty boxes on Linux

In a run from source, symbols such as ❌, ⏳ and ➕ show as empty boxes when libXft, the library with which Tk
draws text, is older than 2.3.5, and the first font with these symbols is a color emoji font, such as Noto Color
Emoji. Ubuntu 22.04 has libXft 2.3.4. Such a libXft cannot draw color fonts, and a glyph of one can end the app
with a segmentation fault, so the app leaves color fonts out ([colorfonts.md](modules/colorfonts.md)). Install a
font with black and white versions of the symbols, such as Symbola (`fonts-symbola` on Debian and Ubuntu), or
use a release build, which includes libXft 2.3.9 and shows them in color.

## Reporting a problem

Report a problem on this project's [Issues page](https://github.com/davidcristian/TwitchDropsMiner/issues). Do
not report it on DevilXD/TwitchDropsMiner, whose code differs. Include:

- the version, from `--version` or the window title;
- your operating system and the build you use: Windows, macOS, AppImage, Linux PyInstaller or source;
- the steps that lead to the problem;
- `log.txt` from a run with `-vvv --log`, read first so that it contains nothing private. The app writes
  `<hidden>` in place of your login token.

Never share `cookies.jar`.
