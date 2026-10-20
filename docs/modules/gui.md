# `gui.py`

**Purpose.** The whole tkinter window: four tabs, the tray icon, the light and dark themes, and a preview that
opens the window with mock data. `Twitch.__init__` creates one `GUIManager`, and the rest of the app changes the
window only through that object and the parts it exposes as attributes. The file has about 3300 lines, over ten
times the 300 line cap in [AGENTS.md](../../AGENTS.md#module-map), so new logic that does not need tkinter goes in
a new module ([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)). Before a search and replace edit
in this file, read the `gui.py` recipe in [AGENTS.md](../../AGENTS.md#recipes).

## The window

`GUIManager.__init__` builds each part and keeps it as an attribute. The labels in quotes are the English strings
from [translate.md](translate.md).

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
  `get_selection()` and watches the selected channel when `Twitch.can_watch` allows it. `display(channel,
  add=True)` adds a row, or updates the row with the same `iid` and stores the new object for it, so
  `get_selection()` returns the object that `Twitch.channels` holds and not an older one with the same `id`.
- **`CampaignProgress`** counts down the current minute in its own `_timer_loop` task, one step per second.
  `minute_almost_done()` returns `True` when no countdown runs or `ALMOST_DONE_SECONDS` (10) or fewer are left;
  `Twitch._watch_loop` calls it to decide whether to send the `CurrentDrop` GQL query.
- **`InventoryOverview.add_campaign`** is a coroutine, because it awaits `ImageCache.get` for the campaign and
  reward images ([cache.md](cache.md)). The filters are "Not linked", "Upcoming", "Expired", "Excluded" and
  "Finished". `refresh()` applies them again, and it runs each time the Inventory tab is opened. The campaigns are on
  a `tk.Canvas`. When the pointer enters it, `bind_all` binds the events that `wheel_events` returns, and leaving it
  removes them. `wheel_scroll` gives the direction, and Shift scrolls sideways ([mousewheel.md](mousewheel.md)).
- **`SettingsPanel`** has the sections "Games Being Mined" (filled by `set_wanted_games`), "General", "Advanced",
  "Priority", "Exclude" and "Detected Games". It writes each change to `Settings` at once
  ([settings.md](settings.md)). "Reload" sets `State.INVENTORY_FETCH` through `Twitch.state_change`, a full
  reload ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)). "Rescan" and the folder buttons start
  `Twitch.detect_games` ([ADR-0004](../adr/ADR-0004-installed-game-detection.md)). Adding a list entry with `*`
  or `?` prints the games it matches ([ADR-0005](../adr/ADR-0005-list-patterns.md)). The "Autostart" checkbox
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
  `TKINTER_DONT_WAIT` (`1 << 1`) until no Tk event is left, then sleeps 0.05 seconds. With that flag Tcl returns
  at once on an empty queue, which stops Tk from blocking inside an X11 or Wayland call during a large redraw.
- `Twitch._run` calls `start()` at the beginning of each run. `stop()` cancels the poll task and the progress
  timer; [main.py](main.md) calls it after the window is closed.
