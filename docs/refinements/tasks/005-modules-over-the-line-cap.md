# Eight modules are over the line cap

**Status:** open
**Area:** module layout
**Origin:** [AGENTS.md](../../../AGENTS.md#module-map)
**Verified:** 2026-10-20

AGENTS.md sets a limit of 300 lines per module, and `scripts/linecap.py` checks it. Eight modules are over it,
measured with `wc -l` on 2026-10-20, and linecap.py names them in `EXCEPTIONS`. An entry there fails once its
module is under the limit, so a split removes it. AGENTS.md forbids adding a new responsibility to any of them:
new work goes into a new module that they call. This task records where each one can be split. It does not ask
for the split now.

| Module | Lines |
| --- | --- |
| `gui.py` | 3218 |
| `twitch.py` | 1625 |
| `translate.py` | 590 |
| `constants.py` | 519 |
| `inventory.py` | 506 |
| `channel.py` | 505 |
| `utils.py` | 413 |
| `websocket.py` | 404 |

`main.py` (203), `cache.py` (147), `settings.py` (113), `registry.py` (112), `exceptions.py` (71) and every
module in `gamelib/` (at most 225) are under the cap.

## Split points

Line counts are of the class or block today.

- **`gui.py`**
  - The generic widgets `PlaceholderEntry`, `PlaceholderCombobox`, `PaddedListbox`, `MouseOverLabel`,
    `LinkLabel`, `SelectMenu` and `SelectCombobox`, about 330 lines together.
  - The Main tab panels: `StatusBar`, `WebsocketStatus`, `LoginForm`, `CampaignProgress` (163),
    `ConsoleOutput` and `ChannelList` (236).
  - `TrayIcon` (125), `InventoryOverview` (315) and `HelpTab` (103), one module each.
  - `SettingsPanel` (801), which is over the cap by itself. Its `__init__` is 378 lines and builds each frame:
    Games Being Mined, General, Advanced, Priority, Exclude, Detected Games and the Reload row. Each frame can
    become its own class.
  - `GUIManager` (495), of which `apply_theme` is 210 lines and can move to a theme module.
  - The mock under `if __name__ == "__main__":` (260). Moving it to its own preview script changes the
    `python gui.py` command that AGENTS.md and `docs/building.md` give.
- **`twitch.py`**
  - `_AuthState` (198): login, the OAuth flow, cookies and request headers.
  - HTTP and GQL requests: `get_session`, `request` and `gql_request`.
  - Inventory fetching: `fetch_campaigns`, `fetch_inventory` (122) and `_merge_data`.
  - The PubSub handlers: `process_stream_state`, `process_stream_update`, `on_channel_update`, `process_drops`
    and `process_notifications`.
  - Channel discovery: `get_live_streams` and `bulk_check_online`.
  - `Twitch._run` (320). The wanted games ranking in its `State.GAMES_UPDATE` branch and the channel order in
    its `State.CHANNELS_FETCH` branch need no I/O. As functions in their own module they can be tested
    ([003](003-test-suite.md)).
- **`translate.py`**: the `TypedDict` classes (about 265 lines), `default_translation` (248) and `Translator`.
- **`constants.py`**: `ClientInfo` and `ClientType`, the GQL classes with `GQL_QUERIES` (about 190 lines), and
  `WebsocketTopic` with `WEBSOCKET_TOPICS`.
- **`inventory.py`**: `Benefit`, `BaseDrop` (152) and `TimedDrop` (118) in one module, `DropsCampaign` (173)
  in another.
- **`channel.py`**: `Stream` (131) and `Channel` (332). `Channel` stays over the cap after that split.
- **`utils.py`**: four groups. The JSON helpers (`json_load`, `json_save`, `merge_json` and the private
  helpers they call), `ExponentialBackoff`, `Game`, and the task helpers such as `task_wrapper` and
  `first_to_complete`.
- **`websocket.py`**: `Websocket` (299) and `WebsocketPool` (69).

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
