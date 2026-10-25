# `restartdelay.py`

**Purpose.** `RestartDelay` returns the minutes that `Twitch.run` waits after a fatal error before it starts the
run again ([twitch.md](twitch.md#restart-after-a-fatal-error)). The wait doubles while the error comes back
within an hour of each start, so an error that ends every run causes a full reload at most once an hour after
the first hour ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)). The module has no I/O, so a test runs
it with a fake clock.

## Public contract

- `RestartDelay(clock)` keeps the waits of one `Twitch`. `clock` returns the current time in seconds. `Twitch`
  passes the time of the running event loop, which is `time.monotonic` in the app.
- `started()` records the time a run started. `Twitch.run` calls it before each call of `_run`, after a restart,
  an `Invalidate` press and at startup.
- `next_minutes(minutes)` returns the wait after a run ended on a fatal error. `minutes` is the `restart_delay`
  setting:
  - after a run shorter than `RESET_AFTER` (3600 seconds), the last wait doubled, at most `LONGEST` (60), and
    never less than `minutes`.
  - after a run of `RESET_AFTER` or longer, after the first error, and when no run has started, `minutes`.
- `reset()` forgets the last wait, so `next_minutes` returns `minutes` after the next error, as after the first.
  `Twitch._await_restart` calls it when a `Reload` press ends the wait, because a press starts a new run as a
  start of the app does ([ADR-0006](../adr/ADR-0006-restart-after-fatal-error.md)).

## Invariants

- From the setting of 1 minute the waits are 1, 2, 4, 8, 16, 32 and then 60 minutes, and from the default of 10
  they are 10, 20, 40 and then 60. A setting of 60 always waits 60.
- A setting changed during a series is read at the next error. A higher setting is used at once, and a lower one
  does not shorten the doubled wait.
- The clock is read only in `started` and `next_minutes`, so `Twitch.__init__` can build the object outside a
  running event loop, as the test suite does.

**Dependencies.** None: the standard library only.
