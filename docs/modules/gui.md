# `gui.py`

**Purpose.** The tkinter window: four tabs, the tray icon, the light and dark themes, and a preview that opens
the window with mock data. `Twitch.__init__` creates one `GUIManager`, and the rest of the app changes the
window only through that object and the parts it exposes as attributes. Every part is in the package `ui/`,
from which `gui.py` imports it ([ui.md](ui.md)), and so are the two mixins of `GUIManager`: `EventLoopMixin` in
`ui/eventloop.py` and `ThemeMixin` in `ui/theme.py`. `gui.py` keeps `GUIManager.__init__`, which builds the
window, the Windows message handler and the methods that pass a call on to a part, such as `display_drop`.
Before a search and replace edit in this file, read the `gui.py` recipe in [AGENTS.md](../../AGENTS.md#recipes).

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
| `login` | `LoginForm` | Main | The login status, the user ID, the "Login" button, the masked "Token:" entry with the "Use token" button, and the "Log in with browser" button, all enabled only while the login waits |
| `progress` | `CampaignProgress` | Main | Game, campaign and rewards of the current drop, two progress bars, a countdown |
| `output` | `ConsoleOutput` | Main | The Output box: a read-only `tk.Text` with a time stamp on each line |
| `channels` | `ChannelList` | Main | The channel table and the "Switch" button |
| `inv` | `InventoryOverview` | Inventory | One frame per campaign with its images and drops, and the Filter row |
| `settings` | `SettingsPanel` | Settings | The settings widgets, the lists and the "Reload" button |
| `help` | `HelpTab` | Help | About, links, help text and the "Invalidate" button |

Every class in the table is in `ui/`, with the generic widgets, such as `PlaceholderEntry` and
`PaddedListbox` ([ui.md](ui.md)), which also describes the Inventory, Settings and Help tabs.

## How the GUI runs with asyncio

The asyncio event loop and Tk run on one thread, so Tk callbacks and coroutines need no locks. The methods in
this section, except `wnd_proc`, are in `EventLoopMixin`.

- `GUIManager.start()` creates the `_poll` task in place of `Tk.mainloop()`. It calls `Tk.dooneevent` with
  `TKINTER_DONT_WAIT` (`1 << 1`) until no Tk event is left, writes the queued log records to the Output box
  ([ui.md](ui.md#log-records-in-the-output-box)), then sleeps 0.05 seconds. With that flag Tcl returns at once
  on an empty queue, which stops Tk from blocking inside an X11 or Wayland call during a large redraw.
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

## Public contract

Other modules use these names. Everything else in the file is internal to the GUI.

| Caller | What it uses |
| --- | --- |
| `twitch/` | `GUIManager(twitch)`; `start`, `close`, `close_requested`, `wait_until_closed`, `coro_unless_closed`, `prevent_close`, `print`, `save`, `set_games`, `clear_drop`; `status.update`; `tray.change_icon`; `channels.clear`, `clear_watching`, `set_watching`, `get_selection`, `set_selection`, `get_iids`; `inv.add_campaign`, `inv.clear`; `progress.minute_almost_done`, `progress.stop_timer`; `settings.set_wanted_games`, `set_detected`, `set_scanning`; `login.ask_login`, `login.ask_enter_code`, `login.update`; `help._invalidate_button` |
| `inventory/` | `display_drop`, `inv.update_drop`, `tray.notify` |
| `channel/` | `channels.display`, `channels.remove` |
| `websocket/` | `websockets.update`, `websockets.remove` |
| `cache.py` | `ImageCache(manager)` reads `manager._root` and `manager._twitch` |
| `main.py` | `close`, `close_requested`, `wait_until_closed`, `status.update`, `tray.change_icon`, `grab_attention`, `stop`, `close_window` |

The GUI calls back into `Twitch` through `settings`, `change_state`, `state_change`, `close`, `detect_games`,
`get_auth`, `request` and `_client_type`. `save()` saves the image cache; `Twitch.save` calls it together with
`Settings.save`. `grab_attention(sound=True)` restores the window from the tray, focuses it and rings the bell.

## The theme and dark mode

`apply_theme(dark)`, in `ThemeMixin`, runs at the end of `GUIManager.__init__` with the `dark_mode` setting,
and again from the "Dark mode" checkbox through `SettingsPanel.update_dark_mode`, so a change shows at once.

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
  minimum is 865 by 602 pixels in light mode and 878 by 636 in dark mode before the mock data arrives. On macOS
  it is measured once more after the window first shows, as the end of this section describes.
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
has room for 9 lines in light mode and 7 in dark mode.

On macOS, Tk reports a window whose size was set to `wm maxsize` while it was withdrawn as `zoomed`, and at its
first `<Map>` event the window leaves that state and becomes 20 pixels smaller on each axis
([task 072](../refinements/tasks/072-macos-window-smaller-than-wm-maxsize.md)). So when
`sizes_again_after_first_map` returns true for Tk's windowing system, which it does only for `aqua`, the first
`<Map>` event of the root calls `_measure_and_fit` through `after_idle`, and the binding is then removed.
`_measure_and_fit` calls `MinimumSize.measure` and then `_fit_to_screen`, so the fit uses the new minimum. In
runs on macOS in CI with Tk 8.6.12 and 9.0.4 the second fit gave the full size, and a fit inside the `<Map>`
handler, a size one pixel below `wm maxsize` or `wm state zoomed` did not. On X11 and Windows neither call runs
again. `_fit_to_screen` sets the geometry whenever the window requests more than `wm maxsize`, so there it could
replace a size that the window manager chose at the first show, and with the `tray` setting the first show is
the first restore from the tray.

On a macOS runner in CI with Python 3.14.9 and Tk 9.0.4, the measurement in `apply_theme` set a minimum of 914
by 606 pixels. Once `__init__` had returned, with the window still withdrawn, the same content requested 906 by
598, and a measurement at any later time set that size. The tab frames requested the same sizes as before, so
`MinimumSize.follow` did not measure again, and the minimum stayed 8 pixels larger on each axis than that size.
On an older runner image with Python 3.14.8 and Tk 9.0.4, on Python 3.10.11 with Tk 8.6.12, and on Linux, the
measurement in `apply_theme` already gave the final size. Which call in `__init__` changes the requested size
was not found. The most likely one is the geometry call of `_fit_to_screen`, when Tk on macOS creates the real
window.

## The preview

`python gui.py` runs the block under `if __name__ == "__main__":`, which calls `run_preview` in `ui/preview.py`
with `GUIManager` ([ui.md](ui.md#the-preview)). `constants.py` treats a run of `gui.py` like a run of `main.py`,
so the preview uses the repository folder as its working folder. To run the preview without a display, follow
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
- Widget text comes from `_()`, except the names and addresses that
  [translate.md](translate.md#text-that-stays-english) lists. Widgets read it when they are built, so a
  language change needs a restart. `SettingsPanel` reads its choice names in
  `cached_property` attributes so that no string is read before the language is set.
- `apply_theme` runs before the window is shown, because it defines the fonts and named styles the widgets use.
  A new plain Tk widget needs its own `configure_theme` call in `apply_theme`.

**Dependencies.** Repo modules: `translate`, `cache`, `colorfonts`, `scrollarea`, `utils`, `constants` and
`ui`; `twitch` and `inventory` for type checking only. Third-party: pywin32 (`win32api`, `win32con`, `win32gui`)
on Windows.
