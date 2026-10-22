# ADR-0003: The stream refresh

**Status:** Accepted (2026-08-03)

## Context

The app learns that a tracked channel went live from a PubSub websocket event, handled by
`process_stream_state` in `twitch.py`. Only channels on the tracked list get these events. A campaign without an
ACL (a list of channels whose streams count toward its drops) gets its channels from one `GameDirectory` query
in `get_live_streams`. That query returns the channels that are live at that moment.

`get_live_streams` runs only in `State.CHANNELS_FETCH`. Without a periodic check, that state runs on three
events: after a full reload, which comes at least once an hour
([ADR-0002](ADR-0002-twitch-traffic-budget.md)), at the start and end times of campaigns and drops, and when
the list of detected installed games changes. A channel
that goes live after the query is found at the next of these, up to an hour later. By then too little of the
stream can be left to finish a drop. The case that showed it was a Warframe developer stream that the app
found too late.

A shorter full reload is not an option, because a reload is the most expensive work the app does
(ADR-0002).

## Decision

1. **A periodic stream refresh re-enters the channel fetch, never the reload.** When the refresh time comes,
   `_maintenance_task` changes the state to `State.CHANNELS_CLEANUP`. That state removes tracked channels that
   are not from an ACL and are offline or no longer stream a wanted game, then moves to
   `State.CHANNELS_FETCH`, or to `State.IDLE` when no game is wanted. `State.CHANNELS_FETCH` queries the
   directory again for each wanted game without an ACL. The refresh never enters `State.INVENTORY_FETCH`, so
   it costs a few requests instead of a reload.

2. **The interval is the `refresh_interval` setting, in minutes, 5 by default.** The Settings tab shows it as
   "Check for new streams every:" with the choices 1, 2, 5, 10, 15 and 30 min, and "Never (hourly reload
   only)", which is stored as 0. `SettingsPanel` resets a value that is not one of these choices to 5. With the
   default, a refresh comes at most 6 minutes after the previous one, against up to an hour without it.

3. **Each refresh time gets a random extra delay of 0 to 60 seconds.** `_maintenance_task` adds
   `random.uniform(0, REFRESH_JITTER.total_seconds())` to every refresh time, and `REFRESH_JITTER` in
   `constants.py` is 60 seconds. The requests are then not sent on a fixed schedule. The waits for the hourly
   reload and for a campaign time trigger get no extra delay.

4. **The hourly reload and the campaign time triggers keep their schedule.** `_maintenance_task` schedules the
   refresh only when it comes before the hourly reload. A start or end time of a campaign or a drop
   (`_mnt_triggers`) that comes before the refresh replaces the refresh for that wait, and leads to the same
   `State.CHANNELS_CLEANUP`. A time trigger is taken from the queue only when it is the earliest one, so a
   refresh never skips one.

5. **A refresh that finds nothing new keeps the channel list, its selection and the status lines.**
   `State.CHANNELS_FETCH` rebuilds the channel list in the GUI only when the set of channels changed, and then
   restores the selection. The "No available channels to watch" message prints once until a channel is
   watched again (`_no_channel_printed`), and "No active campaigns to mine drops for." once until a game is
   wanted again (`_no_campaign_printed`). `State.CHANNEL_SWITCH` does not call `watch` again for the channel
   that is already watched. Without these, every refresh would redraw the table, drop the selection and print
   the same status lines again. One change remains. While a drop is mined, `State.CHANNELS_FETCH` shows it
   again with `subone=True`, which stops the countdown at a whole minute until the next progress update.

6. **The change is the smallest one that fixes the common case.** Two other causes of late discovery are known
   and stay open as refinement tasks (see Related).

## Consequences

The GQL requests of one refresh:

- `State.CHANNELS_CLEANUP` sends none.
- `State.CHANNELS_FETCH` sends one `GameDirectory` request per wanted game with a campaign that has no ACL,
  typically 0 to 3.
- `acl_channels.difference_update(new_channels)` drops the ACL channels already tracked. When every ACL channel
  of the wanted campaigns is on the tracked list, `bulk_check_online` receives an empty set and sends nothing.
- The tracked list holds at most `MAX_CHANNELS` channels, 199 from the PubSub topic limits in `constants.py`.
  When the wanted campaigns list more ACL channels than that, the ones left off the list are checked again on
  every refresh. That costs one `GetStreamInfo` request per 20 of them, plus one `AvailableDrops` request per
  20 online ones when `available_drops_check` is on.
- While a drop is mined, the countdown that the channel fetch stops makes `_watch_loop` send one `CurrentDrop`
  request at its next check (`minute_almost_done`), unless a PubSub progress update restarts it first.

So in the common case a refresh sends one request per wanted game without an ACL, 0 to 3 requests, plus at
most one `CurrentDrop` while a drop is mined. At the default interval, at most 11 refreshes run between two
hourly reloads, because each one comes at least 5 minutes after the previous wait began.

- The check of ACL channels left off the list also finds one that went live since the last refresh. If it
  streams a wanted game, the channel fetch sorts it ahead of every offline channel.
- `WebsocketPool.add_topics` skips topics it already has, so a refresh that keeps the same channels sends no
  websocket message.
- `_maintenance_task` reads `refresh_interval` each time it schedules a wait, so a new value applies from the
  next wait.
- With the setting at "Never (hourly reload only)", the channel fetch runs only on the three events under
  Context.

## Alternatives rejected

- **A shorter or user-set full reload.** It repeats the most expensive work the app does (ADR-0002) to find
  streams that a channel fetch finds for a few requests.
- **Fixing every known cause of late discovery at once.** The refresh fixes the common case. The other two
  causes are in the channel ordering and in the online check after a stream-up event, and stay open as tasks.

## Related

- [ADR-0002](ADR-0002-twitch-traffic-budget.md): the traffic budget and the cost of a full reload.
- [twitch.md](../modules/twitch.md) (`_maintenance_task` and the `State` machine),
  [settings.md](../modules/settings.md), [gui.md](../modules/gui.md), [constants.md](../modules/constants.md),
  [websocket.md](../modules/websocket.md).
- [001-offline-acl-channels-trimmed-first.md](../refinements/tasks/001-offline-acl-channels-trimmed-first.md):
  offline ACL channels sort last in `State.CHANNELS_FETCH`, so they are the first ones removed at
  `MAX_CHANNELS` and get no PubSub events.
- [002-online-delay-single-try.md](../refinements/tasks/002-online-delay-single-try.md): after a stream-up
  event, the app waits `ONLINE_DELAY` (120 seconds) and checks the stream once.
