# `ui/`

**Purpose.** The parts of the tkinter window that `gui.py` builds, and `run_preview`, which `python gui.py`
calls. `gui.py` stays a file, because that command names it, and its classes move here
([ADR-0020](../adr/ADR-0020-module-splits.md)). The window as a whole, `GUIManager` and `SettingsPanel`, which
are still in `gui.py`, are in [gui.md](gui.md). Every file here needs a display, so the package is outside the
coverage floor, as `gui.py` is.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | Imports the names listed in `__all__`. `gui.py` imports from `ui`, never from a file of it |
| `placeholder.py` | `PlaceholderEntry` and `PlaceholderCombobox` |
| `widgets.py` | `PaddedListbox`, `MouseOverLabel`, `LinkLabel`, `SelectCombobox` and `Notebook` |
| `status.py` | `StatusBar` and `WebsocketStatus` |
| `login.py` | `LoginForm` |
| `progress.py` | `CampaignProgress` |
| `output.py` | `ConsoleOutput` and `_TKOutputHandler`, the log handler that writes to it |
| `channellist.py` | `ChannelList` |
| `tray.py` | `TrayIcon` |
| `inventorytab.py` | `InventoryOverview`, the Inventory tab, without the two methods of its mixin |
| `dropstatus.py` | `DropStatusMixin`, a base class of `InventoryOverview` that holds `update_progress` and `update_drop`, which write the status line under each drop |
| `helptab.py` | `HelpTab` |
| `preview.py` | `run_preview`, the mock data of the preview |

## The generic widgets

Only the GUI uses them: `gui.py` and the files of this package.

- `PlaceholderEntry` is a `ttk.Entry` that shows `placeholder` in `placeholdercolor` (`grey60`) while it is
  empty. `get()` then returns an empty string. On focus it removes the placeholder and inserts `prefill`.
  `PlaceholderCombobox` is the same for a `ttk.Combobox`. The proxy field of the Settings tab is a
  `PlaceholderEntry`, and the game name fields of the Priority and Exclude lists are `PlaceholderCombobox`.
