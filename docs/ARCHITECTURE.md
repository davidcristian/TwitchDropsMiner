# Twitch Drops Miner architecture

This page describes the app's objects, the state machine that runs it, the path from login to a claimed drop,
its Twitch requests, its background tasks and its platform code. The rules are in [AGENTS.md](../AGENTS.md),
the decisions in [adr/](adr/README.md), and one page per module in [modules/](modules/).

## Components

The app is one Python process. `main.py` loads `Settings`, takes the lock on `lock.file` and runs `main()`
with `asyncio.run`, which creates `Twitch` and awaits `Twitch.run`. All code runs on that one event loop:

- **Tk runs without `mainloop`.** The `GUIManager._poll` task calls `Tk.dooneevent` with `DONT_WAIT` until no
  Tk event is left, then sleeps 0.05 seconds. GUI callbacks therefore run on the event loop and need no locks.
- **Two worker threads are the exception.** `TrayIcon` runs `pystray.Icon.run` with `loop.run_in_executor`, and
  its menu items pass their calls to the loop with `loop.call_soon_threadsafe`. `Twitch.detect_games` runs
  `gamelib.scan_directories` with `asyncio.to_thread`, because reading game folders blocks. At `-vvvv` the
  Output box's log handler runs on that thread for a DEBUG record of the scan. `_tkinter` raises `RuntimeError`
  instead of writing the record, which ends the scan
  ([task 021](refinements/tasks/021-scan-thread-logs-into-tk.md)).

```
main.py
├─ Settings             settings.json, with the command line flags read first
└─ Twitch               twitch.py: the state machine; creates everything below
   ├─ _AuthState        device ID, access token, user ID and the login flow
   ├─ ClientSession     the one aiohttp session; its cookie jar is saved to cookies.jar
   ├─ _qgl_limiter      the RateLimiter that every GQL request passes through
   ├─ GUIManager        gui.py: the Tk root, the four tabs, TrayIcon, ChannelList, SettingsPanel
   │  └─ ImageCache     cache.py: game and reward images in cache/
   ├─ WebsocketPool     websocket.py: up to 8 Websocket connections to Twitch PubSub
   ├─ inventory         DropsCampaign list; each campaign holds its TimedDrop objects and ACL channels
   ├─ _drops            every TimedDrop by ID, to match PubSub drop events
   ├─ _campaigns        every DropsCampaign by ID, for the AvailableDrops check
   ├─ channels          the tracked Channel objects by ID; each holds its current Stream or None
   └─ watching_channel  an AwaitableValue with the Channel being watched
```

A campaign's ACL lists the channels it allows (`allow.channels` in Twitch's data), which get `acl_based` set.
A campaign with an empty ACL progresses on any channel that streams its game with drops enabled. Nothing
clears `_campaigns`, not even `shutdown` ([task 027](refinements/tasks/027-campaigns-never-cleared.md)).

## The state machine

`Twitch._run` loops over `State` from `constants.py`: it handles the current state, then waits on the
`_state_change` event, which `change_state` sets with `_state`. A handler that ends with `change_state`
continues at once; `IDLE`, and `CHANNEL_SWITCH` when it watches a channel, clear the event and wait. `_state`
holds one value, so the next state a handler sets replaces any request made during its `await` calls
([task 012](refinements/tasks/012-button-requests-lost-during-a-fetch.md)). `EXIT` is never replaced. Before
the loop, `_run` starts the GUI poll task, logs in with `get_auth`, starts the websocket pool and `_watch_loop`,
subscribes the user's two PubSub topics and moves to `INVENTORY_FETCH`.

