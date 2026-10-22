# ADR-0006: Restart after a fatal error

**Status:** Accepted (2026-10-22)

## Context

A fatal error is an exception that leaves `Twitch._run`, other than `ReloadRequest` and `ExitRequest`. Nothing
is mined until `_run` starts again. Most of these errors come from a temporary problem on Twitch's side, and
trying again a few minutes later is enough. The app runs in the background for hours, often while nobody looks
at it. If it waits for the user to restart it, mining can stop for the rest of the day.

A Twitch outage stops every running copy of the app at the same time, and with the same fixed delay they would
all reconnect at the same moment.

Each restart begins with a full reload, the most expensive work the app does
([ADR-0002](ADR-0002-twitch-traffic-budget.md)). Some errors end every run, such as an outdated hash of a GQL
operation that each run sends. With the same delay after every error, such an error reloads once per delay: up
to 49 times an hour at the 1 minute choice and 5.9 at the default, against once an hour in a run that works
([019](../refinements/tasks/019-restart-runs-a-full-reload.md)).

## Decision

1. **A fatal error restarts the run inside the same process.** `Twitch.run` catches the exception and calls
   `Twitch._await_restart`. That method prints `Fatal error encountered:` and the traceback in the Output box,
   logs the error, calls `Twitch.shutdown()`, waits, and returns; the loop in `Twitch.run` then calls `_run`
   again. It is the same loop that restarts `_run` after a `ReloadRequest`, which `State.RESTART` raises. The
   window stays open, the tray icon stays, and the Output box keeps its lines, including the traceback. An
   `aiohttp.ContentTypeError` is first replaced by a `RequestException` with the "Unexpected content type
   returned" message, which names the likely cause. An exception in a critical task (`_watch_loop`,
   `_maintenance_task` or `Websocket._handle`) is a fatal error too: `task_wrapper` passes it to
   `Twitch.task_failed`, which requests `State.RESTART`, and that state raises it from `_run`. The run cannot
   go on without these tasks, and the same error raised in `_run` restarts the run.

2. **The first delay is a setting.** `restart_delay` holds the minutes of the wait after the first error and
   defaults to 10. It is set by "Restart after a crash after:" in the General section of the Settings tab. Its
   choices are `SettingsPanel.RESTART_DELAYS`: "Never (stay stopped)" (`0`), and 1, 5, 10, 15, 30 and 60
   minutes. A saved value that is not one of these is reset to 10 when `SettingsPanel` is created. Decision 7
   makes the later waits longer.

3. **A random jitter is added to every delay.** `_await_restart` adds `random.uniform` between 0 and
   `RESTART_JITTER` (60 seconds). After an outage, the copies of the app restart at different moments instead
   of all at once.

4. **Closing the window during the wait exits at once.** The wait is
   `asyncio.wait_for(self.gui.wait_until_closed(), ...)`, so it ends when the user closes the window, and
   `Twitch.run` leaves its loop when `gui.close_requested` is set. During the wait the tray icon is `error`,
   the Status box shows `Restarting at {time}`, the Output box shows
   `Restarting automatically at {time}...`, and the channel list is empty.

5. **Never stops on the error.** With `restart_delay` set to `0`, `_await_restart` returns `False` and
   `Twitch.run` raises the error. `main.py` prints it, shows "Terminated" and keeps the window open until the
   user closes it.

6. **The restart time includes a date when it is not today.** `_await_restart` formats the time with `%X`
   when the restart falls on today's date, and with `%x %X` otherwise. A wait that starts shortly before
   midnight ends on the next day, where a time alone would be ambiguous.

7. **The delay doubles while the error comes back within an hour.** `Twitch.run` records the start of each run
   in a `RestartDelay` ([restartdelay.md](../modules/restartdelay.md)). After a run shorter than an hour, the
   wait is the last wait doubled, at most 60 minutes and never less than the setting. After a run of an hour or
   more, it is the setting again. So an error that ends every run reloads at most once an hour after the first
   hour, as a run that works does. When the wait is longer than the setting, a line in the Output box before
   the restart time says so and gives the wait in minutes (`status.restart_longer`). The run's length is
   measured on the event loop's clock, which is `time.monotonic` in the app.

## Consequences