- `PaddedListbox` is a `tk.Listbox` inside a `tk.Frame`, so that it can have padding. `grid` and the other grid
  methods act on the frame. The four lists of the Settings tab are one each, and `configure_theme` sets their
  colors ([gui.md](gui.md#the-theme-and-dark-mode)).
- `MouseOverLabel` shows `alt_text` while the pointer is over it, or, with `reverse`, shows `alt_text` until
  the pointer is over it. On the Inventory tab it shows a campaign's end time and, on hover, its start time. An
  upcoming campaign shows its start time first.
- `LinkLabel` has the style `Link.TLabel` and opens `link` in the browser with `webopen` when it is clicked
  ([utils.md](utils.md#other-helpers)). With `style` set to an empty string it is a plain label that opens
  nothing, as the "Linked" status of a campaign on the Inventory tab is.
- `SelectCombobox` is a read-only `ttk.Combobox` as wide as its longest value, which calls `command` when a value
  is selected. The four drop-down lists of the Settings tab are one each.
- `Notebook` holds the `ttk.Notebook` of the four tabs. `GUIManager` keeps it as `tabs`.

## The Main tab panels

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

### Log records in the Output box

`GUIManager.__init__` adds a `_TKOutputHandler` with `OUTPUT_FORMATTER` to the `TwitchDrops` logger, so every log
record at the level set by `-v` also appears in the Output box. The handler writes a record of the event loop
thread at once. A record that another thread logs, such as a `DEBUG` record of the game scan thread at `-vvvv`,
waits in a `queue.SimpleQueue` of the handler. `GUIManager._poll` writes the queued records on each pass, and a
record of the event loop thread writes them before itself, so the lines keep the order of the log calls. A
queue, rather than `loop.call_soon_threadsafe` as the tray menu uses, needs no running event loop when the window
is built, and the tests build it without one.

## The Inventory and Help tabs

- **`InventoryOverview.add_campaign`** is a coroutine, because it awaits `ImageCache.get` for the campaign and
  reward images ([cache.md](cache.md)). `clear()`, which `Twitch.fetch_inventory` calls at each reload, removes
  the campaigns and calls `ImageCache.retry_failed`, so that each failed image download is tried once more
  ([cache.md](cache.md#failed-downloads)). The filters are "Not linked", "Upcoming", "Expired", "Excluded" and
  "Finished". Without "Excluded", the tab shows only a campaign whose game `State.GAMES_UPDATE` may mine: the game
  matches no Exclude entry and, under "Priority list only", it matches a Priority entry or is in `detected_games`.
  `refresh()` applies the filters again, and it runs each time the Inventory tab is opened. The campaigns are in
  a `ScrollArea` with both scroll bars always shown. The mouse wheel scrolls it, and Shift scrolls sideways
  ([scrollarea.md](scrollarea.md)).
- **`HelpTab`** "Invalidate" posts the access token to `https://id.twitch.tv/oauth2/revoke`, deletes
  `cookies.jar` when Twitch returns 200, and sets `State.RESTART`. The button stays disabled until a login
  completes.

## The tray icon

`TrayIcon` wraps a `pystray.Icon` named `twitch_miner`. `tray.py` imports pystray through `import_pystray`, which
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
  icon takes the stored state and the title of the drop on the Main tab. `restore()` stops the icon also before
  pystray has shown it, and `close_window` stops it as the app ends. A stop at any moment ends both of pystray's
  threads ([traybackend.md](traybackend.md)).
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

## The preview

`run_preview(manager)` builds the window from `manager`, the class `GUIManager` that `gui.py` passes, around a
mock `Twitch`, and runs it in a new event loop until the window closes.

- It builds a mock `Twitch` from `SimpleNamespace`: `settings` with each setting the GUI reads, `change_state`
  that prints the state number to the Output box, `state_change`, `request` set to `icon_request`, and `close`
  set to `GUIManager.stop`.
- Its settings have two Priority entries, one with `*`, one Exclude entry, two game folders and two detected
  games, one of them excluded. It fills the window with a login status, three games, the Games Being Mined
  table with `set_wanted_games`, four channels (offline, pending and two online, the pending one marked as
  watched), one active and linked campaign of a detected game with one drop, and two Output messages. It also
  calls `tray.notify`, which shows nothing, because no tray icon exists until `minimize()` runs.
- Over about 90 seconds it moves the drop display through a still display, a countdown, a cleared display, a
  drop one minute from the end and a finished drop. Closing the window ends the preview.
- `icon_request` returns the data of `icons/pickaxe.ico` for every request, so the campaign and reward images
  are the app icon, and the preview sends no request to Twitch or any other server. The campaign image shows
  the square icon stretched to 108 by 144 pixels. The preview never calls `GUIManager.save`, so it writes the
  icon to `cache/` but not `cache/mapping.json`, which maps each URL to its file.

A new setting that the GUI reads needs an entry in the mock `settings`, or the preview fails with an
`AttributeError` ([AGENTS.md](../../AGENTS.md#recipes)). `rostercheck.py` fails when the mock lacks a setting
that `gui.py` or a file of this package reads as an attribute of `settings` or `_settings`.

## Invariants

- The preview mock provides every setting the GUI reads and every `Twitch` attribute that building the window
  needs. It has no `detect_games`, `get_auth` or `_client_type`, so "Rescan", the ❌ folder button and a folder
  chosen with ➕ raise `AttributeError` in the preview.

**Dependencies.** Repo modules: `translate`, `cache`, `exceptions`, `gamelib`, `scrollarea`, `traybackend`,
`utils` and `constants`; `gui`, `channel`, `inventory` and `settings` for type checking only. Third-party:
`pystray`, Pillow and `yarl`.
