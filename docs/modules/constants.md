# `constants.py`

**Purpose.** Holds the values that the other modules share: the working directory and file paths, the intervals
and limits, the `State` and `PriorityMode` enums, the GQL operations, the Twitch client identities, the PubSub
topic names and the logging levels. It computes the paths once, at import, from how the app was started. It
reads the app version from [`version.py`](#versionpy). The module is 523 lines, over the 300 line soft cap in
AGENTS.md ([refinement task 005](../refinements/tasks/005-modules-over-the-line-cap.md)). `tests/test_constants.py`
tests it with plain values, and loads a second copy of it with a test `sys.argv[0]`, `APPIMAGE` and `sys.platform`
to check the paths.

## Public contract

### Working directory and paths

`WORKING_DIR` is the folder of `SELF_PATH`, and the app writes every file it keeps into it. `SELF_PATH` depends
on how the app runs:

| How the app runs | `SELF_PATH` | `WORKING_DIR` |
| --- | --- | --- |
| From source, `python main.py` | `main.py` | the repo folder |
| From source, `python gui.py`, or `pyinstaller build.spec` (which imports `constants`) | `main.py` next to `constants.py` | the repo folder |
| PyInstaller build on Windows or Linux | the executable | the executable's folder |
| macOS app bundle | the executable inside the bundle | `Contents/MacOS` inside the bundle |
| AppImage | the `.AppImage` file, read from the `APPIMAGE` environment variable | the folder of the `.AppImage` file |

`constants.py` has no branch for macOS: PyInstaller sets `sys.argv[0]` to the executable in `Contents/MacOS`.
`IS_APPIMAGE` is true when `APPIMAGE` names an existing path. `IS_PACKAGED` is true for a PyInstaller build
(`sys._MEIPASS` exists) or an AppImage.

Bundled read only files (`lang/`, `icons/`) are found by `_resource_path`, which `utils` exports as
`resource_path`. It returns a path under:

- the folder of `sys.argv[0]` in an AppImage, which is `usr/src` inside the mounted image, because
  `appimage/AppImageBuilder.yml` starts `usr/src/main.py`;
- `sys._MEIPASS` in a PyInstaller build, the temporary folder the one-file executable unpacks into;
- `WORKING_DIR` from source.

| Constant | Path under `WORKING_DIR` |
| --- | --- |
| `SETTINGS_PATH` | `settings.json` |
| `COOKIES_PATH` | `cookies.jar` |
| `LOCK_PATH` | `lock.file` |
| `LOG_PATH` | `log.txt` |
| `DUMP_PATH` | `dump.dat` |
| `CACHE_PATH`, `CACHE_DB` | `cache/` and `cache/mapping.json` ([cache.md](cache.md)) |
| `VENV_PATH`, `SITE_PACKAGES_PATH`, `SCRIPTS_PATH` | `env/` and its packages and scripts folders. `SYS_SITE_PACKAGES` and `SYS_SCRIPTS` hold the folder names for the platform. `build.spec` reads `SITE_PACKAGES_PATH`; autostart from source runs `pythonw` from `SCRIPTS_PATH` |

`LANG_PATH` is `_resource_path("lang")`. [troubleshooting.md](../troubleshooting.md#where-the-app-keeps-its-files)
says what each file holds.

### Intervals and limits

| Constant | Value | What it sets |
| --- | --- | --- |
| `PING_INTERVAL` | 3 minutes | Time between PING messages on each PubSub websocket ([websocket.md](websocket.md)) |
| `PING_TIMEOUT` | 10 seconds | How long a websocket waits for the PONG |
| `WS_MIN_UPTIME` | 60 seconds | How long a websocket connection stays open before its reconnect skips the backoff wait ([reconnect.md](reconnect.md)) |
| `ONLINE_DELAY` | 120 seconds | Wait after a stream-up event before `Channel` checks the stream again, because Twitch sends the event before the stream is live. [Task 002](../refinements/tasks/002-online-delay-single-try.md) covers the single check |
| `WATCH_INTERVAL` | 20 seconds | Time between the `Channel.send_watch` calls of `Twitch._watch_loop` |
| `REFRESH_JITTER` | 60 seconds | Largest random delay added to the `refresh_interval` setting in `_maintenance_task` ([ADR-0003](../adr/ADR-0003-stream-refresh.md)) |
| `RESTART_JITTER` | 60 seconds | Largest random delay added to each automatic restart ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)) |
| `MAX_EXTRA_MINUTES` | 15 | Minutes a drop may advance locally without a progress update from Twitch. At this count `TimedDrop.can_earn` returns false and the loop changes to `CHANNEL_SWITCH`, until a progress update or a reload resets the count |
| `MAX_WEBSOCKETS` | 8 | PubSub connections in the pool |
| `WS_TOPICS_LIMIT` | 50 | Topics on one connection |
| `BASE_TOPICS` | 2 | The user topics added at login, `Drops` and `Notifications` |
| `TOPICS_PER_CHANNEL` | 2 | The channel topics, `StreamState` and `StreamUpdate` |
| `MAX_TOPICS` | 398 | `MAX_WEBSOCKETS * WS_TOPICS_LIMIT - BASE_TOPICS` |
| `MAX_CHANNELS` | 199 | `MAX_TOPICS // TOPICS_PER_CHANNEL`. `CHANNELS_FETCH` sorts the channels by priority, ACL (a campaign's list of allowed channels) and viewer count, keeps the first 199 and drops the rest. [Task 001](../refinements/tasks/001-offline-acl-channels-trimmed-first.md) describes which ones are dropped first |
| `MAX_INT` | `sys.maxsize` | The rank of a game or channel that is not wanted, below every real rank |

### `State` and `PriorityMode`

`State` lists the states of the loop in `Twitch._run`. [twitch.md](twitch.md) and
[ARCHITECTURE.md](../ARCHITECTURE.md) describe the transitions.

| Member | What the loop does in it |
| --- | --- |
| `IDLE` | Waits for the next state change |
| `INVENTORY_FETCH` | The full reload: fetches the inventory and campaigns, runs game detection, saves ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)) |
| `GAMES_UPDATE` | Claims ready drops and builds `wanted_games` from the lists and the detected games |
| `CHANNELS_CLEANUP` | Removes the channels that are no longer needed |
| `CHANNELS_FETCH` | Collects the channels that can be watched |
| `CHANNEL_SWITCH` | Chooses the channel to watch |
| `RESTART` | Raises `ReloadRequest` |
| `EXIT` | Ends the loop |

