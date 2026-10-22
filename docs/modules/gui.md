# `gui.py`

**Purpose.** The whole tkinter window: four tabs, the tray icon, the light and dark themes, and a preview that
opens the window with mock data. `Twitch.__init__` creates one `GUIManager`, and the rest of the app changes the
window only through that object and the parts it exposes as attributes. The file is far over the 300 line cap
in [AGENTS.md](../../AGENTS.md#module-map), so new logic that does not need tkinter goes in a new module
([task 005](../refinements/tasks/005-modules-over-the-line-cap.md) gives its line count). Before a search and
replace edit in this file, read the `gui.py` recipe in [AGENTS.md](../../AGENTS.md#recipes).

## The window

`GUIManager.__init__` first calls `skip_color_fonts`, which leaves color fonts out of the fonts Tk uses when
libXft is older than 2.3.5 ([colorfonts.md](colorfonts.md)), and then creates the `Tk` root. It builds each part
and keeps it as an attribute. The labels in quotes are the English strings from [translate.md](translate.md).

| Attribute | Class | Tab | What it shows |
| --- | --- | --- | --- |
| `tabs` | `Notebook` | | The `ttk.Notebook` with the tabs "Main", "Inventory", "Settings" and "Help" |
| `tray` | `TrayIcon` | all | The "Minimize to Tray" button at the top right, and the tray icon |
| `status` | `StatusBar` | Main | One line that says what the app does now, such as "Fetching inventory..." |
| `websockets` | `WebsocketStatus` | Main | The state and topic count of each of the `MAX_WEBSOCKETS` (8) websockets |
| `login` | `LoginForm` | Main | The login status, the user ID and the "Login" button |
| `progress` | `CampaignProgress` | Main | Game, campaign and rewards of the current drop, two progress bars, a countdown |
| `output` | `ConsoleOutput` | Main | The Output box: a read-only `tk.Text` with a time stamp on each line |
| `channels` | `ChannelList` | Main | The channel table and the "Switch" button |
| `inv` | `InventoryOverview` | Inventory | One frame per campaign with its images and drops, and the Filter row |
| `settings` | `SettingsPanel` | Settings | The settings widgets, the lists and the "Reload" button |
| `help` | `HelpTab` | Help | About, links, help text and the "Invalidate" button |

- **`ChannelList`** has the columns Channel, Status, Game, 🎁 (drops enabled), Viewers and 📋 (the channel is on a
  campaign's list of allowed channels). "Switch" sends `State.CHANNEL_SWITCH`. `Twitch` then reads
  `get_selection()` and watches the selected channel when `Twitch.can_watch` allows it, also after a reload
  ([ADR-0017](../adr/ADR-0017-state-requests.md)). `display(channel,
  add=True)` adds a row, or updates the row with the same `iid` and stores the new object for it, so
  `get_selection()` returns the object that `Twitch.channels` holds and not an older one with the same `id`.
- **`ConsoleOutput.print`** deletes the oldest lines past `MAX_LINES` (5000). A line costs about 0.4 KB, so the
  box stays near 2 MB of memory in a run of any length. With `--log`, `log.txt` keeps every log line.
- **`ConsoleOutput`** requests `LINES` (10) lines of height. Its row is the only row of the Main tab that
  changes height with the window, and a window at its minimum height shows `MIN_LINES` (4) lines.
- **`CampaignProgress`** counts down the current minute in its own `_timer_loop` task, one step per second.
  `minute_almost_done()` returns `True` when no countdown runs or `ALMOST_DONE_SECONDS` (10) or fewer are left;
  `Twitch._watch_loop` calls it to decide whether to send the `CurrentDrop` GQL query.
- **`InventoryOverview.add_campaign`** is a coroutine, because it awaits `ImageCache.get` for the campaign and
  reward images ([cache.md](cache.md)). `clear()`, which `Twitch.fetch_inventory` calls at each reload, removes
  the campaigns and calls `ImageCache.retry_failed`, so that each failed image download is tried once more
  ([cache.md](cache.md#failed-downloads)). The filters are "Not linked", "Upcoming", "Expired", "Excluded" and
  "Finished". Without "Excluded", the tab shows only a campaign whose game `State.GAMES_UPDATE` may mine: the game
  matches no Exclude entry and, under "Priority list only", it matches a Priority entry or is in `detected_games`.
  `refresh()` applies the filters again, and it runs each time the Inventory tab is opened. The campaigns are in
  a `ScrollArea` with both scroll bars always shown. The mouse wheel scrolls it, and Shift scrolls sideways
  ([scrollarea.md](scrollarea.md)).
- **`SettingsPanel`** has the sections "Games Being Mined" (filled by `set_wanted_games`), "General", "Advanced",
  "Priority", "Exclude" and "Detected Games", side by side in a `ScrollArea` with `fit`. In a window as large
  as the sections, the tab shows them centered and no scroll bar. In a smaller window, such as on a screen 1366
  pixels wide, a scroll bar shows for each axis that needs one. The layouts with Detected Games below the other
  sections are narrower but taller than a screen 768 pixels high
  ([task 044](../refinements/tasks/044-window-wider-than-small-screens.md)), so the tab scrolls instead. It
  writes each change to `Settings` at once ([settings.md](settings.md)). "Reload" sets
  `State.INVENTORY_FETCH` through `Twitch.state_change`, a full reload
  ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)). "Rescan" and the folder buttons start
  `Twitch.detect_games` ([ADR-0004](../adr/ADR-0004-installed-game-detection.md)). The ➕ folder button opens
  the folder dialog in a child process through `FolderPicker` ([folderpicker.md](folderpicker.md)), and stays
  disabled while the dialog is open. Adding a list entry with `*` or `?` prints the games it matches
  ([ADR-0005](../adr/ADR-0005-list-patterns.md)). The "Autostart" checkbox
  writes the Windows `Run` registry value, a Linux `.desktop` file in the autostart folder or a macOS
  `LaunchAgents` plist, named after `AUTOSTART_NAME` (`TwitchDropsMiner`). `_query_autostart` finds the entry by
  these names, so a rename leaves the old entry in place ([ADR-0007](../adr/ADR-0007-kept-identifiers.md)). On
  Linux the write fails when the autostart folder does not exist, and a run from source writes a `pythonw`
  command ([task 015](../refinements/tasks/015-autostart-on-linux-and-macos.md)).
- **`HelpTab`** "Invalidate" posts the access token to `https://id.twitch.tv/oauth2/revoke`, deletes
  `cookies.jar` when Twitch returns 200, and sets `State.RESTART`. The button stays disabled until a login
  completes.

The helper widgets at the top of the file (`PlaceholderEntry`, `PlaceholderCombobox`, `PaddedListbox`,
`MouseOverLabel`, `LinkLabel`, `SelectCombobox`) are used only inside `gui.py`. `SelectMenu` is defined and not
used ([task 022](../refinements/tasks/022-unused-code.md)).

## How the GUI runs with asyncio

The asyncio event loop and Tk run on one thread, so Tk callbacks and coroutines need no locks.

- `GUIManager.start()` creates the `_poll` task in place of `Tk.mainloop()`. It calls `Tk.dooneevent` with
  `TKINTER_DONT_WAIT` (`1 << 1`) until no Tk event is left, writes the queued log records to the Output box
  ([below](#log-records-in-the-output-box)), then sleeps 0.05 seconds. With that flag Tcl returns at once on an
  empty queue, which stops Tk from blocking inside an X11 or Wayland call during a large redraw.
- `Twitch._run` calls `start()` at the beginning of each run. `stop()` cancels the poll task and the progress
  timer; [main.py](main.md) calls it after the window is closed.
- A Tk callback that needs async work starts a task: `HelpTab.invalidate_token`,
  `SettingsPanel.rescan_games` and `SettingsPanel.game_dir_add` call `start_task(task_wrapper(...)())`, which
  keeps a reference to the task until it ends ([utils.md](utils.md#tasks)). A button that changes the state
  uses `Twitch.state_change(state)`, which returns a `partial` of `Twitch.change_state`. A press during a fetch
  runs when the fetch ends, or as part of it when the fetch goes on to that state
  ([ADR-0017](../adr/ADR-0017-state-requests.md)).
- `close()` sets `_close_requested` and calls `Twitch.close()`, which sets `State.EXIT`. The window's close
  button, the tray menu's "Quit" and, on Linux, SIGINT and SIGTERM call it. On Windows, `wnd_proc` replaces the
  window procedure so that `WM_CLOSE` and `WM_QUERYENDSESSION` call it, and `ShutdownBlockReasonCreate`
  registers "Exiting..." as the text Windows shows while the app finishes during a system shutdown.
- `coro_unless_closed(coro)` returns the result of `coro`, or cancels it and raises `ExitRequest` when the
  window closes first. When its caller is cancelled, it cancels `coro` too. `Twitch.request` runs every HTTP
  request through it.
- `prevent_close()` clears the close request, so the window stays open to show a fatal error.
- `close_window()` stops the tray icon, removes the log handler and destroys the Tk root.

### Log records in the Output box

`GUIManager.__init__` adds a `_TKOutputHandler` with `OUTPUT_FORMATTER` to the `TwitchDrops` logger, so every log
record at the level set by `-v` also appears in the Output box. The handler writes a record of the event loop
thread at once. A record that another thread logs, such as a `DEBUG` record of the game scan thread at `-vvvv`,
waits in a `queue.SimpleQueue` of the handler. `_poll` writes the queued records on each pass, and a record of the
event loop thread writes them before itself, so the lines keep the order of the log calls. A queue, rather than
`loop.call_soon_threadsafe` as the tray menu uses, needs no running event loop when the window is built, and the
tests build it without one.

## Public contract

Other modules use these names. Everything else in the file is internal to the GUI.

| Caller | What it uses |
| --- | --- |
| `twitch.py` | `GUIManager(twitch)`; `start`, `close`, `close_requested`, `wait_until_closed`, `coro_unless_closed`, `prevent_close`, `print`, `save`, `set_games`, `clear_drop`; `status.update`; `tray.change_icon`; `channels.clear`, `clear_watching`, `set_watching`, `get_selection`, `set_selection`, `get_iids`; `inv.add_campaign`, `inv.clear`; `progress.minute_almost_done`, `progress.stop_timer`; `settings.set_wanted_games`, `set_detected`, `set_scanning`; `login.ask_login`, `login.ask_enter_code`, `login.update`; `help._invalidate_button` |
| `inventory.py` | `display_drop`, `inv.update_drop`, `tray.notify` |
| `channel.py` | `channels.display`, `channels.remove` |
| `websocket.py` | `websockets.update`, `websockets.remove` |
| `cache.py` | `ImageCache(manager)` reads `manager._root` and `manager._twitch` |
| `main.py` | `close`, `close_requested`, `wait_until_closed`, `status.update`, `tray.change_icon`, `grab_attention`, `stop`, `close_window` |

The GUI calls back into `Twitch` through `settings`, `change_state`, `state_change`, `close`, `detect_games`,
`get_auth`, `request` and `_client_type`. `save()` saves the image cache; `Twitch.save` calls it together with
`Settings.save`. `grab_attention(sound=True)` restores the window from the tray, focuses it and rings the bell.

## The tray icon

`TrayIcon` wraps a `pystray.Icon` named `twitch_miner`. `gui.py` imports pystray through `import_pystray`, which
chooses the tray backend, and creates the icon from `icon_class(pystray.Icon)`, which makes the icon of the X11
backend receive clicks ([traybackend.md](traybackend.md)).

- The icon is created on the first `minimize()`, not at start. `pystray.Icon.run` blocks, so it runs in a thread
  of the default executor (`loop.run_in_executor`). The menu items "Show" (the default action) and "Quit" call
  back through `loop.call_soon_threadsafe`, so their handlers run on the event loop thread.
- `minimize()` hides the window and shows the icon. `restore()` hides the icon and shows the window. With
  `--tray`, `GUIManager.__init__` calls `minimize()` once the window is built.
- With the X11 backend, `restore()` stops the icon instead of hiding it, because `hides_by_stopping` returns True
  for it ([traybackend.md](traybackend.md)), and the next `minimize()` creates a new icon. While the window is
  open, no icon exists: `change_icon` only stores the state, `update_title` and `notify` do nothing, and the new
  icon takes the stored state and the title of the drop on the Main tab. `restore()` stops the icon only once
  pystray's setup thread has shown it and `visible` is True. pystray's `stop` does nothing before the icon thread
  marks the icon ready, and a stop while the setup thread still waits for a change can leave that thread waiting
  forever. A `restore()` before that, which only `grab_attention` can cause, keeps the icon, and the next
  `restore()` stops it.
- On macOS, `minimize()` does nothing, the button is hidden and `--tray` is ignored.
- `change_icon(state)` takes `pickaxe`, `active`, `idle`, `error` or `maint`, the files in `icons/`, and raises
  `ValueError` for any other name. It stores the state when no icon exists yet.
- `update_title(drop)` sets the tooltip to three lines: the app name, the game, and the rewards with the progress
  and claimed count. `get_title` shortens the rewards, then the game name, to fit 127 characters, and raises
  `MinerException` when that is not enough.
- `notify(message, title)` shows a notification for 10 seconds when `tray_notifications` is on and the icon
  exists. `BaseDrop.claim` calls it after a claim with the title "Mined Drop".

The Linux tray needs AppIndicator support; [troubleshooting.md](../troubleshooting.md#the-tray-icon-on-linux)
lists the problems.

## The theme and dark mode

`apply_theme(dark)` runs at the end of `GUIManager.__init__` with the `dark_mode` setting, and again from the
"Dark mode" checkbox through `SettingsPanel.update_dark_mode`, so a change shows at once.

- Dark mode switches ttk to the `clam` theme, except on macOS, because `clam` accepts the color changes. Light
  mode switches back to the theme that was active at start (`_orig_theme_name`).
- It sets the colors of the ttk styles, defines the fonts and the named styles `Large.TButton`, `Arrow.TButton`,
  `Link.TLabel` and `MS.TLabel`, and writes Tk option database entries for the combobox drop-down lists.
- Plain Tk widgets ignore ttk styles, so it calls `configure_theme` on the Output box, the four `PaddedListbox`
  lists of the Settings tab and the canvases of the Inventory and Settings tabs.
- On Windows it sets the title bar color with `DwmSetWindowAttribute` (attribute 35, `DWMWA_CAPTION_COLOR`). On
  macOS it sets the app's `NSAppearance` to `DarkAqua` or `Aqua` through `AppKit`.
- Last, it calls `MinimumSize.measure` ([scrollarea.md](scrollarea.md)), which sets the window's minimum size
  to the size the window requests while the Settings tab's area is `collapsed()` and the Output box is
  `shortened()` to `MIN_LINES`, because the fonts and paddings of the theme change that size. The Settings tab
  scrolls, so the widest tab that cannot scroll, the Main tab, sets the minimum. In the preview on Linux the
  minimum is 865 by 602 pixels in light mode and 878 by 636 in dark mode before the mock data arrives.
- `MIN_LINES` is 4, so the minimum height fits a screen 720 pixels high. On that screen Tk on X11 allows a
  window 690 pixels high, and on Windows a taskbar and a title bar leave about 650, an estimate that was not
  measured. With all 10 lines the minimum height in dark mode was 738 pixels; with 4 it is 636.
- The Main tab grows later, for example when a long channel name widens a column of the channel table. After
  each pass over the Tk events, `_poll` calls `MinimumSize.follow`, which measures again when the Main,
  Inventory or Help tab requests a new size. In the preview the minimum width becomes 928 pixels in light mode
  and 941 in dark mode.

After `apply_theme`, `GUIManager.__init__` calls `_fit_to_screen`. When the window requests more than
`wm maxsize`, which Tk sets from the screen size (on X11, the screen less 15 by 30 pixels for the window
frame), the window opens at `fitted_size` of the two and the Settings tab scrolls. Otherwise the window keeps
following its requested size, so a large screen shows it as before. On a screen 1366 by 768 pixels the preview
window is 1351 pixels wide. On a screen 1280 by 720 pixels it is 1265 by 690 in both themes, and the Output box
has room for 9 lines in light mode and 7 in dark mode. On macOS in CI the window opened 20 pixels smaller than
`wm maxsize` on each axis ([task 072](../refinements/tasks/072-macos-window-smaller-than-wm-maxsize.md)).

## The preview

`python gui.py` runs the block under `if __name__ == "__main__":`. `constants.py` treats a run of `gui.py` like a
run of `main.py`, so the preview uses the repository folder as its working folder.

- It builds a mock `Twitch` from `SimpleNamespace`: `settings` with each setting the GUI reads, `change_state`
  that prints the state number to the Output box, `state_change`, `request` set to `aiohttp.request`, and
  `close` set to `GUIManager.stop`.
- It fills the window with a login status, three games, four channels (offline, pending and two online, the
  pending one marked as watched), one campaign with one drop and two Output messages. It also calls
  `tray.notify`, which shows nothing, because no tray icon exists until `minimize()` runs.
- Over about 90 seconds it moves the drop display through a still display, a countdown, a cleared display, a
  drop one minute from the end and a finished drop. Closing the window ends the preview.
- `ImageCache` downloads two images from `static-cdn.jtvnw.net` on every run. The preview never calls
  `GUIManager.save`, so it writes the image files to `cache/` but not `cache/mapping.json`, which maps each URL
  to its file. The preview sends no GQL request.

A new setting that the GUI reads needs an entry in the mock `settings`, or the preview fails with an
`AttributeError` ([AGENTS.md](../../AGENTS.md#recipes)). To run the preview without a display, follow
[gui-preview-headless.md](../runbooks/gui-preview-headless.md).

## Invariants

- Only the event loop thread calls Tk, because Tk is not thread safe. The pystray thread reaches the GUI only
  through `loop.call_soon_threadsafe`, and a log record of another thread only through the queue of
  `_TKOutputHandler`. With a Tcl built with thread support, `_tkinter` passes a call from another thread to Tk
  only while Tk runs `mainloop`, which the app never calls, and otherwise raises
  `RuntimeError: main thread is not in main loop` in the calling thread after one second.
- A Tk callback returns quickly and starts a task for slow work. The window and the miner share one thread, so a
  slow callback stops both. A Tk dialog that waits for the user, such as `filedialog.askdirectory`, does not
  return until it closes, so the folder dialog runs in a child process ([folderpicker.md](folderpicker.md)).
- Widget text comes from `_()`, except for the hard-coded strings that
  [task 014](../refinements/tasks/014-hard-coded-strings.md) lists, such as the "Language" label. Widgets read
  it when they are built, so a language change needs a restart. `SettingsPanel` reads its choice names in
  `cached_property` attributes so that no string is read before the language is set.
- `apply_theme` runs before the window is shown, because it defines the fonts and named styles the widgets use.
  A new plain Tk widget needs its own `configure_theme` call in `apply_theme`.
- The preview mock provides every setting the GUI reads and every `Twitch` attribute that building the window
  needs. It has no `detect_games`, `get_auth` or `_client_type`, so "Rescan", the ❌ folder button and a folder
  chosen with ➕ raise `AttributeError` in the preview.

**Dependencies.** Repo modules: `translate`, `cache`, `colorfonts`, `gamelib`, `exceptions`, `folderpicker`,
`traybackend`, `scrollarea`, `utils`, `constants`, and `registry` on Windows; `twitch`, `channel`, `settings` and
`inventory` for type checking only. Third-party: `pystray`, Pillow, `yarl`, pywin32 (`win32api`, `win32con`,
`win32gui`) on Windows, `AppKit` on macOS, and `aiohttp` in the preview.