| State | What `_run` does | Next |
| --- | --- | --- |
| `INVENTORY_FETCH` | The full reload. Sets the tray icon to `maint`, runs `fetch_inventory` (which restarts `_maintenance_task`), fills the game choices of the Priority and Exclude lists, runs `detect_games`, and saves the settings and the image cache. | `GAMES_UPDATE` |
| `GAMES_UPDATE` | Claims each drop that `can_claim` in campaigns that are not upcoming. Rebuilds `wanted_games` from the Priority list, the detected games, the Exclude list and Priority mode, keeping games with a campaign that can progress within the next hour. Fills the Games Being Mined table and ends the watch loop's wait. | `CHANNELS_CLEANUP`, as a full cleanup |
| `CHANNELS_CLEANUP` | Removes every channel on a full cleanup or when `wanted_games` is empty. Otherwise removes the channels that are not ACL-based and are offline or stream a game outside `wanted_games`. Unsubscribes their topics. | `CHANNELS_FETCH`; `IDLE` when no game is wanted |
| `CHANNELS_FETCH` | Adds the untracked ACL channels of wanted campaigns, checked with `bulk_check_online`, and up to 20 live channels with drops enabled for each wanted game that has a campaign without an ACL (`get_live_streams`). Sorts by priority, ACL first, then viewers, keeps the first `MAX_CHANNELS` (199) and subscribes their topics. Offline channels sort last and are cut first ([task 001](refinements/tasks/001-offline-acl-channels-trimmed-first.md)). | `CHANNEL_SWITCH` |
| `CHANNEL_SWITCH` | Watches the channel selected in the channel list when `can_watch` accepts it, else the first channel by priority for which `should_switch` is true, else keeps the current channel. | waits; `IDLE` when nothing can be watched |
| `IDLE` | Sets the tray icon to `idle` and stops watching. With `--dump`, it and `CHANNEL_SWITCH` close the window instead, so the app exits after one full reload. | waits |
| `RESTART` | Raises `ReloadRequest`. `run` catches it, calls `shutdown` and starts `_run` again, which logs in again. | a new run |
| `EXIT` | Sets the status to exiting and returns from `_run`. | none |

| Event | Source | Moves to |
| --- | --- | --- |
| `Reload` button on the Settings tab | `SettingsPanel` | `INVENTORY_FETCH` |
| One hour after the last inventory fetch | `_maintenance_task` | `INVENTORY_FETCH` |
| A `drop-claim` event whose campaign cannot continue on the watched channel | `process_drops` | `INVENTORY_FETCH` |
| A drop or emote reward notification | `process_notifications` | `INVENTORY_FETCH` |
| The stream refresh, or the start or end of a campaign or drop | `_maintenance_task` | `CHANNELS_CLEANUP` |
| The list of detected games (installed games matched to a campaign) changes: after each inventory fetch, `Rescan`, or a game folder added or removed | `detect_games` | `GAMES_UPDATE` |
| The watched channel goes offline or can no longer be watched | `on_channel_update` | `CHANNEL_SWITCH` |
| A drop reaches `MAX_EXTRA_MINUTES` (15) estimated minutes | `DropsCampaign.bump_minutes` | `CHANNEL_SWITCH` |
| `Switch` button above the channel list | `ChannelList` | `CHANNEL_SWITCH` |
| `Invalidate` button on the Help tab | `HelpTab` | `RESTART` |
| Window closed, tray `Quit`, SIGINT or SIGTERM on Linux, Windows shutdown | `GUIManager.close` | `EXIT` |
| An exception in a task wrapped with `task_wrapper(critical=True)` | `utils.task_wrapper` | `EXIT` |

`on_channel_update` watches a channel that goes online and passes `should_switch` without a state change.
A change to the Priority list, Exclude list or Priority mode sets no state; the next `GAMES_UPDATE` reads it.

**Fatal errors.** An exception that leaves `_run` reaches `Twitch.run`. When "Restart after a crash after" is
Never (`restart_delay` 0), `run` raises it again, and `main.py` prints it and keeps the window open. Otherwise
`_await_restart` calls `shutdown` and waits ([ADR-0006](adr/ADR-0006-restart-after-fatal-error.md)), and `run`
starts `_run` again, which begins with a full reload
([task 019](refinements/tasks/019-restart-runs-a-full-reload.md)). A failed critical task moves to `EXIT`
instead and is not restarted ([task 013](refinements/tasks/013-crashed-task-ends-the-app.md)).

