# A lower progress value sets other drops of the campaign below zero minutes

**Status:** done 2026-10-22
**Area:** inventory (drop progress)
**Origin:** Found on 2026-10-18 while the docs were written, [inventory.md](../../modules/inventory.md#progress)
**Verified:** 2026-10-22

`TimedDrop.update_minutes(new_minutes)` in `inventory.py` computes `delta = new_minutes - real_current_minutes`,
limits it so that this drop stays between 0 and `required_minutes`, and passes it to
`DropsCampaign._update_real_minutes`. That method calls `TimedDrop._update_real_minutes(delta)` on every drop of
the campaign:

```python
if self.real_current_minutes + delta < 0:
    self.real_current_minutes = 0
if self.real_current_minutes + delta < self.required_minutes:
    self.real_current_minutes += delta
else:
    self.real_current_minutes = self.required_minutes
```

The second `if` is not an `elif`. When the sum is below 0, the first branch sets the value to 0, and the second
branch then adds `delta` to that 0, so the drop ends at `delta`, a negative number. The drop that received the
update is not affected, because `update_minutes` limits `delta` for it. Every other drop of the campaign is.

## How it was confirmed

The writer's script `check_inventory.py`, run against a copy of the code, built a campaign with two drops of 60
minutes at 10 and 1 watched minutes and called `update_minutes(8)` on the first. It printed `8 -2`. More calls
on a campaign with three drops:

| Watched/required before | Call | Watched after |
| --- | --- | --- |
| d1 10/60, d2 0/1, d4 3/15 | `d1.update_minutes(8)` | d1 8, d2 -2, d4 1 |
| d1 8/60, d2 -2/1, d4 1/15 | `d1.update_minutes(2)` | d1 2, d2 -6, d4 -6 |

## When it happens

A negative `delta` needs Twitch to report fewer minutes for a drop than the app holds. Both callers in
`twitch.py` pass Twitch's value: `process_drops` on a `drop-progress` PubSub message, and `_watch_loop` from the
`CurrentDrop` GQL query. The app adds the same `delta` to every drop, including drops that Twitch does not count
at the same time, such as a drop that starts later. The app's value for such a drop then exceeds Twitch's
count, and when Twitch reports that drop's progress, the `delta` is negative. How often Twitch sends a lower
value is not known.

## What the user sees

A run with d1 at 10/60 and d2 at 1/30 gave the numbers below. `d1.update_minutes(5)` left d1 at 5 and d2 at -5:

- `TimedDrop.progress` returns 0.0 when `current_minutes <= 0`, so d2 shows 0.0% in the Inventory tab, and on
  the Main tab when it is the drop shown there. `InventoryOverview.update_progress` shows the percent text,
  because a negative `current_minutes` counts as true.
- `remaining_minutes` is `required_minutes - current_minutes`, so d2 had 35 minutes left of a 30 minute drop.
  `CampaignProgress._update_time` shows that number as the drop's remaining time when d2 is the drop on the Main
  tab, and `total_remaining_minutes` and `DropsCampaign.remaining_minutes` grow by the same amount.
- `DropsCampaign.progress`, the mean of the drop progress values, went from 10.0% to 4.2%.
- `availability` divides the time left by `total_remaining_minutes`, so the campaign sorts earlier under "Low
  availability first".
- The next update for d2 adds the difference to the other drops. `d2.update_minutes(1)` computed a `delta` of 6
  and set d1 to 11, while Twitch's last value for d1 was 5. With the value stopped at 0, the `delta` would have
  been 1 and d1 would be at 6.

The values are correct again after the next reload, which reads `currentMinutesWatched` from Twitch.

## What a fix involves

Make the second `if` an `elif`, so a drop stops at 0. Cost: no Twitch requests.

A related question for the fix: whether a drop that cannot progress should get the `delta` at all. A
`not self.can_earn()` check in `TimedDrop._update_real_minutes` skipped such drops until it was removed on
2026-04-14 in the original project ("Fix an issue with the miner not switching away from an invalidated
channel").

How it came about: until 2026-10-09 the method returned early when the sum was below 0, which left the drop
unchanged. The original project's commit "Fix an issue with a drop real time update delta of zero not
restarting the timer" replaced that `return` with the assignment to 0 and kept the `if` that follows.

## History

- 2026-10-18: Opened while the docs were written. The writer's script and two more scripts, with campaign data
  built in the script, confirmed the negative values. `git log -L` on `_update_real_minutes` showed when the
  lower limit changed.
- 2026-10-22: Closed. `TimedDrop._update_real_minutes` stops each drop at 0 minutes, and a test in
  `tests/test_inventory.py` updates the first of the two drops above to 8 minutes. Every drop still gets the
  change, a drop that cannot progress included, because the reset of `extra_current_minutes` is how a drop at
  `MAX_EXTRA_MINUTES` progresses again before the next reload. Restoring the `can_earn` check would end that,
  and a second test asserts it ([inventory.md](../../modules/inventory.md#progress)). Opened
  [task 073](073-lower-progress-value-for-claimed-drops.md) for the minutes a claimed drop loses.
