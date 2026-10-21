# A crashed background task ends the app instead of restarting it

**Status:** open
**Area:** utils (`task_wrapper`), twitch, websocket, main
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#invariants)
**Verified:** 2026-10-18

`task_wrapper(critical=True)` in `utils.py` wraps three tasks: `Twitch._watch_loop`, `Twitch._maintenance_task`
and `Websocket._handle` (`websocket.py`). When one of them raises anything other than `ExitRequest` or
`ReloadRequest`, the wrapper logs `Exception in <name> task` with the traceback. It then finds the `Twitch`
object, as the first argument or as its `_twitch` attribute, calls `Twitch.close()`, which is
`change_state(State.EXIT)`, and raises the exception again inside the task.

`_run` handles `State.EXIT` by returning, so `Twitch.run` leaves its loop as after a normal close. The
exception never leaves `_run`, so `Twitch._await_restart` is not called and the restart of
[ADR-0006](../../adr/ADR-0006-restart-after-fatal-error.md) does not apply, whatever `restart_delay` is. An
exception raised inside `_run`, even the same one, restarts the run after the delay.

## What can end each task

- **`_watch_loop`:** `Channel.send_watch` calls `Stream.get_stream_url`, whose `PlaybackAccessToken` query
  raises `GQLException` for an error message that `gql_request` does not retry. `get_stream_url` raises
  `TypeError` when the response's `streamPlaybackAccessToken` is null, and raises `aiohttp.InvalidURL` or
  `ValueError` again after it prints a playlist it cannot read. The `CurrentDrop` check catches only
  `GQLException`, so a null `currentUser` in its response raises `TypeError`. `Twitch.request` raises
  `aiohttp.ClientConnectorCertificateError` without a retry.
- **`Websocket._handle`:** its reconnect loop catches every `Exception` and reconnects, so only the lines
  outside it can end the task: `wait_until_login`, `set_status` and the `get_session` call at the start of
  `_backoff_connect`.
- **`_maintenance_task`:** it computes times and calls `change_state`. It sends no request.

So a change in a Twitch response that the watch loop reads ends the app, while the same change in a response
that `_run` reads restarts it.

## How it was confirmed

A script ran the real `Twitch.run` and `Twitch._run` with stubs for the GUI, the websocket pool, the login and
the requests, with `restart_delay` at 10 and `_await_restart` replaced by a stub that records its calls. The
real `_watch_loop` started, and once `_run` waited in `IDLE` the script set a watched channel whose
`send_watch` raises `GQLException("PlaybackAccessToken failed")`:

```
log ERROR: Exception in _watch_loop task
exceptions.GQLException: PlaybackAccessToken failed
INVENTORY_FETCH > GAMES_UPDATE > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE > <watched channel set>
  > EXIT | Twitch.run returned | _await_restart calls: [] | watch task done: True
```

As a control, the same stubs with `fetch_inventory` raising `GQLException("Inventory failed")` inside `_run`
called `_await_restart` once, with that exception.

## Effect

`main()` in `main.py` gets no exception from `client.run()`, so `exit_status` stays 0. It prints "Exiting...",
runs `shutdown()`, and, since the user did not close the window, sets the tray icon to `error`, prints
"Application Terminated. Close the window to exit the application.", sets the status to "Terminated" and
rings the bell with `grab_attention(sound=True)`. The Output box shows `ERROR: Exception in _watch_loop task`
and the traceback above these lines, but not "Fatal error encountered:" or a restart time. Mining stops until
the user starts the app again. A user who set "Restart after a crash after" to any delay sees the app stop on
an error it would restart from anywhere else, and the process exits with code 0, which
[main.md](../../modules/main.md#exit-codes) lists for this case.

## How it came about

The original project added `critical=True` in "Critical tasks now cause the app to exit, instead of letting it
continue with broken functionality" (2024-07-16, found with `git log -S'critical: bool' -- utils.py`). Before
it, a crashed watch loop left the app open and mining nothing. At that time every fatal error ended the app,
so ending it after a crashed task matched the rest, and it was deliberate.

This project added the restart in "Restart automatically after a fatal error" (2026-08-25). That commit
changed `twitch.py`, `main.py`, `gui.py`, `settings.py`, `constants.py`, `translate.py` and `README.md`, and
not `utils.py`, and its message does not name the critical tasks. The history shows no decision to keep them
out of the restart. ADR-0006 now lists the behavior among its consequences, with a link to this task.

A bug in a critical task may repeat on every run, which is a reason to stop. But the same holds for a bug in
`_run`, and ADR-0006 restarts those after the delay and its jitter. Its "Never (stay stopped)" choice keeps
the stop for a user who wants it.

## What a fix involves

Send a critical task's exception to the restart path instead of `State.EXIT`. For example, the wrapper stores
the exception on the `Twitch` object and wakes `_run`, and `_run` raises it, so `Twitch.run` passes it to
`_await_restart` like any other fatal error. `close()` stays the path for a close by the user.
`_await_restart` already calls `shutdown()`, which cancels `_watch_loop` and `_maintenance_task`. With
`restart_delay` at 0 the error then reaches `main()`, which prints "Fatal error encountered:" and exits with
code 1, as main.md's exit code table says for other errors. ADR-0006 and the invariant in twitch.md change in
the same commit.

Twitch requests: each restart starts `_run` again, which runs a full reload, so an error that repeats in the
watch loop costs one reload per restart delay ([019](019-restart-runs-a-full-reload.md)). Today it costs
nothing, because the app stops.

## History

- 2026-10-18: Opened. While the invariants of twitch.md were written, `task_wrapper` was found to set
  `State.EXIT`. A run of the real `Twitch.run` with a watch loop that raises confirmed that `_await_restart` is
  not called.
- 2026-10-21: A null `currentUser` in the `CurrentDrop` response no longer ends `_watch_loop`. It counts as no
  drop data, and the loop adds an estimated minute ([twitch.md](../../modules/twitch.md#watch-loop)).
- 2026-10-22: A null token in the `PlaybackAccessToken` response no longer ends `_watch_loop`. The cycle fails
  and an online check starts ([channel.md](../../modules/channel.md#a-null-playback-token)).
