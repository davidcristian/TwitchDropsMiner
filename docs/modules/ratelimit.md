# `ratelimit.py`

**Purpose.** `RateLimiter` limits how many requests start in a span of time and how many are open at once.
`Twitch.__init__` creates `RateLimiter(capacity=5, window=1)` as `_qgl_limiter`, and `Twitch.gql_request` enters
it around each POST to GQL ([twitch.md](twitch.md#gql-requests)). It enforces the 5 GQL requests per second of
[the one hard rule](../../AGENTS.md#the-one-hard-rule). The module imports no other module of the app, so a test
runs it on an event loop with a virtual clock.

## Public contract

- `RateLimiter(*, capacity, window, clock=time.monotonic)` is an async context manager: `async with limiter:`
  waits until a request may start, then counts it. A `capacity` below 1 raises `ValueError`. `clock` returns the
  time in seconds on the clock of the running event loop, which `asyncio.sleep` measures. The asyncio event loops
  use `time.monotonic`.
- A request starts when both of these are true:
  - fewer than `capacity` requests are open, that is, entered and not yet exited.
  - the oldest of the last `capacity` starts is at least `window` seconds old.
- Waiting requests start in the order they entered.
- A request that raises or is cancelled inside the block still exits and frees its slot. A task cancelled while
  it waits does not start and is not counted, and the next waiter takes its turn.

With `capacity=5, window=1`, which `tests/test_ratelimit.py` asserts:

- 12 short requests at once start in groups of 5, 5 and 2, one second apart. A long burst starts 5 per second.
- 7 requests of 2.5 seconds each start 5 at once and the other 2 at 2.5 seconds, when the first ones end.
- After one request at 0 seconds, a burst at 0.95 seconds starts 4 requests at 0.95, 1 at 1.0, 4 at 1.95, 1 at
  2.0, and so on.

## Invariants

- No span of `window` seconds holds more than `capacity` starts, as `clock` measures them, and a long burst
  starts `capacity` per `window` seconds on average. [ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md) says
  why the limiter does not count fixed windows.
- At most `capacity` requests are open at once. A POST that `Twitch.request` sends again after a 5xx status or a
  connection error stays in the same slot, and a batch of up to 20 operations is one POST.
- The waiters check the limits one at a time, under an `asyncio.Lock`. A waiter cancelled after a slot opened
  passes the lock to the next one, which checks the limits again, so no request waits while nothing is ahead of
  it.
- Every GQL request passes through the `RateLimiter` in `Twitch.gql_request`. A GQL request sent another way is
  not counted.

**Dependencies.** None: the standard library only.
