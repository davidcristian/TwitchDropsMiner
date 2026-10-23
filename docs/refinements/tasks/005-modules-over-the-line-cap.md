# Eight modules are over the line cap

**Status:** open
**Area:** module layout
**Origin:** [AGENTS.md](../../../AGENTS.md#module-map)
**Verified:** 2026-10-23

AGENTS.md sets a limit of 300 lines per module, and `scripts/linecap.py` checks it. Eight modules are over it,
measured with `wc -l` on 2026-10-23, and linecap.py names them in `EXCEPTIONS`. An entry there fails once its
module is under the limit, so a split removes it. AGENTS.md forbids adding a new responsibility to any of them:
new work goes into a new module that they call. This task records where each one can be split, and
[ADR-0020](../../adr/ADR-0020-module-splits.md) sets how a split is made.

| Module | Lines |
| --- | --- |
| `gui.py` | 3164 |
| `twitch.py` | 1734 |
| `translate.py` | 612 |
| `channel.py` | 528 |
| `inventory.py` | 489 |
| `constants.py` | 477 |
| `websocket.py` | 414 |
| `utils.py` | 371 |

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
