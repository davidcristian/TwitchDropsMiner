# `websocket.py`

**Purpose.** The module keeps the websocket connections to Twitch PubSub (`wss://pubsub-edge.twitch.tv/v1`), the
Twitch service that sends events: drop progress, drop claims, notifications, and the stream state and settings
changes of the tracked channels. `WebsocketPool` distributes the subscribed topics over up to 8 connections. Each
`Websocket` keeps one connection, subscribes its topics, sends pings and reconnects. No GQL request goes through
this module.

## Public contract

### `WebsocketPool(twitch)`

`Twitch` creates one pool, as `Twitch.websocket`.

- `start()` sets `running` and starts the task of every `Websocket` in `websockets`. It returns at once and
  does not wait for a connection ([below](#starting-without-a-connection)).
- `await stop(*, clear_topics=False)` clears `running` and stops every connection. With `clear_topics`, as
  `Twitch.shutdown` calls it, it also removes their topics and their rows in the GUI's Websocket Status box. The
  `Websocket` objects stay in `websockets`.
- `add_topics(topics)` subscribes `WebsocketTopic`s and skips the ones already subscribed. It fills the
  connections in order, up to `WS_TOPICS_LIMIT` topics each, and creates a connection when the others are full,
  started at once when the pool is running. It raises `MinerException("Maximum topics limit has been reached")`
  when `MAX_WEBSOCKETS` connections are full.
- `remove_topics(topics)` unsubscribes topics, given as strings. While the remaining topics fit in one connection
  fewer, it stops the last connection and moves its topics to the others.
- `wait_until_connected()` returns a coroutine that ends when the pool is running. Nothing calls it
  ([task 022](../refinements/tasks/022-unused-code.md)).

### `Websocket(pool, index)`

One connection. `topics` maps a topic string to its `WebsocketTopic`. `start_nowait()`, `stop(*, remove=False)`,
`stop_nowait(*, remove=False)`, `request_reconnect()` and `send(message)` are used by the pool and by the
connection's own task. Nothing reads the `connected` property
([task 022](../refinements/tasks/022-unused-code.md)).

### Topics

`WebsocketTopic(category, topic_name, target_id, process)` is defined in `constants.py`
([constants.md](constants.md)). Its string is `<PubSub topic>.<target_id>`, with the topic name from the
`WEBSOCKET_TOPICS` table. Two topics with the same string are equal. Calling a topic calls
`process(target_id, message)`. The app subscribes to four kinds:

| Category and name | PubSub topic | Handler in `Twitch` |
| --- | --- | --- |
| `User`, `Drops` | `user-drop-events.<user ID>` | `process_drops` |
| `User`, `Notifications` | `onsite-notifications.<user ID>` | `process_notifications` |
| `Channel`, `StreamState` | `video-playback-by-id.<channel ID>` | `process_stream_state` |
| `Channel`, `StreamUpdate` | `broadcast-settings-update.<channel ID>` | `process_stream_update` |

`_run` in `twitch.py` subscribes the two user topics after the login. `CHANNELS_FETCH` subscribes the two channel
topics of each tracked channel, and the channel cleanup unsubscribes them. The other names in `WEBSOCKET_TOPICS`
are not subscribed.

## The 199 channel limit

The limit comes from these values in `constants.py`:

| Constant | Value | Meaning |
| --- | --- | --- |
| `MAX_WEBSOCKETS` | 8 | connections in the pool |
| `WS_TOPICS_LIMIT` | 50 | topics per connection |
| `BASE_TOPICS` | 2 | the user topics |
| `TOPICS_PER_CHANNEL` | 2 | `StreamState` and `StreamUpdate` |
| `MAX_TOPICS` | 398 | `(MAX_WEBSOCKETS * WS_TOPICS_LIMIT) - BASE_TOPICS` |
| `MAX_CHANNELS` | 199 | `MAX_TOPICS // TOPICS_PER_CHANNEL` |

`CHANNELS_FETCH` keeps at most `MAX_CHANNELS` channels and unsubscribes the rest, so `add_topics` does not raise.
With the 2 user topics and the topics of 199 channels, the 8 connections hold 50 topics each, and one more topic
raises the `MinerException`.

## Connection and reconnect

`Websocket._handle` is the task of one connection:

1. It waits until `Twitch` is logged in (`wait_until_login`), then connects, through `settings.proxy` when one is
   set.
2. Before it connects again, it waits the time that `ReconnectDelay` returns ([reconnect.md](reconnect.md)),
   from `ExponentialBackoff(maximum=3*60)`: about 1, 2, 4 seconds and so on, at most 3 minutes. A failed connect
   (a timeout, a response error or a connection error) waits, and so does a connection that ended less than
   `WS_MIN_UPTIME` (60 seconds) after it opened. After a connection that stayed open that long, it connects
   again at once and the backoff starts again from the first delay. Each connection sends a `PING` and its
   `LISTEN` messages, so without the wait a server that closes every connection at once would get them as fast
   as the handshake allows.
3. While connected, it repeats three steps. It sends a `PING` at once on each new connection and then every
   `PING_INTERVAL` (3 minutes). When topics changed, it sends `LISTEN` for the added ones and `UNLISTEN` for the
   removed ones, 20 topics per message, with the access token. It collects incoming messages until 0.5 seconds
   pass with no message, and handles them.
4. It reconnects when no `PONG` arrives within `PING_TIMEOUT` (10 seconds) of a `PING` sent on the same
   connection, when Twitch sends `RECONNECT`, when Twitch closes the connection, and after any exception in the
   loop. The new connection is opened after the wait of step 2 and subscribes every topic of the connection
   again.
5. It ends when `stop()` closed the connection, or when the HTTP session is closed. `stop()` waits up to 2
   seconds for the task to end and then cancels it, so a task that waits before a reconnect stops within 2
   seconds.

Every message the app sends, except `PING`, has a random 30 character nonce. The GUI's Websocket Status box shows
each connection's state and topic count.

## Starting without a connection

`_run` in `twitch.py` calls `start()` before it subscribes the user topics and again at each `INVENTORY_FETCH`,
and goes on at once. So while PubSub cannot be reached, the run still fetches the inventory, claims drops and
switches channels, and closing the window ends it. With no events, `_watch_loop` reads the drop progress with
`CurrentDrop` ([twitch.md](twitch.md#watch-loop)), and a finished drop is claimed at the next inventory fetch,
at most an hour later.

The fetch can then start before the user topics are subscribed: at startup, after a restart, and at an hourly
reload while a connection reconnects. A drop event sent in between is lost, with the same effect. At startup and
after a restart, the run watches no channel before that fetch ends, so such an event can only come from watching
before the run started.

## How events reach `Twitch`

A `MESSAGE` from Twitch names its topic. `Websocket._handle_message` looks the topic up in the connection's
`topics`, decodes the JSON message inside, and starts a task that calls the `WebsocketTopic`. The topic calls its
handler in `Twitch` with the target ID and the message. A message for a topic that is no longer subscribed is
dropped. A `PONG` sets the pong deadline to the time of the next ping, a `RESPONSE` is ignored and an unknown
type is logged. A message that is not JSON, or that lacks a field that this handling reads, is logged as a
warning and skipped, and the rest of its batch is handled. The handlers and what they do are in
[twitch.md](twitch.md#websocket-handlers).

## Invariants

- `send` logs each message at DEBUG through `redact`, so the `auth_token` of a `LISTEN` or `UNLISTEN` message
  shows as `<hidden>` ([redact.md](redact.md)). The `received:` line and the warnings about an unknown or a
  malformed message print the parsed message through `redact` too. A new log call that prints a message does
  the same ([ADR-0011](../adr/ADR-0011-secrets-in-logs.md)).
- The pool holds at most `MAX_WEBSOCKETS * WS_TOPICS_LIMIT` (400) topics, and `Twitch` stays within this through
  `MAX_CHANNELS`. A new topic for each channel must increase `TOPICS_PER_CHANNEL`, and a new user topic must
  increase `BASE_TOPICS`, so that `MAX_CHANNELS` goes down to match.
- `add_topics` and `remove_topics` send no message. They change `topics` and set `_topics_changed`, and the
  pool's methods can also create or stop a connection without waiting for it. The `LISTEN` and `UNLISTEN`
  messages go out from `_handle_topics` on a connected socket. So `_run` can call both at any time, without
  waiting for a connection.
- Each event is handled in its own task, so the receive loop does not wait for a handler, and two events can be
  handled at the same time.
- `_handle` uses `task_wrapper(critical=True)`: an exception that escapes its reconnect loop sets `State.EXIT` in
  `Twitch` ([task 013](../refinements/tasks/013-crashed-task-ends-the-app.md)).
- `stop` keeps the `Websocket` objects, and the next `start` connects every one of them, including those left
  with no topics. A later `remove_topics` call stops the ones not needed. After a stop of a pool with 3
  connections, all 3 stay in `websockets` with 0 topics, and new topics go to the first one
  ([task 024](../refinements/tasks/024-websocket-pool-keeps-empty-connections.md)).
- The module is over the 300 line cap ([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)).

**Dependencies.** `utils` (`ExponentialBackoff`, `AwaitableValue`, `task_wrapper`, `chunk`, `create_nonce`,
`json_minify`, `format_traceback`, `CHARS_ASCII`), `exceptions` (`MinerException`, `WebsocketClosed`),
`constants` (`PING_INTERVAL`, `PING_TIMEOUT`, `MAX_WEBSOCKETS`, `WS_TOPICS_LIMIT`, `WS_MIN_UPTIME`),
`reconnect` (`ReconnectDelay`), `redact` for the log lines that print a message, and `translate` for the status
texts. Third party: aiohttp.
