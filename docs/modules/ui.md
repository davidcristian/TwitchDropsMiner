# `ui/`

**Purpose.** The parts of the tkinter window that `gui.py` builds. `gui.py` stays a file, because
`python gui.py` opens the preview, and its classes move here
([ADR-0020](../adr/ADR-0020-module-splits.md)). The window as a whole, `GUIManager` and the classes that are
still in `gui.py` are in [gui.md](gui.md). Every file here needs a display, so the package is outside the
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

**Dependencies.** Repo modules: `translate`, `utils` (`webopen`) and `constants`; `gui`, `channel` and
`inventory` for type checking only. Third-party: `yarl`.