- A restart runs `_run` from the start: the login check (`get_auth`), which sends a GET of
  `https://www.twitch.tv` and one of `https://id.twitch.tv/oauth2/validate`, then `State.INVENTORY_FETCH`, a
  full reload ([ADR-0002](ADR-0002-twitch-traffic-budget.md)). An error that ends every run right after its
  reload causes these reloads, the one at startup included:

  | `restart_delay` | Waits in minutes | Reloads in the first hour | Reloads in each later hour, at most |
  | --- | --- | --- | --- |
  | 1 minute | 1, 2, 4, 8, 16, 32, then 60 | 6 | 1 |
  | 5 minutes | 5, 10, 20, 40, then 60 | 4 | 1 |
  | 10 minutes (default) | 10, 20, 40, then 60 | 3 | 1 |
  | 15 minutes | 15, 30, then 60 | 3 | 1 |
  | 30 minutes | 30, then 60 | 2 | 1 |
  | 60 minutes | 60 | 1 | 1 |

  For ADR-0002's example of about 100 campaigns and 1200 ACL channels, a reload sends 67 GQL requests with
  1302 operations, or 127 with 2502 when `available_drops_check` is on. So the first hour at the 1 minute
  choice sends at most 402 requests, or 762, and each later hour 67, or 127. The counts hold with any jitter,
  and leave out the failing request and the two login requests of each restart.
- An error that ends each run after an hour or more of running sets the wait back to the setting every time.
  Its restart adds one reload to the run's own hourly reload, so it costs at most 2 reloads an hour.
- An error that ends the run before any GQL request, such as a proxy error at login, doubles the wait too,
  though such a restart sends only the two login requests. After the cause is fixed, the next restart can be up
  to 61 minutes away. Closing and opening the app starts a new run at once, with the setting as the first wait.
- The Settings tab names the setting "Restart after a crash after:", the wait after the first error. The
  Output box line of decision 7 explains a longer wait when it happens.
- `Twitch.shutdown()` clears the drops, campaigns, channels, inventory, login state and `wanted_games`, so a
  restart begins from the same state as a fresh start. `shutdown` also clears `_no_campaign_printed`,
  `_no_channel_printed` and `_scan_errors_printed`, so the next run prints those messages again.
- `shutdown` also empties the channel list in the window. A row left from the old run would show a status that
  no longer changes, and would keep its old `Channel` for `get_selection()` until a `CHANNELS_FETCH` replaces
  it. A selection made before the error is lost, as it is after a fresh start.
- Only `Exception` subclasses restart the run. `ExitRequest` ends it, and `ReloadRequest` restarts it at once.
- A failed critical task restarts the run no sooner than any other fatal error, because its error leaves
  `_run` and waits the same delay. A close requested at the same time ends the app, because `EXIT` comes
  before `RESTART` ([ADR-0017](ADR-0017-state-requests.md)).

## Alternatives rejected

- **Restart the whole process.** It would close the window and lose the lines in the Output box, while the
  loop in `Twitch.run` already restarts `_run` in place.
- **No jitter.** After an outage, every copy of the app would reconnect at the same moment.
- **Setting the wait back at the first `CHANNEL_SWITCH` of a run.** An error after the switch would set it
  back on every run and keep one reload per delay: a failed watch loop, as an outdated `PlaybackAccessToken`
  hash causes, or a failed channel fetch of a stream refresh.
- **Removing the 1 and 5 minute choices.** An error that ends every run would still reload up to 5.9 times an
  hour, and one error would wait at least 10 minutes.
- **Keeping the campaigns across a restart.** The restart would no longer begin from the state of a fresh
  start, and an error in `fetch_inventory` would still need a full reload.
- **Stopping the app when a critical task fails.** A bug in such a task can repeat on every run, but so can a
  bug in `_run`, which restarts. "Never (stay stopped)" keeps the stop for a user who wants it.

## Related

- [main.md](../modules/main.md), [twitch.md](../modules/twitch.md), [settings.md](../modules/settings.md),
  [gui.md](../modules/gui.md), [constants.md](../modules/constants.md),
  [exceptions.md](../modules/exceptions.md), [restartdelay.md](../modules/restartdelay.md).
- [019](../refinements/tasks/019-restart-runs-a-full-reload.md): the reload rate of an error that ends every
  run, with a fixed delay.
- [ADR-0002](ADR-0002-twitch-traffic-budget.md) (the request budget and full reloads).
- [Logging in](../troubleshooting.md#logging-in), for the device code login that the app uses.
- [Translations for new strings](../refinements/tasks/008-translations-for-new-strings.md).
