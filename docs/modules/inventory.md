# `inventory.py`

**Purpose.** The module turns the campaign data from Twitch into objects: `DropsCampaign`, its `TimedDrop`s and
their `Benefit`s. It decides whether a drop or a campaign can progress, on which channel and when. It keeps the
watched minutes of each drop and claims finished drops. `Twitch.fetch_inventory` builds new objects on every
reload ([twitch.md](twitch.md#state-machine)). The only request the module sends is the claim.

## Public contract

### `DropsCampaign(twitch, data, claimed_benefits)`

`data` is one campaign, merged from the `Inventory`, `Campaigns` and `CampaignDetails` GQL responses.
`claimed_benefits` maps a benefit ID to the time it was last awarded, from the inventory's `gameEventDrops`.

- Data: `id`, `name`, `game` (a `Game`), `linked` (the user's account is connected to the game), `link_url`,
  `image_url` (the game's box art without its size suffix), `starts_at`, `ends_at`, `timed_drops` (a
  `dict[str, TimedDrop]` by drop ID) and `drops` (its values).
- `allowed_channels` is the ACL (access control list) as `Channel.from_acl` objects. It is empty when the campaign
  has no ACL or its ACL is disabled, and then every channel passes the ACL check. `Twitch.fetch_inventory` leaves
  out a campaign whose `allow` is null ([gqldata.md](gqldata.md#null-campaign-details)). A null `allow` is not
  read as no ACL, because the real ACL is then unknown and every channel of the game would pass the check.
- Status: `active` is True when the campaign is valid (its status is not `EXPIRED`) and now is between
  `starts_at` and `ends_at`. `upcoming` is True when it is valid and has not started. `expired` is True when it is
  not valid or has ended.
- `eligible` is `linked`, except for a campaign with a badge or emote reward (`has_badge_or_emote`), where it is
  the "Enable partial support for badges and emotes" setting (`enable_badges_emotes`).
- Totals: `total_drops`, `claimed_drops`, `remaining_drops`, `finished` (every drop is claimed or needs no
  minutes), `required_minutes` and `remaining_minutes` (the largest over the drops, with precondition chains),
  `progress` (the mean of the drops' progress) and `availability` (the smallest over the drops). A campaign with
  no drops has the totals of a campaign whose drops need no minutes: `required_minutes` and `remaining_minutes`
  are 0, `progress` is 0.0 and `availability` is `math.inf`. The Inventory tab hides a campaign whose
  `required_minutes` is 0, and `PriorityMode.LOW_AVBL_FIRST` orders it last. Such a campaign is kept, not left
  out, so its game is still offered as a choice in the Priority and Exclude lists.
- `first_drop` is the drop that can progress now with the fewest remaining minutes, or None.
- `time_triggers` is the set of start and end times of the campaign and its drops. The maintenance task ends
  its sleep at these times ([twitch.md](twitch.md#maintenance-task)).
- `can_earn(channel=None, ignore_channel_status=False)`, `can_earn_within(stamp)` and `bump_minutes(channel)` are
  described below. `get_drop(drop_id)` returns a drop or None, and nothing calls it
  ([task 022](../refinements/tasks/022-unused-code.md)).

### `TimedDrop`

- Data: `id`, `name`, `campaign`, `benefits`, `starts_at`, `ends_at`, `claim_id`, `is_claimed`,
  `precondition_drops` (IDs of the drops that must be claimed first) and `required_minutes`.
- Minutes: `real_current_minutes` comes from Twitch, `extra_current_minutes` is estimated by the app, and
  `current_minutes` is their sum. `remaining_minutes` is `required_minutes` less `current_minutes`.
  `total_required_minutes` and `total_remaining_minutes` add the longest chain of precondition drops.
- `progress` is between 0.0 and 1.0. `availability` is the minutes left until `ends_at` divided by
  `total_remaining_minutes`, or `math.inf`. A low value leaves little spare time, and
  `PriorityMode.LOW_AVBL_FIRST` orders such campaigns first.
- `can_earn(channel=None, ignore_channel_status=False)`, `can_claim`, `claim()`, `update_claim(claim_id)` and
  `update_minutes(new_minutes)` are described below. `display(*, countdown=True, subone=False)` shows the drop in
  the Campaign Progress box and the tray title. `rewards_text(delim=", ")` joins the benefit names.

`BaseDrop` holds everything that does not depend on minutes. `TimedDrop` is its only subclass and the only drop
type the app builds. `Benefit` has `id`, `name`, `image_url` and `type`, a `BenefitType`: `BADGE`, `EMOTE`,
`DIRECT_ENTITLEMENT`, or `UNKNOWN` for any other `distributionType`.

## When a drop can progress

`TimedDrop.can_earn(channel, ignore_channel_status)` is True when all of these hold:

1. Every drop in `precondition_drops` is claimed.
2. The drop is not claimed.
3. It has at least one benefit, or an unclaimed drop of the campaign lists it as a precondition.
4. `required_minutes` is above 0, and `extra_current_minutes` is below `MAX_EXTRA_MINUTES` (15).
5. Now is between its `starts_at` and `ends_at`.
6. The campaign is `eligible` and `active`. When a channel is given: the campaign has no ACL or the channel is in
   it, and either `ignore_channel_status` is True, the channel's current game is the campaign's game, or the
   campaign's game is a [special game](#special-games).

`DropsCampaign.can_earn` is True when check 6 passes and any drop passes checks 1 to 5. `Twitch.can_watch` and
`Twitch.get_active_campaign` call it with the channel.

`DropsCampaign.can_earn_within(stamp)` is True when the campaign can progress at some time before `stamp`, on
any channel: it is eligible, valid, has not ended, starts before `stamp`, and has a drop that passes checks 1 to
4, has not ended and starts before `stamp`. `Twitch` calls it with a stamp one hour ahead to choose the wanted
games, the campaigns whose channels it fetches, and the time triggers.

## Special games

`Game.is_special()` in `utils.py` returns True for the game IDs in `Game.SPECIAL_GAME_IDS`: 509663 and 509672.
The commits that added them name these games "Special Events" and "IRL". A campaign for a special game skips the
game check: any channel on its ACL, or any channel when it has no ACL, can progress it, whatever game the channel
streams. `Twitch.can_watch` accepts such a channel without checking its game against the wanted games or its
drops status.

## Progress

Three sources change a drop's minutes:

1. A websocket `drop-progress` event (`Twitch.process_drops`) calls `update_minutes(current_progress_min)` on its
   drop, when that drop can progress on the watched channel.
2. When no event arrives in time, `Twitch._watch_loop` sends a `CurrentDrop` GQL query and calls
   `update_minutes(currentMinutesWatched)` on the drop it names, under the same condition.
3. When that query fails, `_watch_loop` calls `bump_minutes(channel)` on the campaign `Twitch.get_active_campaign`
   returns. It adds 1 to `extra_current_minutes` of each drop that can progress on the channel.

`update_minutes(new_minutes)` computes the change from the drop's `real_current_minutes`, limited so that the drop
stays between 0 and `required_minutes`. `DropsCampaign._update_real_minutes` then adds that same change to every
drop of the campaign, caps each at `required_minutes` and sets its `extra_current_minutes` to 0. The floor at 0
holds only for the drop that was updated. For example, with two drops at 10 and 1 minutes, an update of the first
to 8 leaves them at 8 and -2 ([task 016](../refinements/tasks/016-negative-minutes-for-other-drops.md)).

When an estimate reaches `MAX_EXTRA_MINUTES`, `bump_minutes` logs a warning and enters `State.CHANNEL_SWITCH`.
Check 4 then fails for that drop. The progress handlers in `Twitch` skip a drop that cannot progress, so it stays
at the limit until the next reload builds new objects, unless an update for another drop of the campaign resets
its estimate.

After every change a drop calls `gui.inv.update_drop` for its row on the Inventory tab. After a change of
minutes the campaign also displays its `first_drop`.

## Claiming

- `claim_id` comes from the drop's `self.dropInstanceID` in the campaign data, or from a websocket `drop-claim`
  event through `update_claim`.
- `can_claim` is True when `claim_id` is set, the drop is not claimed, and now is less than 24 hours after the
  campaign's `ends_at`. The code comment cites the Twitch help page for this 24 hour window.
- `claim()` sends nothing for a drop that is already claimed, which counts as a success, or when `can_claim` is
  False, which counts as a failure. Otherwise it sends one `ClaimDrop` GQL mutation with the `dropInstanceID`.
  A `claimDropRewards.status` of `ELIGIBLE_FOR_ALL` or `DROP_INSTANCE_ALREADY_CLAIMED` is a success: the drop is
  marked claimed, its minutes are set to `required_minutes`, a line goes to the Output box and the tray shows a
  notification when tray notifications are on. A `GQLException` or any other response is a failure, which is
  logged as an error.
- `Twitch` claims a drop on a `drop-claim` event, and in `State.GAMES_UPDATE` for every claimable drop of the
  campaigns that are not upcoming. So a drop with a claim ID that no event claimed is claimed at the next reload.
- Without `self` data, a drop counts as claimed when at least one of its benefits is in `claimed_benefits` and
  every such award time is between the drop's `starts_at` and `ends_at`.
- `generate_claim()` builds a claim ID as `<user ID>#<campaign ID>#<drop ID>`. Nothing calls it
  ([task 022](../refinements/tasks/022-unused-code.md)).

## Invariants

- Every time check uses `datetime.now(timezone.utc)` at call time, so a result changes as time passes. Callers
  check again instead of keeping a result.
- `TimedDrop.update_minutes` goes through the campaign, so every drop of a campaign changes by the same amount,
  within the limits under [Progress](#progress).
- The only request is `ClaimDrop` through `Twitch.gql_request`. The rules can be called without Twitch, with a
  stand-in `twitch` object that has `settings`, `gui` and `change_state`
  ([task 003](../refinements/tasks/003-test-suite.md)).
- The module is over the 300 line cap ([task 005](../refinements/tasks/005-modules-over-the-line-cap.md)).

**Dependencies.** `channel` (`Channel`), `utils` (`Game`, `timestamp`), `exceptions` (`GQLException`),
`constants` (`GQL_QUERIES`, `MAX_EXTRA_MINUTES`, `URLType`, `State`) and `translate`. No third party package.
