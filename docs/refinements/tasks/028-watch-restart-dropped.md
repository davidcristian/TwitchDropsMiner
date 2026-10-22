# A watch restart in the first 15 seconds of a cycle has no effect

**Status:** done 2026-10-22
**Area:** twitch (watch loop)
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#watch-loop)
**Verified:** 2026-10-22

`Twitch.restart_watching` in `twitch.py` stops the minute countdown with `gui.progress.stop_timer()` and sets
the event `_watching_restart`, so that the watch loop sends its next watch request at once. One cycle of
`Twitch._watch_loop`, with `WATCH_INTERVAL` at 20 seconds:

1. It notes the time in `last_sent` and awaits `channel.send_watch()`: a playlist GET and one HEAD request per
   stream chunk, sent to Twitch's video servers.
2. It awaits `asyncio.sleep(15 - elapsed)`, which the event cannot end.
3. When `gui.progress.minute_almost_done()` is True, it awaits one `CurrentDrop` GQL query.
4. It awaits `_watch_sleep(20 - elapsed)`. `_watch_sleep` first clears `_watching_restart` and then waits on
   it with a timeout.

So a call during steps 1 to 3, the first 15 seconds after `last_sent` plus the time of a `CurrentDrop` query,
is cleared in step 4 and has no effect. Only a call during step 4, the last 5 seconds, ends the wait at once.

Two places call `restart_watching`:

- `Twitch.process_drops`, after it claims a drop whose campaign can continue on the watched channel. It first
  waits 4 seconds and sends `CurrentDrop` up to 8 times, 2 seconds apart, until Twitch reports another drop.
  The code comment says that the next drop can then be started by sending the watch request again.
- The `State.GAMES_UPDATE` branch of `Twitch._run`, after it computes `wanted_games`. That state runs after
  each reload and after `detect_games` finds a changed list of installed games.

Neither is timed to the watch cycle, so about three quarters of the calls fall in steps 1 to 3.

## How it was confirmed

A script ran the real `_watch_loop` with a stub channel whose `send_watch` records the time, and with
`minute_almost_done` returning False. It called the real `restart_watching` 5, 14 and 17 seconds after a
watch request and printed when the next request went out:

```
restart_watching() 17.0 s after a watch request: next request 17.0 s after it
restart_watching()  5.0 s after a watch request: next request 19.8 s after it
restart_watching() 14.0 s after a watch request: next request 19.8 s after it
```

The calls at 5 and 14 seconds changed nothing: the next request went out on the normal 20 second schedule.

## Effect

A call that has no effect delays the next watch request by the rest of the cycle: up to 20 seconds after the
call, and 12.5 seconds on average for a call in the first 15 seconds. After a drop claim, progress on the next
drop starts that much later than the comment in `process_drops` describes. The effect is small: at most 20
seconds per call.

`stop_timer` runs on every call, so the minute countdown stays stopped until the next progress update. While it
is stopped, `minute_almost_done` is True, and step 3 sends its `CurrentDrop` query, as in any cycle with a
stopped countdown.

## How it came about

These parts of the loop come from the original project, found with `git log -S`. "Redesign the watch loop with
awaitable channel value" (2022-01-11) added the clear before the wait. The wait then followed the watch request
directly, so only a call during the request had no effect. "Reimplement the old mining method" (2025-08-17)
added the plain `asyncio.sleep(20)` before the wait, with `WATCH_INTERVAL` at 59 seconds, so about a third of
the calls had no effect. "Change the mining method to playlist HEAD requests" (2026-10-09) set the sleep to
15 seconds and `WATCH_INTERVAL` to 20, so three quarters do now.

## What a fix involves

Keep a call made during the cycle. One way: `_watch_sleep` clears the event after its wait ends, not before,
so a call during steps 1 to 3 ends the wait as soon as step 4 starts. The next request then goes out about
15 seconds after the last one instead of 20. To send it at once, the wait in step 2 also ends on the event.

Twitch requests: a call that takes effect starts the next cycle early, which adds at most one cycle per call.
That is one playlist GET and its HEAD requests to the video servers, which are not GQL, and at most one
`CurrentDrop` GQL query ([ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md)). Calls come only after a
claim and from `GAMES_UPDATE`.

## History

- 2026-10-18: Opened. While the watch loop in twitch.md was written, `_watch_sleep` was found to clear the
  event first. A run of the real `_watch_loop` timed the next request after calls at three points of a cycle.
- 2026-10-22: Closed. `_watch_loop` clears `_watching_restart` as it sends each watch request, and
  `_watch_sleep` no longer clears it. A call during steps 1 to 3 ends the step 4 wait as soon as it starts,
  and a call before a request has no further effect, where clearing after the wait would have shortened the
  next cycle too. The step 2 wait still does not end on the event: that option sends more requests. A call
  adds at most one cycle. The tests in `tests/test_twitch_watch.py` time the real `_watch_loop` on a fast
  clock, with calls 5, 14 and 17 seconds into a cycle and one before it.
