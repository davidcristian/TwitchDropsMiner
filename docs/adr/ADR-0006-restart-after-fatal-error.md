# ADR-0006: Restart after a fatal error

**Status:** Accepted (2026-08-25)

## Context

A fatal error is an exception that leaves `Twitch._run`, other than `ReloadRequest` and `ExitRequest`. Nothing
is mined until `_run` starts again. Most of these errors come from a temporary problem on Twitch's side, and
trying again a few minutes later is enough. The app runs in the background for hours, often while nobody looks
at it. If it waits for the user to restart it, mining can stop for the rest of the day.

Two cases need more than a plain retry. A Twitch outage stops every running copy of the app at the same time,
and with the same fixed delay they would all reconnect at the same moment. A CAPTCHA denial
(`CaptchaRequired`, raised only by the password login `_AuthState._login`) needs a person to solve it, and
Twitch's message asks the user to wait 12 hours or more.

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
   `RESTART_JITTER` (60 seconds), to the CAPTCHA delay as well. After an outage, the copies of the app restart
   at different moments instead of all at once.

4. **Closing the window during the wait exits at once.** The wait is
   `asyncio.wait_for(self.gui.wait_until_closed(), ...)`, so it ends when the user closes the window, and
   `Twitch.run` leaves its loop when `gui.close_requested` is set. During the wait the tray icon is `error`,
   the Status box shows `Restarting at {time}`, and the Output box shows
   `Restarting automatically at {time}...`.

5. **Never stops on the error.** With `restart_delay` set to `0`, `_await_restart` returns `False` and
   `Twitch.run` raises the error. `main.py` prints it, or the CAPTCHA message for `CaptchaRequired`, shows
   "Terminated" and keeps the window open until the user closes it. `_await_restart` checks the setting
   before it checks for a CAPTCHA, so Never also turns off the CAPTCHA restart.

6. **A CAPTCHA denial has its own schedule.** For `CaptchaRequired` the delay is
   `min(CAPTCHA_RESTART_DELAY * 2 ** self._captcha_denials, CAPTCHA_RESTART_MAX)`: 1, 2, 4 and 8 hours, then 12
   hours for every later denial. The minutes in `restart_delay` are not used for a CAPTCHA denial. `_run`
   sets `_captcha_denials` back to 0 as soon as `get_auth()` returns, so a successful login resets the wait to
   1 hour. Retrying on the normal delay would add a failed login to the account after every delay, against
   Twitch's request to wait. The first wait is 1 hour rather than 12 in case the denial was temporary.
   No login path raises `CaptchaRequired` today: the app logs in with the device code flow `_oauth_login`, and
   nothing calls `_AuthState._login`. So this schedule, and the CAPTCHA branch in `main.py` (decision 5),
   cannot run ([010](../refinements/tasks/010-unreachable-password-login.md)).

7. **The restart time includes a date when it is not today.** `_await_restart` formats the time with `%X`
   when the restart falls on today's date, and with `%x %X` otherwise. The CAPTCHA wait can move the restart
   into the next day, where a time alone would be ambiguous.

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
- `_captcha_denials` is kept in memory only. Closing and reopening the app resets the CAPTCHA wait to 1 hour.
- Only `Exception` subclasses restart the run. `ExitRequest` ends it, and `ReloadRequest` restarts it at once.
- An exception in a critical task (`_watch_loop`, `_maintenance_task` or `Websocket._handle`) does not leave
  `_run`. `task_wrapper` calls `Twitch.close`, so the app stops without a restart
  ([013](../refinements/tasks/013-crashed-task-ends-the-app.md)).

## Alternatives rejected

- **Restart the whole process.** It would close the window and lose the lines in the Output box, while the
  loop in `Twitch.run` already restarts `_run` in place.
- **Retry a CAPTCHA denial on the normal delay.** It adds failed logins while Twitch asks for 12 hours.
- **Wait the full 12 hours after the first CAPTCHA denial.** A temporary denial would then stop mining for 12
  hours.
- **No jitter.** After an outage, every copy of the app would reconnect at the same moment.

## Related

- [main.md](../modules/main.md), [twitch.md](../modules/twitch.md), [settings.md](../modules/settings.md),
  [gui.md](../modules/gui.md), [constants.md](../modules/constants.md),
  [exceptions.md](../modules/exceptions.md).
- [ADR-0002](ADR-0002-twitch-traffic-budget.md) (the request budget and full reloads).
- [Logging in](../troubleshooting.md#logging-in), for the device code login that the app uses.
- [010](../refinements/tasks/010-unreachable-password-login.md): the password login that raises
  `CaptchaRequired` has no caller.
- [Translations for new strings](../refinements/tasks/008-translations-for-new-strings.md).
