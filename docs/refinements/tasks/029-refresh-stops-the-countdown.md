# Each stream refresh stops the drop countdown

**Status:** done 2026-10-22
**Area:** twitch (state machine), gui (progress panel)
**Origin:** Found on 2026-10-18 while the docs were written, [ADR-0003](../../adr/ADR-0003-stream-refresh.md#decision)
**Verified:** 2026-10-22

At the end of `State.CHANNELS_FETCH`, `Twitch._run` in `twitch.py` takes the first channel that `can_watch`
accepts and calls `active_drop.display(countdown=False, subone=True)` for the first drop of its active
campaign. While a channel is watched, `get_active_campaign` uses the watched channel, so this is the drop
being mined. `CampaignProgress.display` in `gui.py` calls `stop_timer()` first. With `subone=True` it then
calls `_update_time(0)`, which shows the remaining time one minute lower at 0 seconds and starts no countdown.
The comment at that branch says that the watch loop subtracts this minute when the first watch request returns
a progress update. That holds when a new watch starts.

A stream refresh starts no new watch. `_maintenance_task` enters `State.CHANNELS_CLEANUP` every
`refresh_interval` minutes plus 0 to 60 seconds, and that state moves to `CHANNELS_FETCH`. When the watched
channel stays, `CHANNEL_SWITCH` does not call `watch` again, and nothing ends the watch loop's wait. So the
countdown stops in the middle of a minute and stays stopped until the next progress update:

- `minute_almost_done()` (`gui.py`) returns True while no countdown runs. The next check in `_watch_loop`
  comes 15 seconds into the next watch cycle, at most about 20 seconds after the refresh, and sends one
  `CurrentDrop` GQL query. Its response, or the estimate that `bump_minutes` adds when the response is not
  usable, shows the drop again with a new countdown. So one refresh causes at most one query.
- A PubSub `drop-progress` event that arrives before that check restarts the countdown, and no query is sent.

Without the refresh, that check sends nothing while the countdown runs with more than `ALMOST_DONE_SECONDS`
(10) left.

## How it was confirmed

A script ran the real `Twitch._run`, `_watch_loop` and `process_drops`, the real `CampaignProgress` with Tk
variables under Xvfb, and a real `DropsCampaign` with one drop at 46 of 60 minutes. Stubs replaced the login,
the websocket pool, the channel and `gql_request`, which counted `CurrentDrop` queries and returned the
drop's current minutes. A channel was watched from t=0, and a PubSub progress event came at t=1. The refresh
was `change_state(State.CHANNELS_CLEANUP)`, as `_maintenance_task` sends it. Excerpts:

```
A: no refresh, PubSub update at t=45
t= 24.9  shows '0:13:37 remaining', timer running, minute_almost_done=False
t= 34.9  shows '0:13:27 remaining', timer running, minute_almost_done=False
CurrentDrop requests in 58 s: 0

B: refresh at t=25, PubSub update at t=45
t= 24.9  shows '0:13:37 remaining', timer running, minute_almost_done=False
t= 25.2  shows '0:13:00 remaining', timer stopped, minute_almost_done=True
t= 34.9  shows '0:13:00 remaining', timer stopped, minute_almost_done=True
t= 35.0  CurrentDrop sent
t= 35.3  shows '0:14:00 remaining', timer running, minute_almost_done=False
CurrentDrop requests in 58 s: 1

C: refresh at t=25, PubSub update at t=30
t= 25.2  shows '0:13:00 remaining', timer stopped, minute_almost_done=True
t= 34.9  shows '0:12:56 remaining', timer running, minute_almost_done=False
CurrentDrop requests in 58 s: 0
```

The real `_maintenance_task` on a fake clock counted the refreshes before the hourly reload, over 3000 hours
for each setting: 10 or 11 (mean 10.3) at the default of 5 minutes, and 36 to 44 (mean 39.5) at 1 minute. Each
wait is at least 60 seconds at 1 minute, so the schedule allows at most 59.

## Effect

While a drop is mined, each refresh sets both remaining times in the progress panel, for the drop and for the
campaign, to the whole minute below and stops them: "0:13:37" becomes "0:13:00". They stay there until the next
progress update, at most about 20 seconds later. When that update is the `CurrentDrop` response with unchanged
minutes, the times go back up to "0:14:00" and count down from there. This happens about 10 times an hour at
the default and about 40 times an hour at 1 minute. The drop's minutes do not change; only the display does.

Twitch requests: at most one `CurrentDrop` per refresh. That is at most 11 an hour at the default of 5 minutes,
and about 40 an hour at 1 minute (59 at most). A refresh itself sends 0 to 3 `GameDirectory` requests in the
common case ([ADR-0003](../../adr/ADR-0003-stream-refresh.md#consequences), which counts this query too).

## How it came about

The pre-display is from the original project, "More accurate active drop pre-display" (2022-01-16), found with
`git log -S'subone=True'`. Then `CampaignProgress.display` stopped the countdown only on the countdown branch.
The upstream commit of 2022-01-30 that fixed a missed claim when two drops finished at the same time moved
`stop_timer()` before the branches, so the `subone` call stops the countdown too. In the original project
`CHANNELS_FETCH` runs after each reload, where `restart_watching` in `GAMES_UPDATE` stops the countdown anyway,
and at the start and end times of campaigns and drops. This project added the stream refresh in "Implement auto
fetch" (2026-08-03), which runs `CHANNELS_FETCH` every few minutes while the same channel is watched.

## What a fix involves

The pre-display is needed only when a new watch starts, so a fix skips it when the refresh keeps the watched
channel. On a copy, the pre-display loop of `State.CHANNELS_FETCH` in `Twitch._run` was skipped while
`watching_channel` has a value. Scenario B then showed '0:13:36 remaining', timer running, at t=25.2, and sent
no `CurrentDrop` in 58 s. By the code, that condition also skips the pre-display after a reload that keeps the
channel, where `restart_watching` has already stopped the countdown. A fix keeps it there, for example with a
flag that `GAMES_UPDATE` sets.

The fix sends no new request and removes up to one `CurrentDrop` per refresh.

## History

- 2026-10-18: Opened. A review of ADR-0003 named the stopped countdown and its `CurrentDrop` query, which
  ADR-0003 records without a task. A run of the real `_run`, `_watch_loop` and `CampaignProgress` with stubs
  showed the stop and counted the queries.
- 2026-10-22: Closed. `CHANNELS_FETCH` runs the pre-display only while no channel is watched after the relink,
  or when `GAMES_UPDATE` came before it, which a local flag in `_run` records. A time trigger takes the refresh
  path too, so a drop it starts or ends shows at the next progress update. Two tests in
  `tests/test_twitch_run.py` run the real `_run` with a fake progress panel: a refresh leaves the countdown
  running, and a reload still shows the drop of the new inventory. The fix sends no new request and removes up
  to one `CurrentDrop` per refresh.
