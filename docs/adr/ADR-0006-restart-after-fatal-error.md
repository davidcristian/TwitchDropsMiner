# ADR-0006: Restart after a fatal error

**Status:** Accepted (2026-08-25)

## Context

A fatal error is an exception that leaves `Twitch._run`, other than `ReloadRequest` and `ExitRequest`. Nothing
is mined until `_run` starts again. Most of these errors come from a temporary problem on Twitch's side, and
trying again a few minutes later is enough. The app runs in the background for hours, often while nobody looks
at it. If it waits for the user to restart it, mining can stop for the rest of the day.

A Twitch outage stops every running copy of the app at the same time, and with the same fixed delay they would
all reconnect at the same moment.

## Decision

1. **A fatal error restarts the run inside the same process.** `Twitch.run` catches the exception and calls
   `Twitch._await_restart`. That method prints `Fatal error encountered:` and the traceback in the Output box,
   logs the error, calls `Twitch.shutdown()`, waits, and returns; the loop in `Twitch.run` then calls `_run`
   again. It is the same loop that restarts `_run` after a `ReloadRequest`, which `State.RESTART` raises. The
   window stays open, the tray icon stays, and the Output box keeps its lines, including the traceback. An
   `aiohttp.ContentTypeError` is first replaced by a `RequestException` with the "Unexpected content type
   returned" message, which names the likely cause.

2. **The delay is a setting.** `restart_delay` holds minutes and defaults to 10. It is set by "Restart after a
   crash after:" in the General section of the Settings tab. Its choices are `SettingsPanel.RESTART_DELAYS`:
   "Never (stay stopped)" (`0`), and 1, 5, 10, 15, 30 and 60 minutes. A saved value that is not one of these
   is reset to 10 when `SettingsPanel` is created.

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

## Consequences

- A restart runs `_run` from the start: the login check (`get_auth`), then `State.INVENTORY_FETCH`, which is
  a full reload ([ADR-0002](ADR-0002-twitch-traffic-budget.md)). An error that repeats on every run costs up
  to one full reload per restart ([019](../refinements/tasks/019-restart-runs-a-full-reload.md)). Restarts
  are at least the delay apart: 10 minutes at the default, and 1 minute at the `1 min` choice.
- `Twitch.shutdown()` clears the drops, channels, inventory, login state and `wanted_games`, so a restart
  begins from the same state as a fresh start, except for `_campaigns`. That dictionary is never cleared and
  keeps every campaign fetched since the app started
  ([027](../refinements/tasks/027-campaigns-never-cleared.md)). `shutdown` also clears `_no_channel_printed`
  and `_scan_errors_printed`, so the next run prints those messages again.
- `shutdown` also empties the channel list in the window. A row left from the old run would show a status that
  no longer changes, and would keep its old `Channel` for `get_selection()` until a `CHANNELS_FETCH` replaces
  it. A selection made before the error is lost, as it is after a fresh start.
- Only `Exception` subclasses restart the run. `ExitRequest` ends it, and `ReloadRequest` restarts it at once.
- An exception in a critical task (`_watch_loop`, `_maintenance_task` or `Websocket._handle`) does not leave
  `_run`. `task_wrapper` calls `Twitch.close`, so the app stops without a restart
  ([013](../refinements/tasks/013-crashed-task-ends-the-app.md)).

## Alternatives rejected

- **Restart the whole process.** It would close the window and lose the lines in the Output box, while the
  loop in `Twitch.run` already restarts `_run` in place.
- **No jitter.** After an outage, every copy of the app would reconnect at the same moment.

## Related

- [main.md](../modules/main.md), [twitch.md](../modules/twitch.md), [settings.md](../modules/settings.md),
  [gui.md](../modules/gui.md), [constants.md](../modules/constants.md),
  [exceptions.md](../modules/exceptions.md).
- [ADR-0002](ADR-0002-twitch-traffic-budget.md) (the request budget and full reloads).
- [Logging in](../troubleshooting.md#logging-in), for the device code login that the app uses.
- [Translations for new strings](../refinements/tasks/008-translations-for-new-strings.md).