`PriorityMode` is the `priority_mode` setting. Its default is `PRIORITY_ONLY`.

| Member | Value | Label | Effect in `GAMES_UPDATE` |
| --- | --- | --- | --- |
| `PRIORITY_ONLY` | 0 | Priority list only | Only games that match a Priority entry or are detected as installed are wanted |
| `ENDING_SOONEST` | 1 | Ending soonest | Games on no list are wanted too, ranked last. Within one rank, the campaign that ends first comes first |
| `LOW_AVBL_FIRST` | 2 | Low availability first | Games on no list are wanted too, ranked last. Within one rank, the lowest `availability` comes first |

### GQL operations

`GQLPersistedQuery(name, sha256, *, variables=None)` is a `dict` with `operationName`, the hash under
`extensions.persistedQuery.sha256Hash` (with `version` 1) and, when given, `variables`. The request contains the
hash and no query text. `with_variables(variables)` returns a deep copy with the given variables merged in; the
stored template does not change. In a template, `...` marks a variable that the caller must give. The merge
raises `RuntimeError` when a `...` is left unset in a dict the caller passes (`Unspecified variable: 'channel'`)
or when a dict meets a value that is not a dict. A `...` inside a dict the caller leaves out stays in the copy:
`ClaimDrop` with `{}` keeps `{"input": {"dropInstanceID": ...}}`, and `aiohttp` raises `TypeError` when it
encodes that body, before the request is sent.

