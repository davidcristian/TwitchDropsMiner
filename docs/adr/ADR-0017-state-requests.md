# ADR-0017: Requests for the next state

**Status:** Accepted (2026-10-22)

## Context

`Twitch._run` handles one `State` per pass and then waits for the next `change_state` call. Three handlers
await requests to Twitch: `INVENTORY_FETCH`, `GAMES_UPDATE` and `CHANNELS_FETCH`. The GUI and the background
tasks run on the same event loop, so a button press or a request from a task arrives while one of these
handlers awaits. `change_state` stored one value, and the handler's last call, which sets its next state,
replaced the request. A `Reload` press during a fetch then ran no reload, and an `Invalidate` press started no
new run. An hourly reload that `_maintenance_task` requested during the channel fetch of a stream refresh was
lost, and no maintenance task was left to request the next one.

## Decision

1. **Of the states requested during one pass of `_run`, `change_state` keeps the first in `STATE_ORDER`**, a
   tuple in `twitch/`: `EXIT`, `RESTART`, `INVENTORY_FETCH`, `GAMES_UPDATE`, `CHANNELS_CLEANUP`,
   `CHANNELS_FETCH`, `CHANNEL_SWITCH`, `IDLE`. The handler's own next state is one of these requests. `_run`
   clears the `_state_change` event as it starts each pass, so a set event marks a request of the current
   pass. `EXIT` and `RESTART` end the run, so they come first. A reload goes through the other states in this
   order, so it also runs a later state that a request names: a `Switch` press during a reload is handled by
   the reload's own `CHANNEL_SWITCH`. A request for an earlier state starts again from that state: a `Reload`
   press during a channel fetch runs a reload after it.
2. **A reload requested while `INVENTORY_FETCH` runs is merged into it.** This sends the fewest requests. The
   status line shows the running reload, and its `GAMES_UPDATE` reads the Priority and Exclude lists after the
   press, so it applies a list change made before the press. A drop claim and its reward notification both
   request a reload, so the second request can come while the reload of the first runs.
3. **After `EXIT` the state no longer changes,** so a late request cannot restart an app that is closing. A
   new run starts with `INVENTORY_FETCH`, and of the requests made before it keeps only `EXIT`.
4. **A reload keeps the selection in the channel list.** The full cleanup of a reload deletes every row, and
   with it the selected one. `CHANNELS_CLEANUP` stores the ID of a selected channel that it removes, and
   `CHANNELS_FETCH` selects that channel again when the new list has it. `CHANNEL_SWITCH` watches the
   selected channel whenever `can_watch` accepts it, so a `Switch` press during a reload watches the chosen
   channel after it while that channel can still be watched. A stream refresh already keeps the selection
   ([ADR-0003](ADR-0003-stream-refresh.md)), and a reload keeps it in the same way.

## Consequences

- A kept request costs what its state costs. A `Reload` press costs the one full reload that the user asked
  for, and the hourly reload and the stream refresh of `_maintenance_task` run on the schedule that
  [ADR-0002](ADR-0002-twitch-traffic-budget.md) and [ADR-0003](ADR-0003-stream-refresh.md) count. A reward
  notification that comes during `GAMES_UPDATE` or a channel fetch runs its reload after it, as ADR-0002
  counts for every such notification.
- A merged reload shows the campaign data of its own `Inventory` and `Campaigns` queries, which can be older
  than the press. A request that comes after `INVENTORY_FETCH` ends, during the rest of the reload, runs a new
  reload.
- A selected channel stays watched through the hourly reload and every other reload, as it does through a
  stream refresh, until the user selects another channel or it can no longer be watched. A restart after a
  fatal error still empties the list and its selection ([ADR-0006](ADR-0006-restart-after-fatal-error.md)).
  Keeping the selection sends no request.

## Alternatives rejected

- **The requested state runs next.** A `Switch` press during `INVENTORY_FETCH` would skip the rest of the
  reload: `GAMES_UPDATE`, the cleanup and the channel fetch.
- **A second reload after the running one.** It repeats the most expensive work the app does for a press that
  the running reload already serves.
- **Keeping only the selection of a `Switch` press during a reload.** A selection already decides every
  `CHANNEL_SWITCH`, so a reload that drops a selection made before it would switch away from a channel the
  user chose.

## Related

- [twitch.md](../modules/twitch.md), [ARCHITECTURE.md](../ARCHITECTURE.md#the-state-machine),
  [gui.md](../modules/gui.md).
- [ADR-0002](ADR-0002-twitch-traffic-budget.md) (the events that run a full reload) and
  [ADR-0003](ADR-0003-stream-refresh.md) (the stream refresh).
- [012](../refinements/tasks/012-button-requests-lost-during-a-fetch.md): the requests that were replaced.
  [074](../refinements/tasks/074-reload-removes-the-channel-selection.md): the selection that a reload removed.
