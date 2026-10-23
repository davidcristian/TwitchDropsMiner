# `reconnect.py`

**Purpose.** `ReconnectDelay` returns the time a PubSub websocket waits before it connects again.
`Websocket._backoff_connect` in `websocket/connection.py` makes the connections and calls `ReconnectDelay` for each wait
([websocket.md](websocket.md#connection-and-reconnect)). The module has no I/O, so a test runs it with a fake
backoff and a fake clock.

## Public contract

- `ReconnectDelay(backoff, min_uptime, clock)` keeps the state of one websocket. `backoff` is a `Backoff`,
  `min_uptime` is in seconds, and `clock` returns the current time in seconds.
- `opened()` records the time a connection opened.
- `next_delay()` returns the seconds to wait after a connection closed or failed to open:
  - 0 after a connection that stayed open for at least `min_uptime` seconds. It also resets the backoff.
  - the next delay of `backoff` after a shorter connection, and after a connect that failed.
- `Backoff` is the `Protocol` of the backoff: `next()` returns a delay in seconds and `reset()` starts again from
  the first delay. `ExponentialBackoff` in `utils/backoff.py` is one ([utils.md](utils.md)).

## Invariants

- `next_delay` reads the time recorded by `opened` once and then forgets it. A failed connect after a long
  connection waits the first backoff delay.
- A connection that Twitch closes at once, or that ends after a `RECONNECT` or an error, waits the same delays
  as a failed connect. With `ExponentialBackoff(maximum=3*60)` that is about 1, 2, 4 seconds and so on, at most 3
  minutes. So one websocket connects about 10 times in the first 10 minutes and then once every 3 minutes,
  however fast Twitch ends each connection.

**Dependencies.** None: the standard library only.
