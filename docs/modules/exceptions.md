# `exceptions.py`

**Purpose.** The app's own exception classes. `MinerException` is the base class, and its subclasses name a
request failure or a request from the user to exit or reload. The module has no logic beyond default messages
and imports nothing.

## Public contract

The classes, with the message each one has by default:

```
Exception
└── MinerException            "Unknown miner error" when raised without arguments
    ├── ExitRequest           "Application was requested to exit"
    ├── ReloadRequest         "Application was requested to reload entirely"
    └── RequestException      "Unknown error during request" when raised without arguments
        ├── RequestInvalid    "Request became invalid during its retry loop"
        ├── WebsocketClosed   "Websocket has been closed"; has the attribute received: bool
        └── GQLException      takes the error message as its one argument
```

## How an exception ends a run

Any exception other than `ExitRequest` and `ReloadRequest` that leaves `Twitch._run` reaches `Twitch.run`, which
treats it as a fatal error. While the "Restart after a crash after" setting is not "Never", `Twitch.run` waits
and starts again ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)). Otherwise it raises the error to
`main()`, which prints it and exits with code 1 ([main.md](main.md#exit-codes)). In a background task that
`utils.task_wrapper` wraps, any other exception is logged and raised again; with `critical=True` the wrapper
passes it to `Twitch.task_failed` instead, and `Twitch._run` raises it as a fatal error.

## Each class

**`MinerException`** is raised directly for errors that have no subclass:

- `Channel.get_stream` wraps a `MinerException` from `Twitch.gql_request` in a new one that names the channel.
  It also catches one from the `AvailableDrops` query, logs it at `CALL` level and continues.
  `Channel._online_delay` catches the wrapped one and ends the online check. It logs the error at `WARNING`,
  except when it wraps an `ExitRequest`.
- `Twitch.get_live_streams` wraps a `GQLException` in a new one that names the game slug.
- `gqldata.merge_data` raises it when the inventory and campaign data have values of different types for one
  key, neither of them null.
- `WebsocketPool.add_topics` raises it when the topics do not fit in `MAX_WEBSOCKETS` websockets.
- `Translator.__call__` raises it for a key path that the current translation does not have
  ([translate.md](translate.md)).
- `TrayIcon.get_title` raises it when the tray tooltip cannot be shortened to 127 characters
  ([gui.md](gui.md#the-tray-icon)).
- `Channel.get_spade_url` raises it when it finds no spade URL. Only `Channel._send_watch_spade` calls it, and no
  code calls that method ([task 022](../refinements/tasks/022-unused-code.md)).

No other code catches `MinerException` by name.

**`ExitRequest`** means the user closed the window.

- Raised by `GUIManager.coro_unless_closed` when the window closes before the wrapped coroutine ends, by
  `Twitch.request` before each try when `GUIManager.close_requested` is set, and by `Twitch.fetch_inventory`
  after each campaign is added to the Inventory tab.
- Caught by `Twitch.run`, which ends the run loop, and by `utils.task_wrapper`, which ends the task without a
  log line. `Channel._online_delay` ends the online check without a log line when its `MinerException` wraps
  one.

**`ReloadRequest`** means a full restart of the client without closing the window.

- Raised by `Twitch._run` in `State.RESTART`. Only `HelpTab._invalidate_token` sets that state, after the
  "Invalidate" button sends the token to Twitch's revoke endpoint.
- Caught by `Twitch.run`, which calls `Twitch.shutdown()` and starts `Twitch._run` again, and by
  `utils.task_wrapper`.

**`RequestException`** is the base class for request failures.

- Raised directly only by `Twitch.run`, which wraps an `aiohttp.ContentTypeError` in one with the message
  `_("login", "unexpected_content")` and the original error as its cause. It goes to
  `Twitch._await_restart` like any other fatal error.
- Caught by `Channel._send_watch_spade` and `Channel._send_watch_gql`, which return `False`. No code calls
  either method.

**`RequestInvalid`** means the deadline of a request passed before the request was sent.

- Raised by `Twitch.request` when the `invalidate_after` time, less the session timeout, has passed before a
  try. Only `_AuthState._oauth_login` passes `invalidate_after`, set to the expiry of the device code.
- Caught by `_AuthState._oauth_login`, which then asks Twitch for a new device code.

**`WebsocketClosed`** means a websocket connection ended. `received` is `True` when the server sent a close
frame.

- Raised by `Websocket._gather_recv` for a connection error, a `CLOSE`, `CLOSED` or `ERROR` message, and by
  `Websocket.send` for a connection error.
- Caught by `Websocket._handle`. When `received` is `True` it logs a warning and reconnects. When the app
  closed the websocket itself, it sets the status to "Disconnected" and returns. In every other case it
  reconnects.

**`GQLException`** means Twitch returned an error in the response to a GQL request.

- Raised by `Twitch.gql_request` for a response with an `error` key, or with an `errors` list in which no
  message is one the method retries or clears. It retries `service error` and `PersistedQueryNotFound` once,
  retries `service timeout`, `request cancelled`, `service unavailable` and `context deadline exceeded`, and
  sets the data at the error's path to `None` for `server error`, or logs the error when the path names no
  field.
- Raised by `gqldata.user_inventory` and `gqldata.campaign_summaries` when the `Inventory` or `Campaigns`
  response has a null user, inventory, claimed drop or award time. `Twitch.fetch_inventory` does not catch it,
  so the run ends ([gqldata.md](gqldata.md#a-null-inventory)).
- Caught by `BaseDrop._claim`, which returns `False` because the claim may have failed; by
  `Twitch._watch_loop` around the `CurrentDrop` query, which then uses no drop data; and by
  `Twitch.get_live_streams`, which raises a `MinerException` that names the game.

## Invariants

- `ExitRequest` and `ReloadRequest` are control flow, not errors. A broad `except Exception` around a call that
  can raise them raises the exception again, as the blocks in `Twitch.fetch_inventory` and
  `Twitch.bulk_check_online` do, because `Twitch.run` must see it to exit or reload.
- `except MinerException` also catches `ExitRequest` and `ReloadRequest`, because they are subclasses.
  `Channel.get_stream` turns an `ExitRequest` from its GQL request into a plain `MinerException` this way. It runs
  only in the task that `Channel.check_online` starts with `asyncio.create_task`. Nothing awaits that task, so
  `Channel._online_delay` catches the `MinerException`, and reads its cause to tell a closing window from an
  error.

**Dependencies.** None.