## Data flow

1. **Login.** `_AuthState._validate` takes the device ID from the `unique_id` cookie of `www.twitch.tv`.
   Without an `auth-token` cookie, `_oauth_login` runs the device code flow with the `ClientType.ANDROID_APP`
   client ID: after the user presses `Login`, it prints a code from `id.twitch.tv/oauth2/device`, opens the
   activation page and polls `id.twitch.tv/oauth2/token`. `id.twitch.tv/oauth2/validate` returns the user ID.
2. **Inventory.** `fetch_inventory` sends `Inventory` (campaigns in progress, rewards claimed), `Campaigns`
   (every campaign; it keeps `ACTIVE` and `UPCOMING`) and `CampaignDetails` for each campaign, 20 per request.
   It builds a `DropsCampaign` from each, and the Inventory tab loads their images through `ImageCache`.
3. **Games and channels.** `GAMES_UPDATE` orders the games: Priority list matches
   ([ADR-0005](adr/ADR-0005-list-patterns.md)), then installed games
   ([ADR-0004](adr/ADR-0004-installed-game-detection.md)), then the rest unless Priority mode is "Priority list
   only". `CHANNELS_FETCH` checks ACL channels with `GetStreamInfo`, 20 per request, plus `AvailableDrops` when
   "Enable extra available drops check" is on. It finds other channels with `GameDirectory`, and subscribes
   `video-playback-by-id` and `broadcast-settings-update` for each channel.
4. **Choosing.** `can_watch` returns true for an online channel that streams a game in `wanted_games` with
   drops enabled and has a campaign for which `DropsCampaign.can_earn` is true; a special game
   (`Game.is_special`) skips the game and drops checks. `should_switch` returns true for a channel that
   `can_watch` accepts when nothing is watched or the watched channel fails `can_watch`, or when its game has a
   higher priority, or an equal one and it has an ACL while the watched channel has none.
5. **Watching.** Every `WATCH_INTERVAL` (20 seconds), `_watch_loop` calls `Channel.send_watch`. For a new
   stream it sends one `PlaybackAccessToken` request and keeps the last URL of the quality list from
   `usher.ttvnw.net`, usually the lowest quality. Each call downloads that playlist and sends a `HEAD` request
   for each video segment URL in it, so no video is downloaded.
6. **Progress.** `drop-progress` events on the `user-drop-events` topic go to `TimedDrop.update_minutes`, and
   the progress panel counts each minute down. 15 seconds after a watch request, if that count has stopped or
   is at `ALMOST_DONE_SECONDS` (10) or less (`minute_almost_done`), `_watch_loop` sends `CurrentDrop`. With no
   usable response, `DropsCampaign.bump_minutes` adds an estimated minute.
7. **Stream changes.** `stream-up`, `broadcast-settings-update` or a viewer count for an offline channel calls
   `Channel.check_online`, which sends `GetStreamInfo` once, after `ONLINE_DELAY` (120 seconds)
   ([task 002](refinements/tasks/002-online-delay-single-try.md)). `stream-down` sets the channel offline at
   once. Both end in `on_channel_update`.
8. **Claiming.** A `drop-claim` event contains the drop instance ID, and `TimedDrop.claim` sends `ClaimDrop`.
   Then `process_drops` sends `CurrentDrop` until Twitch reports another drop, at most 8 times, and ends the
   watch loop's wait ([task 028](refinements/tasks/028-watch-restart-dropped.md)) when the campaign continues
   on the channel. Otherwise it moves to `INVENTORY_FETCH`, as the reward notification also does.

## Twitch traffic

Every request uses one `aiohttp.ClientSession` with at most 50 connections and the proxy from the Settings
tab. [ADR-0002](adr/ADR-0002-twitch-traffic-budget.md) sets the request budget.

