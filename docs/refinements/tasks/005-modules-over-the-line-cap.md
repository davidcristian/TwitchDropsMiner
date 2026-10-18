# Eight modules are over the line cap

**Status:** open
**Area:** module layout
**Origin:** [AGENTS.md](../../../AGENTS.md#module-map)
**Verified:** 2026-10-18

AGENTS.md sets a soft cap of 300 lines per module. Eight modules are over it, measured with `wc -l` on
2026-10-18. AGENTS.md already forbids adding a new responsibility to any of them: new work goes into a new
module that they call. This task records where each one can be split. It does not ask for the split now.

| Module | Lines |
| --- | --- |
| `gui.py` | 3283 |
| `twitch.py` | 1849 |
| `translate.py` | 608 |
| `constants.py` | 523 |
| `inventory.py` | 510 |
| `channel.py` | 506 |
| `utils.py` | 458 |
| `websocket.py` | 404 |

`main.py` (208), `cache.py` (142), `settings.py` (113), `registry.py` (112), `exceptions.py` (94) and every
module in `gamelib/` (at most 207) are under the cap.

## Split points

Line counts are of the class or block today.

- **`gui.py`**
  - The generic widgets `PlaceholderEntry`, `PlaceholderCombobox`, `PaddedListbox`, `MouseOverLabel`,
    `LinkLabel`, `SelectMenu` and `SelectCombobox`, about 350 lines together.
  - The Main tab panels: `StatusBar`, `WebsocketStatus`, `LoginForm`, `CampaignProgress` (163),
    `ConsoleOutput` and `ChannelList` (236).
  - `TrayIcon` (125), `InventoryOverview` (315) and `HelpTab` (103), one module each.
  - `SettingsPanel` (801), which is over the cap by itself. Its `__init__` is 378 lines and builds each frame:
    Games Being Mined, General, Advanced, Priority, Exclude, Detected Games and the Reload row. Each frame can
    become its own class.
  - `GUIManager` (507), of which `apply_theme` is 210 lines and can move to a theme module.
  - The mock under `if __name__ == "__main__":` (260). Moving it to its own preview script changes the
    `python gui.py` command that AGENTS.md and `docs/building.md` give.
- **`twitch.py`**
  - `_AuthState` (351): login, the OAuth flow, cookies and request headers.
  - HTTP and GQL requests: `get_session`, `request` and `gql_request`.
  - Inventory fetching: `fetch_campaigns`, `fetch_inventory` (122) and `_merge_data`.
  - The PubSub handlers: `process_stream_state`, `process_stream_update`, `on_channel_update`, `process_drops`
    and `process_notifications`.
  - Channel discovery: `get_live_streams` and `bulk_check_online`.
  - `Twitch._run` (327). The wanted games ranking in its `State.GAMES_UPDATE` branch and the channel order in
    its `State.CHANNELS_FETCH` branch need no I/O. As functions in their own module they can be tested
    ([003](003-test-suite.md)).
- **`translate.py`**: the `TypedDict` classes (about 275 lines), `default_translation` (258) and `Translator`.
- **`constants.py`**: `ClientInfo` and `ClientType`, the GQL classes with `GQL_QUERIES` (about 190 lines), and
  `WebsocketTopic` with `WEBSOCKET_TOPICS`.
- **`inventory.py`**: `Benefit`, `BaseDrop` (158) and `TimedDrop` (118) in one module, `DropsCampaign` (173)
  in another.
- **`channel.py`**: `Stream` (131) and `Channel` (346). `Channel` stays over the cap after that split.
- **`utils.py`**: four groups. The JSON helpers (`json_load`, `json_save`, `merge_json` and the private
  helpers they call), `ExponentialBackoff` with `RateLimiter`, `Game`, and the task helpers such as
  `task_wrapper` and `first_to_complete`.
- **`websocket.py`**: `Websocket` (295) and `WebsocketPool` (69).

A split changes imports in other modules, and `gui.py` edits follow the AGENTS.md recipe for repeated lines. A
new package follows the "A new package" recipe, which adds the folder to `appimage/AppImageBuilder.yml`.
Splits cost no Twitch requests.

## History

- 2026-10-18: Opened. Found while the docs were written, from the soft cap in AGENTS.md. Line counts from
  `wc -l` and class sizes from the `ast` module.
