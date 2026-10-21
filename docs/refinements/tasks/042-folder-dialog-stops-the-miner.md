# The game folder dialog stops the miner while it is open

**Status:** done 2026-10-21
**Area:** gui (`SettingsPanel`)
**Origin:** Found on 2026-10-20: a timer task stopped for as long as the game folder dialog was open
**Verified:** 2026-10-21

The ➕ button under "Game folders" on the Settings tab calls `SettingsPanel.game_dir_add` in `gui.py`, which calls
`filedialog.askdirectory`. That call returns only when the user closes the dialog. It runs in a Tk callback inside
`dooneevent` in the `GUIManager._poll` task, so the asyncio event loop runs no other task until it returns. While
the dialog is open the miner sends no watch request and no PubSub ping, and the drop countdown stops. The tasks
continue when the dialog closes, so the loss is the mining time while the dialog is open.

## How it was confirmed

The preview (`python gui.py`) ran under Xvfb with the network blocked. A task that runs every 0.5 seconds started,
the ➕ button was invoked, and a press on the dialog's Cancel button followed 4 seconds later:

```text
button callback returned after 4.0 s
ticks: 10, largest gap: 4.0 s (expected 0.5)
```

On X11, Tk's dialog waits in a nested Tcl event loop (`vwait` in `choosedir.tcl`). On Windows and macOS
`askdirectory` shows the system dialog and also returns only when it closes; that was not run.

## What a fix involves

Tk has no folder dialog that returns at once. A Tcl timer handler still runs during the dialog, but asyncio
cannot run a task from there: `run_until_complete` raises `RuntimeError` ("This event loop is already
running"), and a task step raises `RuntimeError` ("Cannot enter into task") while the `_poll` step is running.
Only the event loop thread may call Tk ([gui.md](../../modules/gui.md#invariants)). The options:

- Run the dialog in a child process of the app and await its output. This needs a mode in `main.py` that runs
  before the single instance lock, a separate command for a run from source, the PyInstaller build and the
  AppImage. The dialog then has no parent window. Its Windows and macOS behavior cannot be checked on Linux.
- Replace the dialog with a text entry for the path, like the Priority and Exclude lists. This removes the
  pause, and every user then types or pastes the path of a Steam or Epic folder.
- A text entry beside the ➕ button keeps the pause for every use of the dialog.

None of them adds a Twitch request. The dialog stays because the pause lasts only while the user keeps it open,
in a step most users take once. The first fix needs builds that cannot be tested here, and the second makes
adding a folder harder for every user. [troubleshooting.md](../../troubleshooting.md#installed-games-are-not-detected)
tells users that mining stops while the dialog is open.

## History

- 2026-10-20: Opened. A task that ran every 0.5 seconds stopped for as long as the game folder dialog was open.
  The limit was written into gui.md and troubleshooting.md.
- 2026-10-21: Closed. `folderpicker.py` shows the dialog in a child process started with the spawn method, and
  `game_dir_add` awaits the answer in a task, with the ➕ button disabled until it comes. Under Xvfb with the
  network blocked, in `python gui.py` and `python main.py`, the 0.5 second task kept a largest gap of 0.53
  seconds while the dialog was open, a chosen folder was added and Cancel added none. A PyInstaller one-file
  build on Linux switched tabs while the dialog was open and saved the chosen folder. Windows, macOS and the
  AppImage were not run.
