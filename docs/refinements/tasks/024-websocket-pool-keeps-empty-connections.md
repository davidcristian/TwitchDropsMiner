# After a restart, the PubSub pool connects websockets that have no topics

**Status:** done 2026-10-22
**Area:** websocket
**Origin:** Found on 2026-10-18 while the docs were written, [websocket.md](../../modules/websocket.md#invariants)
**Verified:** 2026-10-22

`WebsocketPool.stop(clear_topics=True)` in `websocket.py` calls `Websocket.stop(remove=True)` on each connection.
That closes the connection, clears its `topics` and removes its row from the Websocket Status box, but the pool
keeps the `Websocket` object in `websockets`. `WebsocketPool.start()` then calls `start_nowait()` on every object
in the list. `add_topics` fills the connections in order from index 0, so when the next run has fewer topics, the
last connections stay connected with none.

## When it is called

Only `Twitch.shutdown()` calls `stop(clear_topics=True)`, and `shutdown()` runs in three places:

- at exit, from `main.py`, after which nothing starts again;
- in `Twitch.run` after a `ReloadRequest`, which `_run` raises in `State.RESTART`. The Invalidate button on the
  Help tab sets that state;
- in `Twitch._await_restart`, after a fatal error when the `restart_delay` setting is above 0.

In the last two cases `run` calls `_run` again, and `_run` calls `self.websocket.start()` before it adds a topic.

## How it was confirmed

The writer's script `check_ws_stop.py`, run against a copy of the code, added 120 topics, called
`stop(clear_topics=True)` and added 10. It printed `before stop: [50, 50, 20]`, then
`after stop: 3 websockets, [0, 0, 0]`, then `after adding 10: [10, 0, 0]`.

A second script replaced `Websocket.start` and `Websocket.start_nowait` with stubs that record the index, so it
opened no connection:

1. The 2 user topics and 198 channel topics (99 channels) gave `[50, 50, 50, 50]`.
2. `stop(clear_topics=True)` and then `start()` started connections 0, 1, 2 and 3.
3. The 2 user topics and 20 channel topics (10 channels) gave `[22, 0, 0, 0]`.
4. `remove_topics([])` returned at once and kept 4 connections.
5. `remove_topics` with one subscribed topic stopped connections 3, 2 and 1 and left `[21]`.

## How long they stay

`WebsocketPool.remove_topics` stops the last connection while the remaining topics fit in one connection fewer.
It makes that check only when it is called with at least one topic. `Twitch._run` calls it in
`State.CHANNELS_CLEANUP` when that state removes channels, and in `State.CHANNELS_FETCH` when the list is cut to
`MAX_CHANNELS`. `shutdown()` clears `channels`, so the first cleanup after the restart removes nothing. The empty
connections stay until a later cleanup removes at least one channel:

- at a refresh (every 5 minutes plus up to 60 seconds with the default `refresh_interval`), when a channel
  without an ACL went offline or changed game;
- at the next full reload, at most an hour later, which removes every tracked channel.

With no game to mine, no channel is tracked, no cleanup removes one, and the empty connections stay until the
app closes.

## Cost

Each empty connection is a PubSub websocket to `wss://pubsub-edge.twitch.tv/v1`. It costs one connection when it
starts, a `PING` every `PING_INTERVAL` (3 minutes), so 20 per hour, and a new connection whenever Twitch closes
it. These are not GQL requests, so the `RateLimiter` does not count them. With `MAX_WEBSOCKETS` at 8, up to 7
connections can be empty after a restart. The user sees nothing wrong, apart from extra rows in the Websocket
Status box.

## What a fix involves

When `clear_topics` is set, `WebsocketPool.stop` empties `websockets` after the connections have stopped. The
next `add_topics` then creates only the connections it needs, and starts each one at once because the pool is
running, as on the first run after launch. The fix removes requests and adds none. A test needs no Twitch
connection: it imports `websocket.py` and replaces `start_nowait` as the second script did.

How it came about: `clear_topics` and its call in `shutdown()` came from the original project on 2022-09-17
("Add clear_topics to websocket stop" and "Hard-reload on integrity expiring during request"). Restart after a
fatal error added the third path through `shutdown()` on 2026-08-25.

## History

- 2026-10-18: Opened while the docs were written. The writer's script and a second script with stubbed
  connections confirmed it, and reading `Twitch._run` showed when `remove_topics` stops the empty connections.
- 2026-10-20: `WebsocketPool.start()` now calls `start_nowait()` on each connection and does not wait for it,
  and `Websocket.start` was removed. The empty connections still start, so the task stays open.
- 2026-10-21: Importing `websocket.py` in a test no longer fails, so the fix can have a suite test.
- 2026-10-22: Done. The claim still held: `WebsocketPool.stop` kept the stopped objects, and `start` connected
  each one again. With `clear_topics`, `stop` now empties `websockets`, so the next `add_topics` creates and
  connects only the connections its topics fill ([websocket.md](../../modules/websocket.md#invariants)). The
  test in `tests/test_websocket.py` runs 120 topics, a stop with `clear_topics` and 10 topics. Before the change
  the pool held `[10, 0, 0]` and opened 6 connections, after it `[10]` and 4. The change sends no GQL request
  and removes up to 7 PubSub connections after a restart, with the `PING` that each sends every 3 minutes.
