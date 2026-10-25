# Twitch Drops Miner architecture

This page describes the app's objects, the state machine that runs it, the path from login to a claimed drop,
its Twitch requests, its background tasks and its platform code. The rules are in [AGENTS.md](../AGENTS.md),
the decisions in [adr/](adr/README.md), and one page per module in [modules/](modules/).

## Components

The app is one Python process, except for the game folder dialog, which runs in a child process while it is
open ([folderpicker.md](modules/folderpicker.md)). `main.py` loads `Settings`, takes the lock on `lock.file`
and runs `main()` with `asyncio.run`, which creates `Twitch` and awaits `Twitch.run`. All code runs on that one
event loop:

- **Tk runs without `mainloop`.** The `GUIManager._poll` task calls `Tk.dooneevent` with `DONT_WAIT` until no
  Tk event is left, then sleeps 0.05 seconds. GUI callbacks therefore run on the event loop and need no locks.
- **Two worker threads are the exception.** `TrayIcon` runs `pystray.Icon.run` with `loop.run_in_executor`, and
  its menu items pass their calls to the loop with `loop.call_soon_threadsafe`. `Twitch.detect_games` runs
  `gamelib.scan_directories` with `asyncio.to_thread`, because reading game folders blocks. A log record of
  either thread waits in a queue until the event loop thread writes it to the Output box
  ([ui.md](modules/ui.md#log-records-in-the-output-box)).

```
main.py
├─ Settings             settings.json, with the command line flags read first
└─ Twitch               twitch/: the state machine; creates everything below
   ├─ _AuthState        device ID, access token, user ID and the login flow
   ├─ ClientSession     the one aiohttp session; its cookie jar is saved to cookies.jar
   ├─ _qgl_limiter      the RateLimiter that every GQL request passes through
   ├─ _restart_delay    the RestartDelay that sets the wait before each restart after a fatal error
   ├─ GUIManager        gui.py: the Tk root; ui/: the tabs, TrayIcon, ChannelList
   │  └─ ImageCache     cache.py: game and reward images in cache/
   ├─ WebsocketPool     websocket/: up to 8 Websocket connections to Twitch PubSub
   ├─ inventory         DropsCampaign list; each campaign holds its TimedDrop objects and ACL channels
   ├─ _drops            every TimedDrop by ID, to match PubSub drop events
   ├─ _campaigns        every DropsCampaign of the latest reload by ID, for the AvailableDrops check
   ├─ channels          the tracked Channel objects by ID; each holds its current Stream or None
   └─ watching_channel  an AwaitableValue with the Channel being watched
```

A campaign's ACL lists the channels it allows (`allow.channels` in Twitch's data), which get `acl_based` set.
A campaign with an empty ACL progresses on any channel that streams its game with drops enabled. Each reload
replaces the entries of `_drops` and `_campaigns`, and `shutdown` clears both.

## The state machine

`Twitch._run` loops over `State` from `constants.py`: it clears the `_state_change` event, handles the current
state, then waits on the event, which `change_state` sets with `_state`. It handles each state from
`INVENTORY_FETCH` to `CHANNEL_SWITCH` in a method named for that state, such as `_run_games_update`, which
returns the values that a later state reads. A handler that ends with `change_state` continues at once; `IDLE`,
and `CHANNEL_SWITCH` when it watches a channel, wait. Of the states
requested during a pass, the handler's own next state included, the first in `STATE_ORDER` runs next: `EXIT`,
`RESTART`, then the states of a reload from `INVENTORY_FETCH` to `CHANNEL_SWITCH`, then `IDLE`. So a reload
also runs a later state that a request names, and a reload requested during `INVENTORY_FETCH` is merged into
it ([ADR-0017](adr/ADR-0017-state-requests.md)). `EXIT` is never replaced. Before
the loop, `_run` starts the GUI poll task, logs in with `get_auth`, starts the websocket pool without waiting for
a connection, starts `_watch_loop`, subscribes the user's two PubSub topics and moves to `INVENTORY_FETCH`.

| State | What `_run` does | Next |
| --- | --- | --- |
| `INVENTORY_FETCH` | The full reload. Sets the tray icon to `maint`, runs `fetch_inventory` (which restarts `_maintenance_task`), fills the game choices of the Priority and Exclude lists, runs `detect_games`, and saves the settings and the image cache. | `GAMES_UPDATE` |
| `GAMES_UPDATE` | Claims each drop that `can_claim` in campaigns that are not upcoming. Rebuilds `wanted_games` from the Priority list, the detected games, the Exclude list and Priority mode, keeping games with a campaign that can progress within the next hour. Fills the Games Being Mined table and ends the watch loop's wait. | `CHANNELS_CLEANUP`, as a full cleanup |
| `CHANNELS_CLEANUP` | Removes every channel on a full cleanup or when `wanted_games` is empty. Otherwise removes the channels that are not ACL-based and are offline or stream a game outside `wanted_games`. Unsubscribes their topics. | `CHANNELS_FETCH`; `IDLE` when no game is wanted |
| `CHANNELS_FETCH` | Adds the untracked ACL channels of wanted campaigns, checked with `bulk_check_online`, and up to 20 live channels with drops enabled for each wanted game that has a campaign without an ACL (`get_live_streams`). Sorts by priority, ACL first, then viewers, keeps `MAX_CHANNELS` (199) and subscribes their topics: first the channels that `CHANNEL_SWITCH` can watch next, then the others by the priority of their game, where an offline ACL channel takes that of its campaign ([ADR-0018](adr/ADR-0018-channel-slots.md)). The old channels stay in `channels` until the requests end ([twitch.md](modules/twitch.md#invariants)). When no channel is watched or `GAMES_UPDATE` came before, shows the active drop one minute lower with its countdown stopped; a refresh that keeps the watched channel leaves the countdown running. Selects again a channel that was selected when the cleanup removed it ([ADR-0017](adr/ADR-0017-state-requests.md)). | `CHANNEL_SWITCH` |
| `CHANNEL_SWITCH` | Watches the channel selected in the channel list when `can_watch` accepts it, else the first channel by priority for which `should_switch` is true, else keeps the current channel. After a stop of the watched channel, or a change of its game to one of a lower priority (`_watched_stopped`), when the last `CHANNELS_FETCH` left off the list a channel that `can_watch` accepted with a higher priority than this choice (`_cut_priority`), or any such channel when there is no choice, it stops watching and moves to `CHANNELS_CLEANUP` instead, a stream refresh. A selected channel that `can_watch` accepts is watched without it, and `refresh_interval` at 0 turns it off ([ADR-0018](adr/ADR-0018-channel-slots.md)). | waits; `IDLE` when nothing can be watched; `CHANNELS_CLEANUP` for that refresh |
| `IDLE` | Sets the tray icon to `idle` and stops watching. With `--dump`, it and `CHANNEL_SWITCH` close the window instead, so the app exits after one full reload. | waits |
| `RESTART` | Raises `ReloadRequest`. `run` catches it, calls `shutdown` and starts `_run` again, which logs in again. After a critical task failed, raises that task's error instead, which `run` handles as a fatal error. | a new run |
| `EXIT` | Sets the status to exiting and returns from `_run`. | none |

| Event | Source | Moves to |
| --- | --- | --- |
| `Reload` button on the Settings tab | `SettingsPanel` | `INVENTORY_FETCH` |
| One hour after the last inventory fetch | `_maintenance_task` | `INVENTORY_FETCH` |
| A `drop-claim` event whose campaign cannot continue on the watched channel | `process_drops` | `INVENTORY_FETCH` |
| A drop or emote reward notification | `process_notifications` | `INVENTORY_FETCH` |
| The stream refresh, or the start or end of a campaign or drop | `_maintenance_task` | `CHANNELS_CLEANUP` |
| The list of detected games (installed games matched to a campaign) changes: after each inventory fetch, `Rescan`, or a game folder added or removed | `detect_games` | `GAMES_UPDATE` |
| The watched channel goes offline, can no longer be watched, or changes to a game of a lower priority | `on_channel_update` | `CHANNEL_SWITCH` |
| The watched channel stopped or changed to a game of a lower priority, and the last `CHANNELS_FETCH` left off the list a better channel than the switch can watch | `_run_channel_switch` | `CHANNELS_CLEANUP` |
| A drop reaches `MAX_EXTRA_MINUTES` (15) estimated minutes | `DropsCampaign.bump_minutes` | `CHANNEL_SWITCH` |
| `Switch` button above the channel list | `ChannelList` | `CHANNEL_SWITCH` |
| `Invalidate` button on the Help tab | `HelpTab` | `RESTART` |
| Window closed, tray `Quit`, SIGINT or SIGTERM on Linux, Windows shutdown | `GUIManager.close` | `EXIT` |
| An exception in a task wrapped with `task_wrapper(critical=True)` | `utils.task_wrapper`, through `Twitch.task_failed` | `RESTART` |

`on_channel_update` watches a channel that goes online and passes `should_switch` without a state change.
A change to the Priority list, Exclude list or Priority mode sets no state; the next `GAMES_UPDATE` reads it.

**Fatal errors.** An exception that leaves `_run` reaches `Twitch.run`. When "Restart after a crash after" is
Never (`restart_delay` 0), `run` raises it again, and `main.py` prints it and keeps the window open. Otherwise
`_await_restart` calls `shutdown` and waits ([ADR-0006](adr/ADR-0006-restart-after-fatal-error.md)), and `run`
starts `_run` again, which begins with a full reload. The wait is `restart_delay` after the first error, and it
doubles after each run that ends within an hour, up to 60 minutes ([restartdelay.md](modules/restartdelay.md)).
So an error that ends every run reloads at most once an hour after its first hour. The error of a failed
critical task takes the same path: `RESTART` raises it from `_run`. A `Reload` press ends the wait at once, and
the wait after the next error is `restart_delay` again.

## Data flow

1. **Login.** `_AuthState._validate` takes the device ID from the `unique_id` cookie of `www.twitch.tv`.
   Without an `auth-token` cookie, `_oauth_login` runs the device code flow with the `ClientType.ANDROID_APP`
   client ID: at each press of `Login`, it requests a code from `id.twitch.tv/oauth2/device`, prints it, opens
   the activation page and polls `id.twitch.tv/oauth2/token`. `id.twitch.tv/oauth2/validate` returns the user ID.
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
   (`Game.is_special`) in `wanted_games` skips the game and drops checks. `should_switch` returns true for a
   channel that `can_watch` accepts when nothing is watched or the watched channel fails `can_watch`, or when
   its game has a higher priority, or an equal one and it has an ACL while the watched channel has none.
5. **Watching.** Every `WATCH_INTERVAL` (20 seconds), `_watch_loop` calls `Channel.send_watch`. For a new
   stream it sends one `PlaybackAccessToken` request and keeps the last URL of the quality list from
   `usher.ttvnw.net`, usually the lowest quality. Each call downloads that playlist and sends a `HEAD` request
   for each video segment URL in it, so no video is downloaded.
6. **Progress.** `drop-progress` events on the `user-drop-events` topic go to `TimedDrop.update_minutes`, and
   the progress panel counts each minute down. 15 seconds after a watch request, if that count has stopped or
   is at `ALMOST_DONE_SECONDS` (10) or less (`minute_almost_done`), `_watch_loop` sends `CurrentDrop`. With no
   usable response, `DropsCampaign.bump_minutes` adds an estimated minute.
7. **Stream changes.** `stream-up`, `broadcast-settings-update` or a viewer count for an offline channel calls
   `Channel.check_online`, which sends `GetStreamInfo` after `ONLINE_DELAY` (120 seconds), and up to twice more,
   120 seconds apart, while an offline channel has no stream
   ([channel.md](modules/channel.md#after-a-stream-up-event)). `stream-down` sets the channel offline at once.
   Both end in `on_channel_update`. A playlist request that returns a status of 400 or above, which it does once
   the stream has ended, also calls `check_online` and makes the next cycle request usher again, in case
   `stream-down` was missed ([channel.md](modules/channel.md#a-failed-playlist-request)).
8. **Claiming.** A `drop-claim` event contains the drop instance ID, and `TimedDrop.claim` sends `ClaimDrop`.
   Then `process_drops` sends `CurrentDrop` until Twitch reports another drop, at most 8 times, and ends the
   current watch cycle after its `CurrentDrop` check ([twitch.md](modules/twitch.md#watch-loop)) when the
   campaign continues on the channel. Otherwise it moves to `INVENTORY_FETCH`, as the reward notification
   also does. An event for a drop that is already claimed does nothing.

## Twitch traffic

Every request uses one `aiohttp.ClientSession` with at most 50 connections and the proxy from the Settings
tab. [ADR-0002](adr/ADR-0002-twitch-traffic-budget.md) sets the request budget.

| Kind | Sent by | Sent to | Limits and retries |
| --- | --- | --- | --- |
| GQL, Twitch's GraphQL API | `Twitch.gql_request`, with the operations and hashes in `GQL_QUERIES` ([runbook](runbooks/gql-operations.md)) | `https://gql.twitch.tv/gql` | `RateLimiter(capacity=5, window=1)`: at most 5 POSTs start in any span of 1 second, and at most 5 are open. A batch of operations is one POST. Retries with backoff up to 60 seconds. |
| HTTP | `Twitch.request` | `id.twitch.tv` (login, `Invalidate`), `www.twitch.tv`, `usher.ttvnw.net`, the stream playlist and its segment URLs, image URLs from campaign data (`ImageCache`) | No rate limit. Retries a 5xx status or a connection error with backoff up to 3 minutes. |
| PubSub | `Websocket` | `wss://pubsub-edge.twitch.tv/v1` | Up to `MAX_WEBSOCKETS` (8) connections with up to `WS_TOPICS_LIMIT` (50) topics each. `LISTEN` and `UNLISTEN` go in groups of 20 topics. A `PING` every `PING_INTERVAL` (3 minutes); a connection with no `PONG` within `PING_TIMEOUT` (10 seconds) reconnects. |

## Background tasks

| Task | Started by | Runs |
| --- | --- | --- |
| `GUIManager._poll` | `GUIManager.start`, at the start of `_run` | every 0.05 seconds |
| `Twitch._watch_loop` | `_run`, once per run | every `WATCH_INTERVAL` (20 seconds); the `CurrentDrop` check 15 seconds into a cycle; `restart_watching` ends a cycle after that check |
| `Twitch._maintenance_task` | the end of each `fetch_inventory` | sleeps until the earliest of: `refresh_interval` minutes plus up to `REFRESH_JITTER` (60 seconds); the start or end of a campaign or drop that can progress within the hour; one hour after it started, when it moves to `INVENTORY_FETCH` and ends |
| `Websocket._handle`, one per connection | `WebsocketPool.start` and `WebsocketPool.add_topics` | each pass collects messages until 0.5 seconds pass with no message; a `PING` every 3 minutes; reconnects at once after a connection that stayed open `WS_MIN_UPTIME` (60 seconds), and otherwise after a backoff delay of up to 3 minutes |
| `Channel._online_delay`, one per channel | `Channel.check_online` | `ONLINE_DELAY` (120 seconds) after the event, and for an offline channel without a stream up to twice more, 120 seconds apart |
| `CampaignProgress._timer_loop` | `CampaignProgress.start_timer` | once a second, for one minute |
| a PubSub topic handler | `Websocket._handle_message` | one task per message |

`refresh_interval` is "Check for new streams every": 0 (Never), 1, 2, 5, 10, 15 or 30 minutes, 5 by default
([ADR-0003](adr/ADR-0003-stream-refresh.md)). `_watch_loop`, `_maintenance_task` and `Websocket._handle` use
`task_wrapper(critical=True)`: an exception in one ends the run as a fatal error. `Twitch.shutdown` stops all
three.

## Platform differences

| Area | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Autostart ([autostart.md](modules/autostart.md)) | value `TwitchDropsMiner` in `HKCU/Software/Microsoft/Windows/CurrentVersion/Run`, through `registry.py` | `TwitchDropsMiner.desktop` in `$XDG_CONFIG_HOME/autostart`, or in `~/.config/autostart` when that variable is not an absolute path; the app creates the folder | `~/Library/LaunchAgents/com.devilxd.twitchdropsminer.plist` with `RunAtLoad`; [ADR-0007](adr/ADR-0007-kept-identifiers.md) explains the name |
| Tray | pystray | pystray, whose AppIndicator, GTK and X11 backends `traybackend.py` tries in turn, X11 alone without a DBus session bus; `build.spec` bundles `libayatana-appindicator3.so.1` | none: `Minimize to Tray`, `--tray` and the two tray settings are hidden or ignored |
| Closing | a WndProc hook (pywin32) handles `WM_CLOSE` and `WM_QUERYENDSESSION`, so a Windows shutdown closes the app | `WM_DELETE_WINDOW`; SIGINT and SIGTERM call `GUIManager.close`, and in an AppImage without FUSE the end of its runtime sends that SIGTERM (`parentexit.py`) | `WM_DELETE_WINDOW` |
| Dark mode | the `clam` ttk theme and the title bar color through DWM | the `clam` ttk theme | `NSAppearance` through AppKit |
| Lock file | `msvcrt.locking` | `fcntl.lockf` | `fcntl.lockf` |
| Launcher indexes for game detection ([gamelib.md](modules/gamelib.md#launcher-indexes)) | the Epic launcher folder in `%PROGRAMDATA%`, Heroic's in `%APPDATA%` | Heroic's folder in `$XDG_CONFIG_HOME` and in its Flatpak folder | the Epic launcher and Heroic folders in `~/Library/Application Support` |
| Mouse wheel in the Inventory and Settings tabs | `<MouseWheel>` | `<MouseWheel>`, and with Tk 8.6 on X11 also `<Button-4>` and `<Button-5>`, through `mousewheel.py` | `<MouseWheel>` |
| App files | the folder of the executable | the folder of the `.AppImage` file or the executable | `Contents/MacOS` inside the `.app` |
| Other | | `main.py` sets `XMODIFIERS=@im=none` when it is unset; `webopen` restores `LD_LIBRARY_PATH` in a packaged build before it opens a browser | the notebook tab and checkbutton style changes are skipped |

The autostart entry runs `SELF_PATH` with the current `-v` flags, plus `--tray` for "Autostart into tray". From
source it runs `main.py` with the Python in `env/`: `pythonw` on Windows, which opens no console window, and
`python` on Linux and macOS, whose virtual environments have no `pythonw`.

The [app files](troubleshooting.md#where-the-app-keeps-its-files) go in `WORKING_DIR`, the folder of
`SELF_PATH` in `constants.py`; from source, `SELF_PATH` is `main.py`. `IS_PACKAGED` is set in a PyInstaller
build and, with `IS_APPIMAGE`, in an AppImage; a packaged build reads `icons/` and `lang/` from its bundle.

## Repo map

The Python modules are in the [module map](../AGENTS.md#module-map). The other files, then the gitignored ones:

```
lang/                  one translation file per language, named after the language, checked by langcheck.py
icons/                 pickaxe.ico (window and tray) and active, idle, error, maint: the tray icon states
appimage/              AppImageBuilder.yml, the AppImage recipe, and pickaxe.png, its icon
.github/workflows/     ci.yml: the Validate job (just check), the four builds and the dev-build pre-release
.github/dependabot.yml  weekly updates of the action SHAs in ci.yml, monthly ones of the Python packages
.vscode/               launch.json debug configurations and tasks.json build tasks
build.spec             PyInstaller spec: one-file build, icons, translations, Linux tray library, macOS .app
setup_env.sh, .bat     create env/ and install requirements.txt into it
build.sh, build.bat    install PyInstaller into env/ and run build.spec
run_dev.bat            starts main.py from env/ on Windows, with or without a console
pack.bat               zips dist\*.exe, manual.txt and the license files into "Twitch Drops Miner.zip" with 7z.exe
manual.txt             command line flags and exit codes; every release build includes it
requirements.txt       aiohttp, Pillow, pystray, PyGObject (Linux), pywin32 (Windows), truststore
requirements-dev.txt   the tools of just check, and the app's packages that the tests import; no build installs it
constraints.txt        the exact version of every package that a build, setup_env or the Validate job installs
justfile               the recipes of just check, one per check
pyproject.toml         the ruff, pytest and coverage settings; the app is not a package
.pre-commit-config.yaml  the git hooks: just check before a commit, two checks of the commit message
.gitattributes         git stores the .bat files unconverted, so save each with CRLF line endings for cmd.exe
scripts/               the check scripts that just check runs, commitlint.py for commit messages, and
                       installcheck.py, which each build job runs after its installs
tests/                 the pytest suite, one file per module under test
version.py             __version__; CI appends the short commit hash
LICENSE, LICENSE.MIT   GNU AGPL v3 for the project; MIT for the code from DevilXD; every release includes both
README.md, AGENTS.md   the user guide; the engineering rules, which CLAUDE.md includes
docs/                  index.md, ARCHITECTURE.md, building.md, troubleshooting.md
docs/adr/, modules/    decision records (format in adr/README.md); one contract page per Python module
docs/runbooks/         step by step procedures
docs/refinements/      the backlog: index.md and one file per task in tasks/
docs/assets/           the pictures of the four tabs in README.md

settings.json          the settings
cookies.jar            the login session (the rule is /*.jar)
lock.file              the single instance lock
log.txt, dump.dat      written with --log and --dump
cache/                 ImageCache images and mapping.json
lang/English.json      rewritten from default_translation on every run from source
.coverage, .ruff_cache/  written by just check
*.new                  the file json_save writes before it replaces the target
env/                   the virtual environment from setup_env
build/, dist/          PyInstaller output; *.exe, *.zip, *.tmp, *.app and "Twitch Drops Miner/" too
AppDir/, *.AppImage    AppImage output; appimage-build/, appimage-builder/ and *.AppImage.zsync too
.claude/worktrees/     Claude Code's git worktrees; .claude/settings.local.json too
__pycache__, .mypy_cache, .DS_Store
```
