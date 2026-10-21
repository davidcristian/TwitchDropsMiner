# A `drop-claim` event for a claimed drop runs the claim handling again

**Status:** done 2026-10-21
**Area:** twitch
**Origin:** Found on 2026-10-20: a second claim of a claimed drop printed the claim line and showed the tray
notification again
**Verified:** 2026-10-21

A drop's `claim()` returns at once when the drop is claimed, so it prints and notifies once
([inventory.md](../../modules/inventory.md#claiming)). The rest of `Twitch.process_drops` still runs for a
`drop-claim` event whose drop is already claimed: that happens when `State.GAMES_UPDATE` claimed the drop before
the event arrived, or when Twitch sends the event twice. The handler waits 4 seconds, sends `CurrentDrop` up to 8
times when a channel is watched, and then restarts watching or enters `State.INVENTORY_FETCH`. With a stand-in
`Twitch` and a campaign of one drop, two `drop-claim` events for the same drop sent one claim request, and each
event entered `State.INVENTORY_FETCH`:

```text
C. the same event again: ClaimDrop requests: 1 | Claimed lines: 1 | notifications: 1 | states=['INVENTORY_FETCH', 'INVENTORY_FETCH']
```

A fix returns from `process_drops` when the drop was claimed before the event. That removes up to 8 `CurrentDrop`
requests and a watch restart or a second full reload per repeated event, and adds no request. It is deferred
because neither case was seen with real Twitch data: whether Twitch sends the event twice, and whether a drop
claimed in `GAMES_UPDATE` needs the watch restart that the event starts.

## History

- 2026-10-20: Opened. A second claim of a claimed drop printed the claim line twice. The print was fixed in
  `BaseDrop.claim`, and the rest of the handler was left as it was.
- 2026-10-21: Closed. `process_drops` returns at once for a `drop-claim` event whose drop is already claimed.
  The first claim keeps its handling. A drop claimed in `GAMES_UPDATE` needs no restart from the event:
  `GAMES_UPDATE` restarts watching itself, and the watch loop sends a payload every 20 seconds. With the
  stand-in above, the same event twice entered `State.INVENTORY_FETCH` once and sent `CurrentDrop` once.
