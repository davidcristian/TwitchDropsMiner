# A button press during a fetch is replaced by the next state

**Status:** open
**Area:** twitch (state machine), gui
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md)
**Verified:** 2026-10-18

`Twitch.change_state` in `twitch.py` stores one value in `_state` and sets the event that `_run` waits on.
Three handlers in `Twitch._run` await requests and then end with `change_state(<next state>)`:

| Handler | What it awaits | Last call |
| --- | --- | --- |
| `State.INVENTORY_FETCH` | `fetch_inventory` (its GQL queries and the campaign images), `detect_games` (a folder scan in a thread) | `change_state(State.GAMES_UPDATE)` |
| `State.GAMES_UPDATE` | one `TimedDrop.claim` per drop that can be claimed; nothing when there is none | `change_state(State.CHANNELS_CLEANUP)` |
| `State.CHANNELS_FETCH` | `bulk_check_online` for the untracked ACL channels, one `get_live_streams` per wanted game with a campaign without an ACL | `change_state(State.CHANNEL_SWITCH)` |

The GUI runs on the same event loop, so a button press is handled only while `_run` awaits. A press during
one of these awaits stores its state, and the handler's last call then replaces it. `change_state` keeps only
`State.EXIT`: once `_state` is `EXIT`, it no longer changes. The other handlers do not await, so no press can
arrive during them.

## Each button

**Reload** (Settings tab, `State.INVENTORY_FETCH`):

- During `INVENTORY_FETCH`: replaced, while a reload already runs. That reload may have sent its `Inventory`
  and `Campaigns` queries before the press, so it shows campaign data from before the press.
- During `GAMES_UPDATE`: replaced, and no reload runs. The status line never shows "Fetching inventory...".
  This `GAMES_UPDATE` still reads the Priority and Exclude lists after its claims, so a list change made before
  the press is applied.