| Kind | Sent by | Sent to | Limits and retries |
| --- | --- | --- | --- |
| GQL, Twitch's GraphQL API | `Twitch.gql_request`, with the operations and hashes in `GQL_QUERIES` ([runbook](runbooks/gql-operations.md)) | `https://gql.twitch.tv/gql` | `RateLimiter(capacity=5, window=1)`: at most 5 POSTs start in each 1-second window, which opens with the first POST after the last window ended, and at most 5 are open. A batch of operations is one POST. Retries with backoff up to 60 seconds. |
| HTTP | `Twitch.request` | `id.twitch.tv` (login, `Invalidate`), `www.twitch.tv`, `usher.ttvnw.net`, the stream playlist and its segment URLs, image URLs from campaign data (`ImageCache`) | No rate limit. Retries a 5xx status or a connection error with backoff up to 3 minutes. |
| PubSub | `Websocket` | `wss://pubsub-edge.twitch.tv/v1` | Up to `MAX_WEBSOCKETS` (8) connections with up to `WS_TOPICS_LIMIT` (50) topics each. `LISTEN` and `UNLISTEN` go in groups of 20 topics. A `PING` every `PING_INTERVAL` (3 minutes); a connection with no `PONG` within `PING_TIMEOUT` (10 seconds) reconnects. |

Nothing sends `ClaimCommunityPoints`, `ChannelPointsContext`, `SlugRedirect`, `NotificationsView` or
`NotificationsList`, which `GQL_QUERIES` in `constants.py` also defines
([task 022](refinements/tasks/022-unused-code.md)).

## Background tasks

| Task | Started by | Runs |
| --- | --- | --- |
| `GUIManager._poll` | `GUIManager.start`, at the start of `_run` | every 0.05 seconds |
| `Twitch._watch_loop` | `_run`, once per run | every `WATCH_INTERVAL` (20 seconds); the `CurrentDrop` check 15 seconds into a cycle |
| `Twitch._maintenance_task` | the end of each `fetch_inventory` | sleeps until the earliest of: `refresh_interval` minutes plus up to `REFRESH_JITTER` (60 seconds); the start or end of a campaign or drop that can progress within the hour; one hour after it started, when it moves to `INVENTORY_FETCH` and ends |
| `Websocket._handle`, one per connection | `WebsocketPool.start` and `WebsocketPool.add_topics` | each pass collects messages until 0.5 seconds pass with no message; a `PING` every 3 minutes; reconnects with backoff up to 3 minutes |
| `Channel._online_delay`, one per channel | `Channel.check_online` | once, `ONLINE_DELAY` (120 seconds) after the event |
| `CampaignProgress._timer_loop` | `CampaignProgress.start_timer` | once a second, for one minute |
| a PubSub topic handler | `Websocket._handle_message` | one task per message |

`refresh_interval` is "Check for new streams every": 0 (Never), 1, 2, 5, 10, 15 or 30 minutes, 5 by default
([ADR-0003](adr/ADR-0003-stream-refresh.md)). `_watch_loop`, `_maintenance_task` and `Websocket._handle` use
`task_wrapper(critical=True)`: an exception in one moves the app to `EXIT`. `Twitch.shutdown` stops all three.

## Platform differences

