# The campaign map keeps every campaign since the app started

**Status:** open
**Area:** twitch (inventory), channel
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#invariants)
**Verified:** 2026-10-18

`Twitch._campaigns` maps a campaign ID to its `DropsCampaign`. `Twitch.fetch_inventory` in `twitch.py` adds
each fetched campaign to it and never removes one. A few lines earlier it clears `_drops`, `inventory` and
`_mnt_triggers`, and `shutdown` clears the same three, but neither clears `_campaigns`. So the map keeps every
campaign fetched since the process started, across reloads, restarts after a fatal error and the `Invalidate`
button, which logs in again, possibly to another account.

## Who reads it

One function: `Channel._check_drops_enabled` in `channel.py`. It gets the campaign IDs that Twitch's
`AvailableDrops` response lists for a channel and looks each one up in `_campaigns`. It returns True when
`campaign.can_earn(channel, ignore_channel_status=True)` is True for one of them. Two places call it, and only
when the stream information says that drops are not enabled:

- `Channel.external_update`, from `bulk_check_online` in `State.CHANNELS_FETCH`. Its list is empty unless
  `available_drops_check` is on.
- `Channel.get_stream`, after an `AvailableDrops` query, when a stream comes online or changes.

The result sets `Stream.drops_enabled`.

## What a stale entry changes

A stale entry is one that the latest `fetch_inventory` did not return. An ID that the latest fetch returned
has a current entry, because the fetch replaces it. For a stale ID, the old object's data sets the
result: its `ends_at`, its `_valid` flag, the `linked` flag of the account it was fetched for, and the claim
state of its drops.

- A campaign that ended by its time has `active` False, so its entry returns False, as no entry would.
- The fetch leaves out a campaign whose status is not `ACTIVE` or `UPCOMING`, or whose game is null. If
  Twitch still lists such a campaign for a channel while its old entry has a future `ends_at`, that entry can
  return True and set `drops_enabled` on the channel. `can_watch` reads `inventory`, not `_campaigns`, so the
  channel is watched only when a current campaign can also progress on it. Whether Twitch lists such a
  campaign in `AvailableDrops` is not recorded in this repo.
- After `Invalidate` and a login to another account, entries that the new account's fetch did not return keep
  the first account's `linked` flags and claims.

The memory cost applies in every case. Each stale entry keeps its drops, its benefits and one `Channel` object
per channel of its ACL (access control list). A copy that runs for weeks keeps every campaign it has seen.

## How it was confirmed

A script ran the real `fetch_inventory` twice on a stub client whose `gql_request` returns fixed responses: first
campaigns A, with a 1200 channel ACL, and B; then B and C. It measured memory with `tracemalloc` and then
called the real `Channel._check_drops_enabled`:

```
fetch 1 returns A, B -> inventory: ['B', 'A'] _campaigns: ['A', 'B']
fetch 2 returns B, C -> inventory: ['B', 'C'] _campaigns: ['A', 'B', 'C']
stale A still holds 1200 Channel objects
memory freed when A is dropped: 276 KiB
_check_drops_enabled([{'id': 'A'}]) with stale A: True
  same call when _campaigns holds only the current fetch: False
```

`git grep` finds no other reader of `Twitch._campaigns`. `InventoryOverview._campaigns` in `gui.py` is a
separate map, and `fetch_inventory` empties it on every fetch with `gui.inv.clear()`.

## How it came about

The original project added `_campaigns` in "Fix an issue with the drops_enabled flag reporting true for
sub-only drops" (2025-09-09, found with `git log -S'self._campaigns[campaign.id] = campaign'`). That commit
added it next to `_drops`, which `fetch_inventory` clears, and gave it no `clear()` call.

## What a fix involves

Clear `_campaigns` in `fetch_inventory` next to `self._drops.clear()` before the loop that fills it, or build
it from `campaigns` in one step, and clear it in `shutdown` with the other run data. A stale ID then finds no
entry, and `_check_drops_enabled` skips it. The invariant in [twitch.md](../../modules/twitch.md#invariants) and
the consequence in [ADR-0006](../../adr/ADR-0006-restart-after-fatal-error.md) that names `_campaigns` change
in the same commit. The fix sends no Twitch request.

## History

- 2026-10-18: Opened. While the invariants of twitch.md were written, `shutdown` was found not to clear
  `_campaigns`. Two runs of the real `fetch_inventory` with stubbed responses showed the stale entry, its memory
  and its effect on `_check_drops_enabled`.