`GQLQuery(query, g64data)` sends its query text, with gzip and base64 encoded data. Only `Stream.gql_payload` in
`channel.py` uses it, for the `sendSpadeEvents` watch mutation, and only `Channel._send_watch_gql` reads that
payload. Nothing calls that method ([channel.md](channel.md#watching)). `GQLOperation` is either type, and
`Twitch.gql_request` takes one operation or a list.

`GQL_QUERIES` maps the key the code uses to the operation Twitch knows. To update a hash, follow
[gql-operations.md](../runbooks/gql-operations.md).

| Key | `operationName` | Used in |
| --- | --- | --- |
| `GetStreamInfo` | `VideoPlayerStreamInfoOverlayChannel` | `channel.py` |
| `ClaimDrop` | `DropsPage_ClaimDropRewards` | `inventory.py` |
| `Inventory` | `Inventory` | `twitch.py` |
| `CurrentDrop` | `DropCurrentSessionContext` | `twitch.py` |
| `Campaigns` | `ViewerDropsDashboard` | `twitch.py` |
| `CampaignDetails` | `DropCampaignDetails` | `twitch.py` |
| `AvailableDrops` | `DropsHighlightService_AvailableDrops` | `channel.py`, `twitch.py` |
| `PlaybackAccessToken` | `PlaybackAccessToken` | `channel.py` |
| `GameDirectory` | `DirectoryPage_Game` | `twitch.py` |
| `NotificationsDelete` | `OnsiteNotifications_DeleteNotification` | `twitch.py` |
| `ClaimCommunityPoints`, `ChannelPointsContext`, `SlugRedirect`, `NotificationsView`, `NotificationsList` | | no caller ([task 022](../refinements/tasks/022-unused-code.md)) |

### Client identities

`ClientInfo(client_url, client_id, user_agents)` has the attributes `CLIENT_URL`, `CLIENT_ID` and `USER_AGENT`,
and iterates as that tuple. When `user_agents` is a list, `random.choice` picks one when the `ClientType` class
body runs at import, so one run uses one user agent from start to end.

| `ClientType` member | `CLIENT_URL` | User agents |
| --- | --- | --- |
| `WEB` | `https://www.twitch.tv` | one desktop Chrome |
| `MOBILE_WEB` | `https://m.twitch.tv` | a list of Android Chrome |
| `ANDROID_APP` | `https://www.twitch.tv` | a list of the Twitch Android app |
| `SMARTBOX` | `https://android.tv.twitch.tv` | one Android TV box |

`Twitch.__init__` sets `_client_type` to `ClientType.ANDROID_APP`. The `aiohttp` session sends its user agent
with every request, and `twitch.py` adds its client ID to the login and GQL requests.
[gql-operations.md](../runbooks/gql-operations.md) covers updating them.

### PubSub topics

`WEBSOCKET_TOPICS` maps a category (`"User"` or `"Channel"`) and a name to the Twitch topic.
`WebsocketTopic(category, topic_name, target_id, process)` is one subscription: `str()` gives
`<topic>.<target_id>`, such as `video-playback-by-id.123`, and calling it passes `(target_id, message)` to
`process`. It compares equal to another topic or a string with the same text, but its hash differs from the
string's, so a set lookup by the text misses it
([task 041](../refinements/tasks/041-topic-hash-differs-from-its-text.md)). `WebsocketTopic.as_str` builds that
text without an object. [websocket.md](websocket.md) describes the pool.

### Logging and strings

- `CALL` is a log level between `DEBUG` and `INFO` (`logging.INFO - 1`), named `CALL`.
- `LOGGING_LEVELS` maps the number of `-v` flags, 0 to 4, to `ERROR`, `WARNING`, `INFO`, `CALL` and `DEBUG`.
- `FILE_FORMATTER` formats `log.txt` (`main.py`). `OUTPUT_FORMATTER` formats the Output box (`gui.py`).
- `DEFAULT_LANG` is `"English"`. `WINDOW_TITLE` is `Twitch Drops Miner v` followed by the version.

### `version.py`

`version.py` holds only `__version__` (`"16.dev"`). `WINDOW_TITLE` and `main.py --version` show it. Each CI
build job appends `.` and the short commit hash to it before building (PowerShell `-Replace` on Windows, `sed`
on macOS and Linux) and does not commit the change. The AppImage job passes the same string to the builder as
`APP_VERSION`. [building.md](../building.md#release-builds) describes the CI builds.

## Invariants

- Importing the module has side effects: it computes the paths from `sys.argv[0]` and `APPIMAGE`, registers the
  `CALL` level and picks the user agents. Most modules and `build.spec` import it, so it imports no repo
  module except `version`, which keeps it free of import cycles.
- The CI test job installs only `requirements-dev.txt` and imports this module, so it imports no package outside
  that file and the standard library.
- `PriorityMode` is stored in `settings.json` by its value under the type name `PriorityMode`
  ([utils.md](utils.md)). After a rename of the class, the setting falls back to its default on the next load.
  After a stored value is removed from the enum, loading the settings raises `ValueError` and the app does not
  start.
- A new template variable that the caller must give is written as `...`, so a missing value raises before any
  request is sent.
- `MAX_CHANNELS` follows from the websocket limits: a change to `MAX_WEBSOCKETS` or `WS_TOPICS_LIMIT` changes how
  many channels the app tracks.

**Dependencies.** `version`, `yarl` and the standard library.