- During `CHANNELS_FETCH`: replaced, and no reload runs. A change to the Priority list, the Exclude list or the
  Priority mode stays unapplied until the next reload, up to an hour later.
  [troubleshooting.md](../../troubleshooting.md#nothing-is-mined) asks the user to press Reload to apply such
  a change at once, and this press has no effect. A second press, after the fetch, works.

**Switch** (channel list, `State.CHANNEL_SWITCH`, enabled while a channel is selected):

- During `INVENTORY_FETCH` or `GAMES_UPDATE`: replaced. `CHANNEL_SWITCH` still runs at the end of the chain,
  but `GAMES_UPDATE` sets `full_cleanup`, and `CHANNELS_CLEANUP` then removes every channel. `Channel.remove`
  deletes the channel's row from the list, so the selection is gone. `CHANNEL_SWITCH` picks a channel by
  priority, and the channel the user chose is not watched.
- During `CHANNELS_FETCH`: kept in effect, because the handler's next state is `CHANNEL_SWITCH`. The handler
  rebuilds the list only when the set of channels changed, and then selects the chosen channel again if it is
  still tracked.

**Invalidate** (Help tab, `State.RESTART`): `HelpTab._invalidate_token` in `gui.py` awaits `get_auth` and a
POST to `https://id.twitch.tv/oauth2/revoke`. On a 200 response it calls `invalidate(delete_cookies=True)`, which
removes the token and `cookies.jar`. Then it calls `change_state(State.RESTART)`, which any of the three
handlers can replace:

- With the token removed, no `ReloadRequest` is raised and `shutdown` does not run. The next `gql_request`
  calls `get_auth`, which finds no `auth-token` cookie and starts `_oauth_login`, so the Login Form asks for a
  new code in the middle of the running state. After the login, the run goes on with the data it had. `_run`
  subscribed the `User` topics `Drops` and `Notifications` with the old user ID, and they stay until `_run`
  starts again. When the user logged in with another account, the app listens on the first account's topics.
- With a revoke response other than 200, the token stays, the Output box shows "Failed to invalidate the auth
  token", and nothing else happens.

## The same replacement for requests from tasks

The same calls from tasks are replaced the same way:

- `_maintenance_task` enters `CHANNELS_CLEANUP` for a stream refresh or a time trigger, and `INVENTORY_FETCH`
  for the hourly reload, after which the task ends. Only `fetch_inventory` starts a new one. A refresh can
  start up to just before the hour, so the hourly request can arrive while that refresh's `CHANNELS_FETCH`
  awaits its queries. Then no reload runs and no maintenance task is left. No stream refresh, time trigger or
  hourly reload runs until something else enters `INVENTORY_FETCH`: a claim whose campaign cannot continue on
  the watched channel, a reward notification, the Reload button or a restart.
- `process_drops` and `process_notifications` (`INVENTORY_FETCH` after a claim or a reward notification),
  `on_channel_update` and `DropsCampaign.bump_minutes` (`CHANNEL_SWITCH`), and `detect_games` from the
  Rescan button (`GAMES_UPDATE`). A Rescan replaced during `CHANNELS_FETCH` stores the detected games in the
  settings and shows them, but `wanted_games` stays the same until the next reload. A second Rescan does not
  help, because `detect_games` enters `GAMES_UPDATE` only when the list differs from the stored one.

## How it was confirmed

A script ran the real `Twitch._run` with stubs for the GUI, the websocket pool, the login and the requests,
and with one campaign for a wanted game without an ACL. One stub awaited 0.2 seconds in the chosen handler, and
the script called `change_state` with a button's state during that await. The states `_run` handled, with
`...` for `INVENTORY_FETCH > GAMES_UPDATE > CHANNELS_CLEANUP` before the press:

```
INVENTORY_FETCH > <press Reload>     > GAMES_UPDATE > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
INVENTORY_FETCH > <press Switch>     > GAMES_UPDATE > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
INVENTORY_FETCH > <press Invalidate> > GAMES_UPDATE > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
INVENTORY_FETCH > GAMES_UPDATE > <press Reload>     > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
INVENTORY_FETCH > GAMES_UPDATE > <press Switch>     > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
INVENTORY_FETCH > GAMES_UPDATE > <press Invalidate> > CHANNELS_CLEANUP > CHANNELS_FETCH > CHANNEL_SWITCH > IDLE
... > CHANNELS_FETCH > <press Reload>     > CHANNEL_SWITCH > IDLE
... > CHANNELS_FETCH > <press Switch>     > CHANNEL_SWITCH > IDLE
... > CHANNELS_FETCH > <press Invalidate> > CHANNEL_SWITCH > IDLE
EXIT pressed during any of the three:   <press> > EXIT, and _run returned
```

`RESTART` never ran, and `fetch_inventory` ran once in each case with a Reload press. As a control, the same
presses while `_run` waited in `IDLE` ran `INVENTORY_FETCH` (a second `fetch_inventory`), `CHANNEL_SWITCH`,
and `RESTART`, which raised `ReloadRequest`. The stubs held no channel, so the loss of the selection comes
from reading `CHANNELS_CLEANUP` and `Channel.remove`.

## How it came about

The single `_state` value is from the original project. Its "Move asyncio loop handling to main.py"
(2022-01-17) added the check that keeps `State.EXIT`, found with `git log -S` on the comment in
`change_state`. No other state got such a check.

## What a fix involves

`change_state` or the handlers stop discarding a state that arrived during a handler. One way: the handler
moves on to its next state only when no other state was requested meanwhile. Otherwise the requested state
runs next, and of several requests `EXIT` comes first, then `RESTART`, then `INVENTORY_FETCH`. A `Reload`
press during a reload can be merged with the running one, or run after it. A second run costs a second full
reload, so the commit states which one it does and why.

Honoring the presses adds no periodic request: each kept `Reload` press costs the one full reload the user
asked for ([ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md)). Keeping the maintenance task's request
restores the hourly reload and the stream refresh that the schedule in
[ADR-0003](../../adr/ADR-0003-stream-refresh.md) already counts. The commit states these counts, as
[AGENTS.md](../../../AGENTS.md#the-one-hard-rule) asks.

## History

- 2026-10-18: Opened. While twitch.md was written, `change_state` was found to keep only the last state. A run
  of the real `_run` with stubs showed which presses are replaced in each handler.
- 2026-10-20: `INVENTORY_FETCH` no longer awaits `websocket.start`, which now returns at once, so the table
  leaves it out.
