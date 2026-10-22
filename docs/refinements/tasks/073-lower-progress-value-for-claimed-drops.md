# A lower progress value takes minutes from the claimed drops of the campaign

**Status:** done 2026-10-22
**Area:** inventory (drop progress)
**Origin:** Found on 2026-10-22 while the other drops of a campaign were kept at 0 minutes or more,
[inventory.md](../../modules/inventory.md#progress)
**Verified:** 2026-10-22

`DropsCampaign._update_real_minutes` in `inventory.py` adds the change that `TimedDrop.update_minutes` computes
to every drop of the campaign, a claimed drop included. A claimed drop has `real_current_minutes` equal to
`required_minutes`, so a negative change leaves it below that. A campaign with d1 claimed at 60 of 60 minutes,
d2 at 10 of 60, and d3 at 0 of 60 with d1 as its precondition gave these values after `d2.update_minutes(8)`:

- d1 had 58 minutes and a `remaining_minutes` of 2, and `is_claimed` stayed True.
- d3's `total_remaining_minutes` and the campaign's `remaining_minutes` went from 60 to 62, so the
  `availability` that divides by them fell.
- Without d3, `DropsCampaign.progress` was 0.55, where the mean with d1 at 60 minutes is 0.567.

The Inventory tab still shows d1 as claimed, because `InventoryOverview.update_progress` checks `is_claimed`
first, and `first_drop` leaves out claimed drops. The next reload sets a claimed drop's minutes to
`required_minutes` again. A negative change needs Twitch to report fewer minutes for a drop than the app holds,
the case that [task 016](016-negative-minutes-for-other-drops.md) describes.

## What a fix involves

Leave a claimed drop out of the change, in `TimedDrop._update_real_minutes`. A claimed drop has no
`extra_current_minutes` to reset, because `claim()` sets them to 0 and `bump_minutes` adds them only to a drop
that can progress. The other drops that cannot progress keep the change
([inventory.md](../../modules/inventory.md#progress)). Twitch requests: none.

## History

- 2026-10-22: Opened. A script built the campaign above with the test fakes in `tests/fakes.py` and called
  `update_minutes` with a lower value, after the fix that keeps the other drops at 0 minutes or more.
- 2026-10-22: Closed. `TimedDrop._update_real_minutes` returns at once for a claimed drop, which keeps
  `required_minutes`, as building the drop and `claim()` set it. A test in `tests/test_inventory.py` builds d1
  claimed at 60 minutes and d2 at 10, updates d2 to 8 and checks that d1 stays at 60
  ([inventory.md](../../modules/inventory.md#progress)).
