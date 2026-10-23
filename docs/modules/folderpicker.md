# `folderpicker.py`

**Purpose.** The ➕ button under "Game folders" on the Settings tab opens a folder dialog. Tk's folder dialog
returns only when it closes, and the app runs Tk and asyncio on one thread
([gui.md](gui.md#how-the-gui-runs-with-asyncio)). In the app's own process the dialog would stop every task
while it is open, so the miner would send no watch request or PubSub ping and the countdown would stop. This
module shows the dialog in a child process and checks for its answer between other tasks.
`SettingsPanel.game_dir_add` in `ui/detectedgames.py` uses it. Of the app's modules it imports only `colorfonts`, which
imports none, so the child process loads only these two and the standard library. `tests/test_folderpicker.py`
runs `FolderPicker` with fake dialogs and `ChildDialog` with real child processes that run the fake functions in
`tests/fakedialog.py`.

## Public contract

- `FolderPicker(open_dialog=ChildDialog)`. `await choose(title)` opens a dialog with
  `open_dialog(title, start)`, calls its `answer()` every `POLL_SECONDS` (0.1 seconds) with `asyncio.sleep`
  between the calls, and returns the folder, or `""` when the dialog closes without one. It calls the dialog's
  `close()` when it returns and when it is cancelled. `start` is the folder that the last dialog of this picker
  returned, or `""` before the first one, for which Tk opens the working folder of the process. A cancelled
  dialog leaves `start` as it was. A new process has no memory of the last dialog, so the picker keeps it.
- `ChildDialog(title, start, ask=ask_on_top)` starts a child process with the spawn method of `multiprocessing`
  on every platform. The child runs `send_answer`, which sends what `ask(title, start)` returns through a
  one-way `Pipe` and closes it. The parent closes its own copy of the sending end, so the pipe reports the end
  of the child.
  - `answer()` returns None while nothing has arrived, then the folder. It returns `""` when the child ended
    without an answer, such as when Tk could not open a window. The child then prints its traceback to its
    standard error.
  - `close()` kills the child and waits for it to end.
  - The child is a daemon process, so `multiprocessing` ends it when the app exits instead of waiting for it.
- `ask_on_top(title, start)` calls `skip_color_fonts` ([colorfonts.md](colorfonts.md)), creates a hidden Tk
  root with the `-topmost` attribute and calls `filedialog.askdirectory` with `mustexist=True` and `start` as
  the initial folder. It returns `""` on Cancel.
- `Dialog` is the `Protocol` of `answer()` and `close()` that `FolderPicker` calls. Tests pass a fake one.

## The child process

- The spawn method starts a new interpreter with `sys.executable`. From source, that is the Python of the run.
  In a PyInstaller build it is the app's executable, and `freeze_support()`, the first call in `main.py`, runs
  the child's work and exits before the rest of `main.py` ([main.md](main.md#startup-order)). In the AppImage
  it is the AppImage's own Python, and the AppImage stays mounted while the app runs.
- The child imports the main module as `__mp_main__`, so the code under `if __name__ == "__main__":` does not
  run in it. From `main.py` it gets only the import of `freeze_support`. In the preview, `python gui.py`, it
  imports `gui.py` and the modules that `gui.py` imports. It then imports this module for `send_answer` and
  `ask_on_top`. The parent translates the title and passes it in.
- On Linux and macOS, `multiprocessing` also starts its resource tracker at the first dialog. It is an idle
  Python process of about 12 MB, which runs until the app exits.
- The dialog has no parent window in the app. Tk on X11 centers it on the screen and gives it Tk's own window
  icon.

On Linux, a run from source and a PyInstaller one-file build both open the dialog in the child, and the window
and the other tasks keep running while it is open. Nobody has run it on Windows, on macOS or in the AppImage.
There, check that the dialog appears in front of the main window and that the app starts the child without a
second window of the app.

## Invariants

- One dialog at a time: `SettingsPanel` disables the ➕ button until `choose` returns.
- Of the app's modules, the module imports only `colorfonts`, which imports none, because the child imports it.
- The main module keeps all of its work under `if __name__ == "__main__":`
  ([main.md](main.md#invariants)).

**Dependencies.** Repo modules: `colorfonts`. Otherwise the standard library only (`asyncio`, `multiprocessing`,
`tkinter`).