- A Tk callback that needs async work starts a task: `HelpTab.invalidate_token` and
  `SettingsPanel.rescan_games` call `start_task(task_wrapper(...)())`, which keeps a reference to the task until
  it ends ([utils.md](utils.md#tasks)). A button that changes the state uses `Twitch.state_change(state)`, which
  returns a `partial` of `Twitch.change_state`. `change_state` keeps only the last state set, so `_run` can
  replace a press that comes during a fetch
  ([task 012](../refinements/tasks/012-button-requests-lost-during-a-fetch.md)).
- `close()` sets `_close_requested` and calls `Twitch.close()`, which sets `State.EXIT`. The window's close
  button, the tray menu's "Quit" and, on Linux, SIGINT and SIGTERM call it. On Windows, `wnd_proc` replaces the
  window procedure so that `WM_CLOSE` and `WM_QUERYENDSESSION` call it, and `ShutdownBlockReasonCreate`
  registers "Exiting..." as the text Windows shows while the app finishes during a system shutdown.
- `coro_unless_closed(coro)` returns the result of `coro`, or cancels it and raises `ExitRequest` when the
  window closes first. When its caller is cancelled, it cancels `coro` too. `Twitch.request` runs every HTTP
  request through it.
- `prevent_close()` clears the close request, so the window stays open to show a fatal error.
- `close_window()` stops the tray icon, removes the log handler and destroys the Tk root.

`GUIManager.__init__` adds a `_TKOutputHandler` with `OUTPUT_FORMATTER` to the `TwitchDrops` logger, so every log
record at the level set by `-v` that is logged on the event loop thread also appears in the Output box. A record
from another thread does not ([Invariants](#invariants)).

## Public contract

Other modules use these names. Everything else in the file is internal to the GUI.

| Caller | What it uses |
| --- | --- |
| `twitch.py` | `GUIManager(twitch)`; `start`, `close`, `close_requested`, `wait_until_closed`, `coro_unless_closed`, `prevent_close`, `print`, `save`, `set_games`, `clear_drop`; `status.update`; `tray.change_icon`; `channels.clear`, `clear_watching`, `set_watching`, `get_selection`, `set_selection`, `get_iids`; `inv.add_campaign`, `inv.clear`; `progress.minute_almost_done`, `progress.stop_timer`; `settings.set_wanted_games`, `set_detected`, `set_scanning`; `login.ask_enter_code`, `login.update`; `help._invalidate_button` |
| `inventory.py` | `display_drop`, `inv.update_drop`, `tray.notify` |
| `channel.py` | `channels.display`, `channels.remove` |
| `websocket.py` | `websockets.update`, `websockets.remove` |
| `cache.py` | `ImageCache(manager)` reads `manager._root` and `manager._twitch` |
| `main.py` | `close`, `close_requested`, `wait_until_closed`, `status.update`, `tray.change_icon`, `grab_attention`, `stop`, `close_window` |

The GUI calls back into `Twitch` through `settings`, `change_state`, `state_change`, `close`, `detect_games`,
`get_auth`, `request` and `_client_type`. `save()` saves the image cache; `Twitch.save` calls it together with
`Settings.save`. `grab_attention(sound=True)` restores the window from the tray, focuses it and rings the bell.

## The tray icon

`TrayIcon` wraps a `pystray.Icon` named `twitch_miner`.

- The icon is created on the first `minimize()`, not at start. `pystray.Icon.run` blocks, so it runs in a thread
  of the default executor (`loop.run_in_executor`). The menu items "Show" (the default action) and "Quit" call
  back through `loop.call_soon_threadsafe`, so their handlers run on the event loop thread.
- `minimize()` hides the window and shows the icon. `restore()` hides the icon and shows the window. With
  `--tray`, `GUIManager.__init__` calls `minimize()` once the window is built.
- On macOS, `minimize()` does nothing, the button is hidden and `--tray` is ignored.
- `change_icon(state)` takes `pickaxe`, `active`, `idle`, `error` or `maint`, the files in `icons/`, and raises
  `ValueError` for any other name. It stores the state when no icon exists yet.
- `update_title(drop)` sets the tooltip to the app name, game, rewards, progress and claimed count. `get_title`
  shortens the rewards, then the game name, to fit 127 characters, and raises `MinerException` when that is not
  enough.
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
  lists of the Settings tab and the inventory canvas.
- On Windows it sets the title bar color with `DwmSetWindowAttribute` (attribute 35, `DWMWA_CAPTION_COLOR`). On
  macOS it sets the app's `NSAppearance` to `DarkAqua` or `Aqua` through `AppKit`.

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
  through `loop.call_soon_threadsafe`. One path breaks this rule: at `-vvvv`, `gamelib.common.read_text` and
  `gamelib.epic` log DEBUG records from the scan thread that `Twitch.detect_games` starts with
  `asyncio.to_thread`, and `_TKOutputHandler` calls Tk from that thread. The call raises `RuntimeError`, which
  ends the scan, and the record does not reach the Output box
  ([task 021](../refinements/tasks/021-scan-thread-logs-into-tk.md)).
- A Tk callback returns quickly and starts a task for slow work. The window and the miner share one thread, so a
  slow callback stops both. One callback breaks this rule: `SettingsPanel.game_dir_add` calls
  `filedialog.askdirectory`, which returns only when the folder dialog closes. While it is open no task runs, so
  the miner sends no watch request or PubSub ping and the countdown stops. Tk has no folder dialog that returns
  at once ([task 042](../refinements/tasks/042-folder-dialog-stops-the-miner.md)).
- Widget text comes from `_()`, except for the hard-coded strings that
  [task 014](../refinements/tasks/014-hard-coded-strings.md) lists, such as the "Language" label. Widgets read
  it when they are built, so a language change needs a restart. `SettingsPanel` reads its choice names in
  `cached_property` attributes so that no string is read before the language is set.
- `apply_theme` runs before the window is shown, because it defines the fonts and named styles the widgets use.
  A new plain Tk widget needs its own `configure_theme` call in `apply_theme`.
- The preview mock provides every setting the GUI reads and every `Twitch` attribute that building the window
  needs. It has no `detect_games`, `get_auth` or `_client_type`, so "Rescan" and the folder buttons raise
  `AttributeError` in the preview.

**Dependencies.** Repo modules: `translate`, `cache`, `gamelib`, `exceptions`, `mousewheel`, `utils`, `constants`, and
`registry` on Windows; `twitch`, `channel`, `settings` and `inventory` for type checking only. Third-party: `pystray`,
Pillow, `yarl`, pywin32 (`win32api`, `win32con`, `win32gui`) on Windows, `AppKit` on macOS, and `aiohttp` in the
preview.
