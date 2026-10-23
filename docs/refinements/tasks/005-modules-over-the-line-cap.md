# Eight modules are over the line cap

**Status:** done 2026-10-23
**Area:** module layout
**Origin:** [AGENTS.md](../../../AGENTS.md#module-map)
**Verified:** 2026-10-23

AGENTS.md sets a limit of 300 lines per module, and `scripts/linecap.py` checks it. Eight modules were over it,
measured with `wc -l` on 2026-10-23, and linecap.py named those not yet split in `EXCEPTIONS`. An entry there
failed once its module was under the limit, so a split removed it. AGENTS.md forbade adding a new responsibility to any of them:
new work went into a new module that they call. This task records where each one was split, and
[ADR-0020](../../adr/ADR-0020-module-splits.md) sets how a split is made.

| Module | Lines | After the split |
| --- | --- | --- |
| `gui.py` | 3164 | 252, and `ui/`, nineteen files of 41 to 290 lines |
| `twitch.py` | 1734 | `twitch/`, ten files of 6 to 292 lines |
| `translate.py` | 612 | `translate/`, four files of 7 to 284 lines |
| `channel.py` | 528 | `channel/`, five files of 7 to 166 lines |
| `inventory.py` | 489 | `inventory/`, four files of 7 to 284 lines |
| `constants.py` | 477 | 139, and `twitchapi/`, four files of 16 to 183 lines |
| `websocket.py` | 414 | `websocket/`, four files of 7 to 252 lines |
| `utils.py` | 371 | `utils/`, seven files of 32 to 127 lines |

`main.py` (238), `cache.py` (186), `settings.py` (135), `registry.py` (112), `exceptions.py` (71) and every
module in `gamelib/` (at most 246) are under the cap.

## Split points

Line counts are of the class or block today.

- **`gui.py`**
  - The generic widgets `PlaceholderEntry`, `PlaceholderCombobox`, `PaddedListbox`, `MouseOverLabel`,
    `LinkLabel` and `SelectCombobox`, about 300 lines together.
  - The Main tab panels: `StatusBar`, `WebsocketStatus`, `LoginForm`, `CampaignProgress` (163),
    `ConsoleOutput` and `ChannelList` (239).
  - `TrayIcon` (128), `InventoryOverview` (288) and `HelpTab` (103), one module each.
  - `SettingsPanel` (725), which is over the cap by itself. Its `__init__` is 383 lines and builds each frame:
    Games Being Mined, General, Advanced, Priority, Exclude, Detected Games and the Reload row. Each frame can
    become its own class.
  - `GUIManager` (521), of which `apply_theme` is 213 lines and can move to a theme module.
  - The mock under `if __name__ == "__main__":` (273). Moving it to its own preview script changes the
    `python gui.py` command that AGENTS.md and `docs/building.md` give.
- **`twitch.py`**
  - `_AuthState` (200): login, the OAuth flow, cookies and request headers.
  - HTTP and GQL requests: `get_session`, `request` and `gql_request`.
  - Inventory fetching: `fetch_campaigns`, `fetch_inventory` (114) and `_merge_data`.
  - The PubSub handlers: `process_stream_state`, `process_stream_update`, `on_channel_update`, `process_drops`
    and `process_notifications`.
  - Channel discovery: `get_live_streams` and `bulk_check_online`.
  - `Twitch._run` (356). The wanted games ranking in its `State.GAMES_UPDATE` branch and the channel order in
    its `State.CHANNELS_FETCH` branch need no I/O. As functions in their own module they can be tested
    ([003](003-test-suite.md)).
- **`translate.py`**: the `TypedDict` classes (about 275 lines), `default_translation` (260) and `Translator`.
- **`constants.py`**: `ClientInfo` and `ClientType`, the GQL classes with `GQL_QUERIES` (about 165 lines), and
  `WebsocketTopic` with `WEBSOCKET_TOPICS`.
- **`inventory.py`**: `Benefit`, `BaseDrop` (135) and `TimedDrop` (120) in one module, `DropsCampaign` (172)
  in another.
- **`channel.py`**: `Stream` (140) and `Channel` (358). `Channel` stays over the cap after that split.
- **`utils.py`**: four groups. The JSON helpers (`json_load`, `json_save`, `merge_json` and the private
  helpers they call), `ExponentialBackoff`, `Game`, and the task helpers such as `task_wrapper` and
  `start_task`.
- **`websocket.py`**: `Websocket` (300) and `WebsocketPool` (71).

A split changes imports in other modules, and `gui.py` edits follow the AGENTS.md recipe for repeated lines. A
new package follows the "A new package" recipe, which adds the folder to `appimage/AppImageBuilder.yml`.
Splits cost no Twitch requests.

## History

- 2026-10-18: Opened. Found while the docs were written, from the soft cap in AGENTS.md. Line counts from
  `wc -l` and class sizes from the `ast` module.
- 2026-10-18: The limit became a check, `scripts/linecap.py`, with these eight modules as its exceptions. The
  line counts were measured again after the comments and docstrings over three lines were shortened.
- 2026-10-19: Measured again after the removal of the password login, which shortened `gui.py`, `twitch.py`,
  `translate.py`, `constants.py`, `main.py` and `exceptions.py`.
- 2026-10-20: Measured again after the websocket reconnect wait, which lengthened `websocket.py` and
  `constants.py`. The new module `reconnect.py` holds the logic of the wait.
- 2026-10-20: Measured the modules again after `RateLimiter` moved from `utils.py` to the new module
  `ratelimit.py`.
- 2026-10-20: Measured again after `lock_file` moved from `utils.py` to the new module `instancelock.py`, and
  `translate.py` gained the two strings of the "Cannot start" dialog.
- 2026-10-20: Measured `gui.py` again after the Inventory tab's wheel binding gained the X11 buttons. The logic
  went to the new module `mousewheel.py`.
- 2026-10-21: Measured the modules and the classes again after changes to `gui.py`, `twitch.py`, `utils.py`,
  `websocket.py`, `channel.py`, `inventory.py`, `translate.py` and `gamelib/`. The module docs now link here for
  the line counts instead of giving their own.
- 2026-10-21: Measured `gui.py` again after the game folder dialog moved to a child process. The logic went to
  the new module `folderpicker.py`.
- 2026-10-21: Measured `gui.py` again after the Settings tab started to scroll. The scrolling canvas of the
  Inventory tab moved to the new module `scrollarea.py`, which both tabs use.
- 2026-10-23: Measured `gui.py` and `SettingsPanel` again after the autostart entry moved to the new module
  `autostart.py`.
- 2026-10-23: Measured the generic widgets of `gui.py` again after `SelectMenu`, which nothing used, was
  removed. `first_to_complete` left `utils.py` for the same reason.
- 2026-10-23: Measured the modules and the classes again. The scheme for the splits became ADR-0020: a package
  of the same name for each module, except `constants.py` and `gui.py`, mixins for the classes over the limit,
  and commits that only move code.
- 2026-10-23: `utils.py` became the package `utils/`, and its entry left `EXCEPTIONS`.
- 2026-10-23: `websocket.py` became the package `websocket/`, and its entry left `EXCEPTIONS`. The message
  methods of `Websocket`, which had 300 lines by itself, moved to the mixin `MessagesMixin`.
- 2026-10-23: The client types, the GQL operations and the PubSub topics moved from `constants.py` to the new
  package `twitchapi/`, and the entry of `constants.py` left `EXCEPTIONS`. Five modules remain over the cap.
- 2026-10-23: `channel.py` became the package `channel/`, and its entry left `EXCEPTIONS`. `Channel`, which had
  358 lines by itself, keeps its attributes and properties in `tracked.py`. Its online checks moved to the mixin
  `OnlineMixin` and its watch requests to `WatchMixin`. Both set `__slots__ = ()`, so a `Channel` still has no
  `__dict__`. Four modules remain over the cap.
- 2026-10-23: `inventory.py` became the package `inventory/`, and its entry left `EXCEPTIONS`. `Benefit` and
  `BenefitType` have a file of their own, because with them and its imports the file of `BaseDrop` and
  `TimedDrop` had 308 lines. Three modules remain over the cap.
- 2026-10-23: `translate.py` became the package `translate/`, and its entry left `EXCEPTIONS`. The `TypedDict`
  classes, `default_translation` and `Translator` have a file each. With its imports, the file of
  `default_translation` has 269 lines, so the dict was not cut. `langcheck.py`, `dashcheck.py` and
  `prosecheck.py` read the English strings from `translate/english.py`. Two modules remain over the cap.
- 2026-10-23: `twitch.py`, then 1733 lines after the constants split shortened its imports, became the package
  `twitch/`. `_AuthState`, `save_cookies` and the mixin `SessionMixin` with `get_session`, `get_auth` and
  `wait_until_login` moved to `session.py`, `request` and `gql_request` to `RequestsMixin` in `requests.py`, and
  `fetch_campaigns` and `fetch_inventory` to `InventoryFetchMixin` in `inventoryfetch.py`. `get_session` went
  with `_AuthState`, because both read `COOKIES_PATH`, which the tests patch. `_merge_data` had already become
  `merge_data` in `gqldata.py`. `Twitch` stays in `client.py` with the PubSub handlers, the channel discovery
  and `_run`, and the entry in `EXCEPTIONS` is now `twitch/client.py`.
- 2026-10-23: `Twitch._run`, which had 356 lines, was cut into a method for each state from `INVENTORY_FETCH`
  to `CHANNEL_SWITCH`, such as `_run_games_update`, which returns the values that a later state reads. Each
  method holds its branch's lines unchanged. `_run` keeps 58 lines, and `client.py` now has 1226.
- 2026-10-23: The rest of `Twitch` left `client.py` for five mixins. `LifecycleMixin` in `lifecycle.py` holds
  `shutdown`, `_await_restart`, `_watch_loop` and `_maintenance_task`. `StatesMixin` in `states.py` holds `_run`
  and the methods of `INVENTORY_FETCH`, `GAMES_UPDATE` and `CHANNEL_SWITCH`, and `ChannelsMixin` in
  `channels.py` those of `CHANNELS_CLEANUP` and `CHANNELS_FETCH` with `_slot_order`. `DiscoveryMixin` in
  `discovery.py` holds `detect_games`, `get_live_streams` and `bulk_check_online`, and `PubSubMixin` in
  `pubsub.py` the PubSub handlers. `shutdown` and `_watch_loop` share a file because both read `time`, and
  `_await_restart` and `_maintenance_task` because both read `random`, which the tests patch. `client.py` has
  271 lines, and its entry left `EXCEPTIONS`. One module remains over the cap.
- 2026-10-23: The generic widgets left `gui.py` for the new package `ui/`: `PlaceholderEntry` and
  `PlaceholderCombobox` for `placeholder.py`, and `PaddedListbox`, `MouseOverLabel`, `LinkLabel`,
  `SelectCombobox` and `Notebook` for `widgets.py`. `gui.py` imports them from `ui` and has 2829 lines.
- 2026-10-23: The panels of the Main tab left `gui.py` for `ui/`: `StatusBar` and `WebsocketStatus` for
  `status.py`, `LoginForm` for `login.py`, `CampaignProgress` for `progress.py`, `ConsoleOutput` with
  `_TKOutputHandler` for `output.py`, and `ChannelList` for `channellist.py`. Their tests moved to
  `tests/test_ui_*.py`, and the login test patches `_` and `webopen` in `ui/login.py`. `gui.py` has 2175 lines.
- 2026-10-23: The preview's mock left the `__main__` block of `gui.py` for `run_preview` in `ui/preview.py`,
  which the block calls with `GUIManager`. Its lines keep their indentation as the body of the function, and its
  `global` statement became `nonlocal`. `rostercheck.py` now reads the mock there and the settings reads from
  `gui.py` and every file of `ui/`. `gui.py` has 1904 lines.
- 2026-10-23: `TrayIcon` left `gui.py` for `ui/tray.py` with the import of pystray, `HelpTab` for `helptab.py`,
  and `InventoryOverview` for `inventorytab.py`. With its imports that file would have had 318 lines, so
  `update_progress` and `update_drop` moved to the mixin `DropStatusMixin` in `dropstatus.py`. The tray tests
  patch `pystray` in `ui/tray.py`. `gui.py` has 1369 lines and keeps `SettingsPanel` and `GUIManager`.
- 2026-10-23: `SettingsPanel.__init__`, which had 383 lines, was cut into a method for each frame of the
  Settings tab, from `_build_wanted_frame` to `_build_reload_frame`, each with the frame's lines unchanged.
  `__init__` passes them `center_frame` and keeps 45 lines. `gui.py` has 1390 lines.
- 2026-10-23: `SettingsPanel` left `gui.py` for `ui/settingstab.py` with `_SettingsVars`, and its sections for
  three mixins: the General and Advanced sections with the autostart methods and `proxy_validate` for
  `GeneralSettingsMixin` in `generalsettings.py`, the Priority and Exclude lists for `GameListsMixin` in
  `gamelists.py`, and the Detected Games section for `DetectedGamesMixin` in `detectedgames.py`. The `window`
  fixture patches `autostart_entry` in `ui/settingstab.py`, and the tests of the language label patch `_` in
  `ui/generalsettings.py`. `gui.py` has 579 lines and keeps `GUIManager`.
- 2026-10-23: Done. `apply_theme` and `_set_title_bar_color` left `GUIManager` for the mixin `ThemeMixin` in
  `ui/theme.py`, and the methods that run Tk on the asyncio event loop and close the window, from `running` to
  `close_window`, for `EventLoopMixin` in `ui/eventloop.py`. `gui.py` has 252 lines with `GUIManager` and the
  preview entry, and its entry left `EXCEPTIONS`, which is now empty. Every module is under the cap.
