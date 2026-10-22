# `twitch.py`

**Purpose.** `Twitch` is the client object. It logs in, sends every HTTP and GQL request, runs the state machine
that decides what to mine, and runs the task that sends the watch requests. It keeps the other parts as
attributes: `gui` (a `GUIManager`), `websocket` (the PubSub `WebsocketPool`), `channels` and `inventory`.
`_AuthState` holds the login session. The module is far over the 300 line cap
([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)).

## Public contract

### Lifecycle and state, used by `main.py`, `gui.py` and `inventory.py`

- `Twitch(settings)` stores the settings and creates the GUI, the websocket pool and `_AuthState`.
- `await run()` runs `_run` until the app exits. On `ReloadRequest` it calls `shutdown()` and runs `_run` again.
  On `ExitRequest` it returns. Any other exception goes to the [restart](#restart-after-a-fatal-error).
- `await shutdown()` stops watching, the tasks, the online checks of the channels and the websockets, saves
  `cookies.jar`, closes the HTTP session and clears the run's data and the channel list in the window. It takes
  at least half a second, so aiohttp can close the session. A failed save of `cookies.jar` is logged, and the
  shutdown goes on ([savefiles.md](savefiles.md#saves-during-the-run-outside-the-inventory-fetch)).
- `close()` sets `State.EXIT`, and `GUIManager.close` calls it. `prevent_close()` clears the GUI's close
  request, so the window stays open to show an error. `print(message)` writes to the Output box, and
  `save(force=False)` saves the GUI state and the settings; `main()` calls it at exit.
- `change_state(state)` stores the next `State` and sets the event `_run` waits on. After `State.EXIT` the
  state no longer changes, so a late call cannot restart an app that is closing. Only the last call is kept,
  so a call made while a handler awaits is replaced by the state that handler sets next
  ([task 012](../refinements/tasks/012-button-requests-lost-during-a-fetch.md)).
- `state_change(state)` returns a function with no arguments that calls `change_state(state)`. The GUI uses it
  as a button command: `Switch` in the channel list (`State.CHANNEL_SWITCH`) and `Reload` on the Settings tab
  (`State.INVENTORY_FETCH`).

### Requests

- `request(method, url, *, invalidate_after=None, **kwargs)` is an async context manager. It sends the request
  through `settings.proxy` when one is set, and yields the `aiohttp.ClientResponse` with its body read for any
  status below 500. It retries a 5xx status, a connection error other than a certificate error, a timeout or a
  payload error with `ExponentialBackoff(maximum=3*60)`, with no limit on the count. It prints each retry to
  the Output box, except after a connection error on the first try. It raises `ExitRequest` when the
  window closes, and `RequestInvalid` when `invalidate_after` is less than one session timeout away. It logs
  its arguments, and the status, method, URL and headers of each response, at DEBUG through `redact`, so the
  token, the device code, cookies, a proxy password and the playback token in the usher URL show as
  `<hidden>` ([redact.md](redact.md)). The URL in its retry message goes through `redact` too. It
  raises a `ClientHttpProxyError` from a proxy without a retry, after it passes the error's `request_info`
  through `redact`, so the traceback shows the proxy password as `<hidden>`.
- `gql_request(ops)` sends one GQL operation, or a list of them, in one POST to `https://gql.twitch.tv/gql`, and
  returns the response JSON, or a list of them for a list. See [GQL requests](#gql-requests).
- `get_auth()` checks the login, logs in when needed and returns the `_AuthState`. `wait_until_login()` returns
  a coroutine that ends once the login is valid. `get_session()` returns the `aiohttp.ClientSession` and creates
  it on the first call, with timeouts of 5 and 10 seconds times `settings.connection_quality` (1 to 6), and with
  the cookies of `cookies.jar`. See [Login](#login) for a file that fails to load.
- `_client_type` is `ClientType.ANDROID_APP`, and the GUI reads its `CLIENT_ID`. Updating it is in
  [the GQL runbook](../runbooks/gql-operations.md).

### Channels, campaigns and watching

- `channels` is an `OrderedDict[int, Channel]` of at most `MAX_CHANNELS` (199) tracked channels. `inventory` is
  the `list[DropsCampaign]`, `wanted_games` the `list[Game]` to mine with the highest priority first, and
  `watching_channel` an `AwaitableValue[Channel]`. `_campaigns` maps a campaign ID to its `DropsCampaign`.
- `can_watch(channel)` returns True when the channel is online, a campaign of a game in `wanted_games` has
  `can_earn(channel)` True, and either the channel's game is in `wanted_games` with drops enabled, or that
  campaign is for a special game ([inventory.md](inventory.md#special-games)). A campaign whose game the Exclude
  list or the "Priority list only" mode keeps out of `wanted_games` makes no channel watchable.
- `get_priority(channel)` returns the index of the channel's game in `wanted_games`, or `MAX_INT` when the
  channel is offline or its game is not wanted. A lower number is a higher priority.
- `should_switch(channel)` returns True when `can_watch(channel)` is True and no channel is watched, or the
  watched channel cannot be watched, has a lower priority, or has the same priority while only the new channel
  is ACL-based (on a campaign's ACL, its access control list of allowed channels).
- `watch(channel)` and `stop_watching()` set and clear the watched channel. `restart_watching()` stops the
  minute countdown and ends the watch loop's wait, so the next watch request goes out at once. A call before
  that wait starts is lost ([task 028](../refinements/tasks/028-watch-restart-dropped.md)).
- `Channel` calls `on_channel_update(channel, stream_before, stream_after)` after a status change. It watches a
  channel that came online or changed its stream, if `should_switch` allows it, and enters
  `State.CHANNEL_SWITCH` when the watched channel can no longer be watched.
- `get_live_streams(game, *, limit=20, drops_enabled=True)` sends one `GameDirectory` query and returns up to
  `limit` live channels of the game, or none when the game is null. `bulk_check_online(channels)` is in
  [channel.md](channel.md#bulk-check).

## GQL requests

Every GQL request in the app goes through `gql_request`. Each POST takes a slot in `_qgl_limiter`, a
`RateLimiter(capacity=5, window=1)` from [ratelimit.md](ratelimit.md): at most 5 POSTs start in any span of 1
second, and at most 5 run at the same time. A list of operations is one POST, so a batch of 20 takes one slot.
The code comment on the limiter says not to change these values ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)).

| Error message in the response | What `gql_request` does |
| --- | --- |
| `service error`, `PersistedQueryNotFound` | retries once, after at least 5 seconds; the second one raises `GQLException` |
| `server error` | sets the field the error's `path` names to `None` and returns the response; when the path names no field, logs the error and returns the response as it is |
| `service timeout`, `request cancelled`, `service unavailable`, `context deadline exceeded` | retries with `ExponentialBackoff(maximum=60)`, with no limit on the count |
| any other message, or an `error` key | raises `GQLException` |

The reads of `fetch_inventory`, `fetch_campaigns`, `_watch_loop` and `process_drops` go through
[gqldata.md](gqldata.md), and those of `get_live_streams` and `bulk_check_online` through
[streamdata.md](streamdata.md). Both leave out an item that a server error set to null, so such an error does
not end the run. A null user or inventory in the `Inventory` or `Campaigns` response still ends it
([gqldata.md](gqldata.md#a-null-inventory)). A null field in stream data is read as an offline channel or a
stream without a game ([streamdata.md](streamdata.md#null-stream-fields)).

## Login

`get_auth` calls `_AuthState.validate`, which holds a lock so that concurrent callers log in once. It creates a
random `session_id`, reads `device_id` from the `unique_id` cookie that a GET of `https://www.twitch.tv` sets, and
takes `access_token` from the `auth-token` cookie in `cookies.jar`. Without that cookie, `_oauth_login` runs the
OAuth device code flow: it POSTs to `https://id.twitch.tv/oauth2/device`, shows the code through the Login Form
(`ask_enter_code`), then POSTs to `https://id.twitch.tv/oauth2/token` every `interval` seconds until the user has
entered the code. An expired code raises `RequestInvalid`, and the flow starts again. A GET of
`https://id.twitch.tv/oauth2/validate` returns `user_id`. After a 401 it clears the domain's cookies, and after
a token for another client ID it deletes `cookies.jar`. In both cases it logs in again. Each of the two checks
runs at most twice, then raises `RuntimeError`. At the end it saves the cookie jar with `save_cookies`, which
writes a second file and renames it over `cookies.jar`. A save that raises `OSError`, such as on a full disk, is
logged, the old `cookies.jar` stays whole and the login goes on
([savefiles.md](savefiles.md#saves-during-the-run-outside-the-inventory-fetch)).

When `cookies.jar` fails to load, `get_session` logs a warning with the error's class and text, empties the
jar and goes on, so the login runs again. aiohttp reads a file that is not JSON as a pickle, so the error can
be of many types, and `get_session` catches `Exception`. With aiohttp 3.14.3, an empty file raised `EOFError`,
a cut off file `KeyError`, a JSON list `AttributeError` and a folder `IsADirectoryError`. None of these texts
held a cookie value.

The `Invalidate` button on the Help tab revokes the token at `https://id.twitch.tv/oauth2/revoke`. On a 200
response it calls `invalidate(delete_cookies=True)`, and in every case it enters `State.RESTART`. The device
code flow is the only login: the app has no password login ([ADR-0010](../adr/ADR-0010-device-code-login.md)).

## State machine

`_run` logs in, starts the websocket pool and `_watch_loop`, subscribes to the user's `Drops` and
`Notifications` topics and enters `State.INVENTORY_FETCH`. It does not wait for a PubSub connection, so the run
goes on and the window can close while PubSub cannot be reached
([websocket.md](websocket.md#starting-without-a-connection)). It then handles one state per pass and waits for the
next `change_state`. [ARCHITECTURE.md](../ARCHITECTURE.md#the-state-machine) has the table of the states, what
each one does, the state that follows it and the events that change it. `fetch_inventory` builds a
`DropsCampaign` for each campaign whose `game`, `self`, `allow` and `timeBasedDrops` fields are not null
([gqldata.md](gqldata.md#null-campaign-details)), keeping only the drops that `TimedDrop` can read
([gqldata.md](gqldata.md#null-drops)), and `GAMES_UPDATE` computes the [wanted games](#wanted-games).
`INVENTORY_FETCH` saves the image cache and the settings through `save_each`, which logs a save that raises
`OSError`, so a full disk does not end the run ([savefiles.md](savefiles.md)).

An offline channel has priority `MAX_INT`, so offline channels sort last and are the first ones cut at
`MAX_CHANNELS` ([task 001](../refinements/tasks/001-offline-acl-channels-trimmed-first.md)). The cut unsubscribes
a channel's topics and cancels its online check ([channel.md](channel.md#invariants)), and the rebuilt channel
list has no row for it.

## Watch loop

Every `WATCH_INTERVAL` (20 seconds) `_watch_loop` takes the watched channel, waiting until there is one, stops
watching it when it is offline, and calls `Channel.send_watch` ([channel.md](channel.md#watching)). About 15
seconds later, when `gui.progress.minute_almost_done()` is True (the countdown for the minute has stopped or has
at most 10 seconds left), it sends a `CurrentDrop` GQL query for the drop's minutes, one per cycle at most.
When that fails or names no drop, which a null `currentUser`, `dropID` or `currentMinutesWatched` also does,
`DropsCampaign.bump_minutes` adds an estimated minute ([inventory.md](inventory.md#progress)).

## Maintenance task

`_maintenance_task` starts at the end of every `fetch_inventory`, replacing the previous one. After one hour it
enters `State.INVENTORY_FETCH` and ends: this is the hourly reload. Until then it sleeps until the earliest of:

- the next stream check, `settings.refresh_interval` minutes from now plus a random 0 to 60 seconds
  (`REFRESH_JITTER`), so that the requests do not follow a fixed schedule. The setting is "Check for new streams
  every" on the Settings tab: "Never (hourly reload only)", stored as 0, or 1, 2, 5, 10, 15 or 30 minutes,
  default 5.
- a time trigger in `_mnt_triggers`: the start or end of a campaign or of one of its drops, for each campaign
  that can progress within the hour.

At each of these it enters `State.CHANNELS_CLEANUP`, which goes on to `State.CHANNELS_FETCH`. That costs one
`GameDirectory` query per wanted game with a campaign that has no ACL, plus `GetStreamInfo` batches for the
untracked ACL channels (and `AvailableDrops` batches with the extra drops check on), and no inventory reload
([ADR-0003](../adr/ADR-0003-stream-refresh.md)). With no wanted game, `CHANNELS_CLEANUP` moves to `IDLE`
instead and prints the no campaign message each time
([task 020](../refinements/tasks/020-no-campaign-message-repeats.md)).

## Restart after a fatal error

When `_run` raises any exception other than `ReloadRequest` and `ExitRequest`, `run` calls `_await_restart`.
With `settings.restart_delay` at 0 it returns False, and `run` raises the error to `main.py`, which shows it and
stops. Otherwise it prints the traceback, calls `shutdown()`, shows the restart time in the status line and the
Output box, and waits `restart_delay` minutes plus a random 0 to 60 seconds (`RESTART_JITTER`). `run` then starts
`_run` again, which begins with a full reload
([task 019](../refinements/tasks/019-restart-runs-a-full-reload.md)). Closing the window ends the wait and the
app. Every error waits the same delay. The setting is "Restart after a crash after" on the Settings tab: "Never
(stay stopped)", stored as 0, or 1, 5, 10, 15, 30 or 60 minutes, default 10
([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)).

## Wanted games

`GAMES_UPDATE` computes `wanted_games` from the campaigns and four settings:

1. `priority` (the Priority list) and `exclude` (the Exclude list) are compiled with `gamelib.compile_patterns`
   ([ADR-0005](../adr/ADR-0005-list-patterns.md)).
2. Each campaign's game gets a rank: the index of the first matching Priority entry (`gamelib.match_rank`),
   else `len(priority)` plus its index in `settings.detected_games`, so an installed game ranks below every
   Priority entry ([ADR-0004](../adr/ADR-0004-installed-game-detection.md)), else `MAX_INT`.
3. `settings.priority_mode` orders the campaigns: `PriorityMode.ENDING_SOONEST` ("Ending soonest") by `ends_at`,
   `PriorityMode.LOW_AVBL_FIRST` ("Low availability first") by `availability`. Then every mode sorts them by
   rank. The sorts are stable, so the mode decides the order within one rank. They change `inventory` in place.
4. A campaign's game is added once when it matches no Exclude entry and the campaign `can_earn_within` the next
   hour. Under `PriorityMode.PRIORITY_ONLY` ("Priority list only", the default) its rank must be below `MAX_INT`.

So an excluded game is never wanted, even when a Priority entry matches it or it is installed. Under the other
two modes every other game with a campaign that can progress within the hour is wanted. The Games Being Mined
table on the Settings tab shows the list.

`detect_games` runs `gamelib.scan_directories(settings.game_dirs)` in a thread, matches the result to the
campaigns' games with `gamelib.match_games` and stores the matched names in `settings.detected_games`. A changed
list enters `State.GAMES_UPDATE`, with no reload. It runs on every `INVENTORY_FETCH`, from the `Rescan` button
and after a game folder is added or removed. A call during a scan returns at once. The thread scans a copy of
`game_dirs`, and when a folder is added or removed during the scan, the result is dropped and the folders are
scanned again. A scan error is printed once while it persists ([gamelib.md](gamelib.md)).

## Websocket handlers

`_run` and `CHANNELS_FETCH` pass these methods to `WebsocketTopic` ([websocket.md](websocket.md#topics)):

- `process_drops`: `drop-progress` updates the drop's minutes. `drop-claim` stores the claim ID, claims the drop
  and sends `CurrentDrop` up to 8 times, 2 seconds apart, until Twitch reports another drop or none. A null
  `currentUser` counts as none. Then it restarts watching, or enters `State.INVENTORY_FETCH` when the campaign
  has nothing left on the channel. A failed claim, such as one with a null `ClaimDrop` result
  ([inventory.md](inventory.md#claiming)), goes through the same steps. A `drop-claim` event for a drop that is
  already claimed does nothing: the claim in `State.GAMES_UPDATE` or the first event already restarted watching
  or reloaded.
- `process_notifications`: a drop or emote reward notification enters `State.INVENTORY_FETCH` and deletes the
  notification with `NotificationsDelete`. `process_stream_state` and `process_stream_update` pass stream
  events to `Channel` ([channel.md](channel.md#online-checks)).

## Invariants

- Every GQL request goes through `gql_request` and `_qgl_limiter`, whose values stay at `capacity=5, window=1`,
  because a burst of requests puts the account at risk ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)).
- `State.INVENTORY_FETCH` runs at startup, once an hour, after a drop claim whose campaign cannot continue on
  the watched channel, after a reward notification, after a restart and from the `Reload` button. No new timer
  may run it more often: a reload sends a `GetStreamInfo` operation, 20 to a request, for every ACL channel of
  the wanted campaigns, and these can be thousands. New periodic work enters `State.CHANNELS_CLEANUP` instead,
  which moves on to `State.CHANNELS_FETCH`.
- `_run`, the handlers, the tasks and the tkinter GUI share one asyncio event loop (`GUIManager._poll` runs the Tk
  events). A blocking call freezes the window, so `detect_games` scans the folders with `asyncio.to_thread`. At
  `-vvvv`, a `DEBUG` record that `gamelib` logs there goes to `_TKOutputHandler` in `gui.py`, whose Tk call from
  that thread raises `RuntimeError` and ends the scan
  ([task 021](../refinements/tasks/021-scan-thread-logs-into-tk.md)).
- `_watch_loop` and `_maintenance_task` use `task_wrapper(critical=True)`. An exception in either is logged and
  sets `State.EXIT`, so the run ends without the automatic restart
  ([task 013](../refinements/tasks/013-crashed-task-ends-the-app.md)).
- `shutdown` cancels the online check of each tracked channel, clears the channels, the GUI channel list,
  inventory, drops, login state, wanted games and triggers, and resets `_no_channel_printed` and
  `_scan_errors_printed`, so the next `_run` starts as a fresh one would.
  It does not clear `_campaigns` ([task 027](../refinements/tasks/027-campaigns-never-cleared.md)). A new field
  filled during a run must be cleared there.
- `channels` stays within `MAX_CHANNELS` ([websocket.md](websocket.md#the-199-channel-limit)).
- `CHANNELS_FETCH` keeps the old channels in `channels` during its requests and replaces them after the last
  one, with no `await` in between. So `process_stream_state` and `process_stream_update` find the channel of an
  event that arrives during the requests, and a `stream-down` for the watched channel still makes the app switch.

**Dependencies.** `gui`, `channel`, `websocket`, `inventory`, `gamelib`, `gqldata`, `streamdata`, `translate`,
`redact`, `savefiles`, `ratelimit`, `exceptions`, `utils` and `constants`. Third party: aiohttp and yarl.