| Area | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Autostart | value `TwitchDropsMiner` in `HKCU/Software/Microsoft/Windows/CurrentVersion/Run`, through `registry.py` | `TwitchDropsMiner.desktop` in `~/.config/autostart`, or in `$XDG_CONFIG_HOME/autostart` when that folder exists | `~/Library/LaunchAgents/com.devilxd.twitchdropsminer.plist` with `RunAtLoad`; [ADR-0007](adr/ADR-0007-kept-identifiers.md) explains the name |
| Tray | pystray | pystray, which tries the AppIndicator backend first; `build.spec` bundles `libayatana-appindicator3.so.1` | none: `Minimize to Tray`, `--tray` and the two tray settings are hidden or ignored |
| Closing | a WndProc hook (pywin32) handles `WM_CLOSE` and `WM_QUERYENDSESSION`, so a Windows shutdown closes the app | `WM_DELETE_WINDOW`; SIGINT and SIGTERM call `GUIManager.close` | `WM_DELETE_WINDOW` |
| Dark mode | the `clam` ttk theme and the title bar color through DWM | the `clam` ttk theme | `NSAppearance` through AppKit |
| Lock file | `msvcrt.locking` | `fcntl.lockf` | `fcntl.lockf` |
| App files | the folder of the executable | the folder of the `.AppImage` file or the executable | `Contents/MacOS` inside the `.app` |
| Other | | `main.py` sets `XMODIFIERS=@im=none` when it is unset; `webopen` restores `LD_LIBRARY_PATH` in a packaged build before it opens a browser | the notebook tab and checkbutton style changes are skipped |

The autostart entry runs `SELF_PATH` with the current `-v` flags, plus `--tray` for "Autostart into tray". From
source it runs `main.py` with the `pythonw` in `env/`, which only a Windows virtual environment has. On Linux the
autostart folder must already exist ([task 015](refinements/tasks/015-autostart-on-linux-and-macos.md)).

The [app files](troubleshooting.md#where-the-app-keeps-its-files) go in `WORKING_DIR`, the folder of
`SELF_PATH` in `constants.py`; from source, `SELF_PATH` is `main.py`. `IS_PACKAGED` is set in a PyInstaller
build and, with `IS_APPIMAGE`, in an AppImage; a packaged build reads `icons/` and `lang/` from its bundle.

## Repo map

The Python modules are in the [module map](../AGENTS.md#module-map). The other files, then the gitignored ones:

```
lang/                  one translation file per language, named after the language; CI checks the JSON
icons/                 pickaxe.ico (window and tray) and active, idle, error, maint: the tray icon states
appimage/              AppImageBuilder.yml, the AppImage recipe, and pickaxe.png, its icon
.github/workflows/     ci.yml: the Validate job, the four builds and the dev-build pre-release
.vscode/               launch.json debug configurations and tasks.json build tasks
build.spec             PyInstaller spec: one-file build, icons, translations, Linux tray library, macOS .app
setup_env.sh, .bat     create env/ and install requirements.txt into it
build.sh, build.bat    install PyInstaller into env/ and run build.spec
run_dev.bat            starts main.py from env/ on Windows, with or without a console
pack.bat               zips dist\*.exe and manual.txt into "Twitch Drops Miner.zip" with 7z.exe
manual.txt             command line flags and exit codes; every release build includes it
requirements.txt       aiohttp, Pillow, pystray, PyGObject (Linux), pywin32 (Windows), truststore
version.py             __version__; CI appends the short commit hash
LICENSE, LICENSE.MIT   GNU AGPL v3 for the project; MIT for the code from DevilXD/TwitchDropsMiner
README.md, AGENTS.md   the user guide; the engineering rules, which CLAUDE.md includes
docs/                  index.md, ARCHITECTURE.md, building.md, troubleshooting.md
docs/adr/, modules/    decision records (format in adr/README.md); one contract page per Python module
docs/runbooks/         step by step procedures
docs/refinements/      the backlog: index.md and one file per task in tasks/

settings.json          the settings
cookies.jar            the login session (the rule is /*.jar)
lock.file              the single instance lock
log.txt, dump.dat      written with --log and --dump
cache/                 ImageCache images and mapping.json
lang/English.json      rewritten from default_translation on every run from source
*.new                  the file json_save writes before it replaces the target
env/                   the virtual environment from setup_env
build/, dist/          PyInstaller output; *.exe, *.zip, *.tmp, *.app and "Twitch Drops Miner/" too
AppDir/, *.AppImage    AppImage output; appimage-build/, appimage-builder/ and *.AppImage.zsync too
__pycache__, .mypy_cache, .DS_Store
```
