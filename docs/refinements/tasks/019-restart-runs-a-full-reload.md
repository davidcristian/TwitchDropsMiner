# Each restart after a fatal error runs a full reload

**Status:** open
**Area:** twitch (restart), Twitch traffic
**Origin:** Found on 2026-10-18 while the docs were written, [ADR-0006](../../adr/ADR-0006-restart-after-fatal-error.md)
**Verified:** 2026-10-18

After a fatal error, `Twitch._await_restart` in `twitch.py` calls `shutdown()`, which clears the inventory,
the channels and the login state, and waits `restart_delay` minutes plus a random 0 to 60 seconds
(`RESTART_JITTER`). `Twitch.run` then calls `_run` again. `_run` logs in, which sends a GET of
`https://www.twitch.tv` for the device ID and a GET of `https://id.twitch.tv/oauth2/validate` for the token,
because `shutdown` removed both from memory. It then starts in `State.INVENTORY_FETCH`, a full reload
([ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md#the-cost-of-a-full-reload)).

The choices of "Restart after a crash after" (`SettingsPanel.RESTART_DELAYS` in `gui.py`) are Never, 1, 5,
10, 15, 30 and 60 minutes. Nothing makes the delay longer when the error comes back. So an error that repeats
on every run, after the reload's requests, causes one full reload per restart, without end.

One such error is an outdated hash. When Twitch stops accepting the `GameDirectory` hash in `constants.py`,
`gql_request` retries the `PersistedQueryNotFound` response once and then raises `GQLException`, and
`get_live_streams` turns it into a `MinerException`. That happens in `State.CHANNELS_FETCH`, after
`fetch_inventory` and after `bulk_check_online` has checked every ACL channel, so each run sends the whole
reload and then fails. An outdated `GetStreamInfo` hash fails inside `bulk_check_online`, after part of its
batches. [gql-operations.md](../../runbooks/gql-operations.md) describes what such an error looks like.

## The worst case

ADR-0002's example has about 100 campaigns and 1200 ACL channels. Its reload sends 67 GQL requests with 1302
operations, or 127 requests with 2502 operations when `available_drops_check` is on. At 5 requests per second
(`RateLimiter(capacity=5, window=1)`) the reload takes at least 13.4 seconds, or 25.4 seconds. A run that fails
right after its reload starts again after that time plus the delay plus the jitter:

| `restart_delay` | Reloads per hour, at most | On average | GQL requests per hour, at most | Operations per hour, at most |
| --- | --- | --- | --- | --- |
| 1 minute | 49 | 35 | 3286 | 63858 |
| 1 minute, drops check on | 42 | 31 | 5354 | 105471 |
| 10 minutes (default) | 5.9 | 5.6 | 393 | 7641 |
| 10 minutes, drops check on | 5.8 | 5.5 | 731 | 14402 |
| 60 minutes | 1 | 1 | 67 | 1302 |

"At most" uses no jitter, and "on average" uses the mean jitter of 30 seconds. In normal operation the reload
runs once an hour. So at the 1 minute choice a repeating error sends about 49 times the reload traffic of a
working app, and at the default about 6 times. The counts leave out one `GameDirectory` request per wanted game
without an ACL, the failing request and its retry, and the two login GETs.

## How it was confirmed

The rates come from a script that read `RESTART_JITTER` from `constants.py` and the choices from
`SettingsPanel.RESTART_DELAYS`, and used ADR-0002's per-reload counts (1 `Inventory`, 1 `Campaigns`, 5
`CampaignDetails` and 60 `GetStreamInfo` requests, plus 60 `AvailableDrops` with the check). The operations
column multiplies the same rates by ADR-0002's 1302 and 2502 operations per reload. Part of the output:

```
restart_delay choices (minutes): [1, 5, 10, 15, 30, 60] | jitter up to 60.0 s
requests per reload: 67 | with available_drops_check: 127
   67 req, delay  1 min: at most  49.0 reloads/h (  3286 req/h), on average  34.8 (  2333 req/h)
   67 req, delay 10 min: at most   5.9 reloads/h (   393 req/h), on average   5.6 (   375 req/h)
  127 req, delay  1 min: at most  42.2 reloads/h (  5354 req/h), on average  31.2 (  3962 req/h)
```

The code path was read in full: `Twitch.run`, `_await_restart`, `shutdown`, `_AuthState._validate`, the start
of `_run`, and the `GQLException` path of `gql_request`, `get_live_streams` and `bulk_check_online`.

## The rule

[AGENTS.md](../../../AGENTS.md#the-one-hard-rule) says a full reload "runs at startup, once an hour from
`_maintenance_task`, after a drop is claimed and from the Reload button", and "Do not add a timer that runs it
more often". The restart is not on that list. ADR-0002 decision 3 counts it under startup, and the consequences
of ADR-0006 say that a repeating error "costs up to one full reload per restart". Neither of them gives the
hourly rate above or compares it with the once an hour of the rule. With a repeating error, the restart delay
works as a timer that runs the reload up to 49 times an hour.

## How it came about

The restart, the 1 minute choice and the jitter were added together in "Restart automatically after a fatal
error" (2026-08-25, found with `git log -S'(1, 5, 10, 15, 30, 60)' -- gui.py`). Its message says that the
restart "costs nothing compared to closing and reopening the application". That holds for one restart, but a
person does not reopen the app 49 times an hour. The reload list in AGENTS.md was written on 2026-10-18,
without the restart.

## What a fix involves

Each of these changes ADR-0006, and the reload list in AGENTS.md names the restart in the same commit.

- **Lengthen the delay while the error repeats.** Double the delay after each restart whose run fails before
  it reaches a set point, such as its first `CHANNEL_SWITCH` or one hour of running, up to 60 minutes, and reset
  it at that point. From the 1 minute choice, the waits are 1, 2, 4, 8, 16, 32 and 60 minutes: about 6 reloads
  in the first hour, then 1 an hour.
- **Raise the shortest choice.** Without the 1 and 5 minute choices, a repeating error causes at most 5.9
  reloads an hour. A saved value that is no longer a choice is reset to 10 when `SettingsPanel` is created.
- **Keep the campaigns across a restart.** A restart soon after a reload starts with `State.CHANNELS_CLEANUP`
  and keeps the inventory, which costs a few requests. It breaks the rule in ADR-0006 that a restart begins
  from the state of a fresh start, and an error in `fetch_inventory` still needs the full reload.

The commit states the new worst case per hour, as AGENTS.md asks for a change to the request count.

## History

- 2026-10-18: Opened. While the consequences of ADR-0006 were written, the restart was found to start with a
  full reload, and the hourly rate was computed from ADR-0002's counts.
- 2026-10-20: A field that a GQL server error sets to null in the campaign details, the game directory or the
  available drops no longer ends the run, so it causes no restart ([gqldata.md](../../modules/gqldata.md)).
  The task stays open for the errors that still end the run, such as an outdated hash and the reads in
  [task 037](037-null-fields-in-other-gql-reads.md).
- 2026-10-21: A null field in a drop, a null campaign `self`, a null campaign in progress and a null campaign
  summary no longer end the run ([gqldata.md](../../modules/gqldata.md#null-drops)). A null user or inventory in the `Inventory` or
  `Campaigns` response still does, after 1 or 2 requests and before the `CampaignDetails` and channel requests
  ([gqldata.md](../../modules/gqldata.md#a-null-inventory)).
- 2026-10-22: A null time of a drop or campaign and a null ACL channel no longer end the run
  ([gqldata.md](../../modules/gqldata.md#null-times-and-acl-channels)). A null `lastAwardedAt` in `Inventory`
  still does.
- 2026-10-22: A null game ID, name or box art and null required minutes of a drop no longer end the run
  ([gqldata.md](../../modules/gqldata.md#null-game-fields)). A null field in stream data still does
  ([task 059](059-null-fields-in-stream-data.md)).
- 2026-10-22: A null field in the stream data of `GetStreamInfo` or `GameDirectory` no longer ends the run
  ([gqldata.md](../../modules/gqldata.md#null-stream-fields)). A null item in `AvailableDrops` data still does,
  with the extra drops check on ([task 060](060-null-fields-in-available-drops.md)).
