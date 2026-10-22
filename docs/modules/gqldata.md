# `gqldata.py`

**Purpose.** Reads the campaign and drop data of GQL responses for `twitch.py` and `inventory.py`. After a
`server error`, `Twitch.gql_request` sets the field that the error's `path` names to null
([twitch.md](twitch.md#gql-requests)), so each function here leaves out a null item instead of raising. A raise
inside `Twitch._run` ends the run, and the restart after it begins with a full reload
([task 019](../refinements/tasks/019-restart-runs-a-full-reload.md)). An inventory that cannot be read at all
still raises ([A null inventory](#a-null-inventory)). Which fields Twitch names in a server error has
not been observed, so the functions accept a null object or list item at any level, and a null value in any
field: the sections below name the reading of each. [streamdata.md](streamdata.md) reads the stream data in the
same way, with `get_field`. The module sends no request and needs neither Twitch nor a display.

## Public contract

- `get_field(data, *path)` returns the value at `path`, a sequence of dict keys and list indexes. It returns
  None when a value on the way is null, missing, or not a dict or a list. With no path it returns `data`.
- `clear_error_field(data, path)` sets the field at a server error's `path` to None and returns True. It
  returns False and changes nothing when the path is empty or the field's parent is null or missing, and
  `gql_request` then logs the error and returns the response as it is.
- `merge_data(primary, secondary)` returns a dict with the keys of both. Where both have a dict, it merges the
  two in the same way; where both have another value, it keeps `primary`'s. A None value counts as no value, so
  the value of the other side is kept. Two values of different types raise
  `MinerException("Inconsistent merge data")`.
- `user_inventory(response)` returns the `inventory` of an `Inventory` response, without a null item of
  `dropCampaignsInProgress`, and with an empty list for a null one. It leaves out a campaign in progress and an
  item of `gameEventDrops` whose `id` is null, with a warning. It raises `GQLException` when `data`,
  `currentUser`, `inventory` or `gameEventDrops` is null, or an item of `gameEventDrops` or its
  `lastAwardedAt` is null.
- `campaign_summaries(response)` maps each campaign ID to the summary of a `Campaigns` response whose `status`
  is `ACTIVE` or `UPCOMING`. It leaves out a null summary, and one whose `id` or `status` is null with a warning.
  It returns no campaigns for a null `dropCampaigns`, and raises `GQLException` when `data` or `currentUser` is
  null.
- `campaign_details(campaign_ids, responses)` maps each ID in `campaign_ids` to the `dropCampaign` of its
  `CampaignDetails` response, the one at the same position in `responses`, and leaves out a response whose
  `data`, `user` or `dropCampaign` is null. `fetch_campaigns` merges the details into the summary, so a null
  `id` in the details is read from the summary.
- `complete_campaigns(campaigns)` returns the campaigns in which none of `CAMPAIGN_FIELDS` (`game`, `self`,
  `allow` and `timeBasedDrops`) is null or missing. `DropsCampaign` reads all four. It also leaves out a
  campaign with a null time or ACL ([Null times and ACL channels](#null-times-and-acl-channels)), or with a null
  game field ([Null game fields](#null-game-fields)). In each campaign it returns, `timeBasedDrops` holds only
  the drops that `TimedDrop` can read ([Null drops](#null-drops)), and `allow.channels` only the channels that
  `Channel.from_acl` can read. It reads the other null fields as [Other null fields](#other-null-fields) says.
- `current_drop(response)` returns the `dropCurrentSession` of a `CurrentDrop` response, or None when it,
  `currentUser` or `data` is null. It keeps a null field of the session. `Twitch._watch_loop` reads a session
  whose `dropID` or `currentMinutesWatched` is null as none, and adds an estimated minute
  ([twitch.md](twitch.md#watch-loop)). `Twitch.process_drops` reads only `dropID`, and a null one ends its wait
  for the next drop after a claim, as a null session does.
- `claim_succeeded(response)` returns True when the `claimDropRewards.status` of a `ClaimDrop` response is in
  `CLAIMED_STATUSES` (`ELIGIBLE_FOR_ALL` and `DROP_INSTANCE_ALREADY_CLAIMED`) and its data has no `errors`.
  It returns False for any other response, a null `data`, `claimDropRewards` or `status` included.

## A null inventory

`Twitch.fetch_inventory` sends `Inventory`, then `Campaigns`. When `user_inventory` or `campaign_summaries`
raises, the reload stops after these 1 or 2 requests, before the `CampaignDetails` and channel requests. The run
ends, and it restarts after the "Restart after a crash after" delay, as after any fatal error
([twitch.md](twitch.md#restart-after-a-fatal-error)).

Reading the null as an empty inventory was rejected. A drop without `self` data counts as claimed only through
the claimed benefits in `gameEventDrops` ([inventory.md](inventory.md#claiming)). Without them, the app would
mine drops that are already claimed until the next hourly reload. Without the `Campaigns` list, it would miss
every campaign that is not in progress.

A null campaign in progress or a null summary is only left out, and one whose `id` is null is left out with a
warning, as is a summary whose `status` is null. A campaign in progress is then built from its summary and
details, without the drop minutes and claim IDs of its `Inventory` data, until the next reload. A campaign with
a null summary that is not in progress is not fetched in this reload, which sends one `CampaignDetails`
operation fewer.

An item of `gameEventDrops` whose `id` is null is left out with a warning, and the run goes on. Ending the run,
as a null `lastAwardedAt` does, would cost a full reload at the restart. Left out, it costs at most that a drop
without `self` data whose benefit it was counts as not claimed until the next reload, so the app may watch a
channel for that drop until `MAX_EXTRA_MINUTES` of estimated minutes stop it ([inventory.md](inventory.md#progress)).

## Null campaign details

`Twitch.fetch_inventory` merges three responses: `Inventory` (the campaigns in progress, with their drops), the
`Campaigns` summary of every campaign, and `CampaignDetails`. When the details of a campaign are null, its
summary is kept. A campaign in progress still has its `Inventory` data and is mined. Any other campaign has
only its summary, and `complete_campaigns` leaves it out unless the summary has every field in
`CAMPAIGN_FIELDS`. The next reload fetches its details again.

## Null drops

`complete_campaigns` reads the drops of each campaign it keeps:

- A null drop is left out, and so is a drop whose `id` is null, because `TimedDrop`, the precondition chain and
  the drop events find a drop by its ID.
- A drop whose `startAt` or `endAt` is null or missing is left out, because `BaseDrop` cannot tell when it
  can progress.
- A drop whose `requiredMinutesWatched` is null or missing is left out, because `TimedDrop` cannot tell how
  many minutes it needs.
- A drop with a null item in `preconditionDrops`, or an item whose `id` is null, is left out, because its
  precondition is unknown.
- A drop whose precondition drop was left out is left out too, and so on along the chain. `TimedDrop` looks up
  each precondition in its campaign, and a missing one raises `KeyError`.
- A null benefit edge, or one whose `benefit` is null, is left out, and the drop is kept. A drop without
  benefits cannot progress unless another drop needs it ([inventory.md](inventory.md#when-a-drop-can-progress)).
- A null `self`, or a `self` whose `isClaimed` is null, is read as no `self`: the drop has no claim ID and no
  minutes, and counts as claimed when its benefits are in `gameEventDrops` ([inventory.md](inventory.md#claiming)).
  Reading a null `isClaimed` as False instead could send a `ClaimDrop` for a claimed drop.
- A benefit whose `name` is null is read with an empty name, because `rewards_text` joins the names for the
  Output box, the tray and the Main tab. A null campaign or drop name is read the same way, so the window never
  shows the text `None` ([Other null fields](#other-null-fields)).

Each item left out logs a warning that names the drop and the campaign. A campaign whose drops are all left
out is kept, as a campaign without drops ([inventory.md](inventory.md#public-contract)).

## Null times and ACL channels

`merge_data` fills a null time from another response that has the campaign, so a time stays null only when
every such response has it null. It does not merge lists, so a null channel stays. Each case logs a warning
that names the campaign:

- A campaign whose `startAt` or `endAt` is null or missing is left out, because `DropsCampaign` cannot tell
  when it is active.
- A channel in `allow.channels` that is null, or whose `id` or `name` is null, is left out, and the campaign is
  kept with the other channels.
- When every channel of an enabled ACL is left out, the campaign is left out too. An empty list reads as no
  ACL, which would let every channel of the game pass the ACL check, as a null `allow` would
  ([inventory.md](inventory.md#public-contract)). A disabled ACL is not read, so its campaign is kept.
- A null `isEnabled` is read as missing, so the ACL is enabled, as `DropsCampaign` reads a missing one. Read as a
  disabled ACL, it would let every channel of the game pass the ACL check. This case logs no warning.

## Null game fields

`Game` reads a game's `id`, and its name from `displayName`, or from `name` when `displayName` is null.
`DropsCampaign` reads the game's `boxArtURL` as the campaign image. A campaign whose game has a null or missing
`id`, name or `boxArtURL` after `merge_data` is left out, with a warning that names the campaign. `GAMES_UPDATE`
compares games by ID to build the wanted games and matches the priority and exclude lists against the name, and
the Settings tab sorts the game names. A null `slug` is read as missing, so `Game` forms the slug from the name,
as for a game without one. `get_live_streams` sends that slug in `GameDirectory`.

## Other null fields

These null values are read as the table says, without a warning unless it says so. Each reading lasts until the
next reload, and none adds a request. `tests/test_twitch_null_campaigns.py` sets each value of complete
`Inventory`, `Campaigns` and `CampaignDetails` responses to null in turn and checks each reading on this page.

| Null field | Read as |
| --- | --- |
| a campaign's `name` | an empty name, which the Inventory and Main tabs show as no text |
| `accountLinkURL` | kept: the account link on the Inventory tab opens no page |
| `status` of a campaign in progress | not `EXPIRED`, so its times decide whether it is active |
| `self.isAccountConnected` | False, with a warning: the campaign counts as not linked, so it is mined only for a badge or emote with that setting on |
| `allow.channels` | no ACL ([below](#nulls-that-read-as-none)) |
| a drop's `name` | an empty name, so a progress line in the Output box shows no name |
| `preconditionDrops` | no preconditions ([below](#nulls-that-read-as-none)) |
| `benefitEdges` | no benefits |
| a benefit's `id` | kept: it matches no claimed benefit in `gameEventDrops` |
| `distributionType` | `UNKNOWN`, as any other value is |
| `imageAssetURL` | kept: the Inventory tab shows a blank image, and the image cache logs a warning |
| `self.dropInstanceID` | no claim ID: the drop is claimed only after a `drop-claim` event gives one |
| `self.currentMinutesWatched` | 0 minutes, until a progress event or a `CurrentDrop` query sets them |
| a game's `name` or `displayName` | the other one ([Null game fields](#null-game-fields)) |

### Nulls that read as none

Twitch sends a null `allow.channels` for a campaign without an ACL, and a null `preconditionDrops` for a drop
without preconditions. A null that a server error leaves in either cannot be told apart from those, so it is
read the same way. Such a campaign has no ACL until the next reload: every channel of its game passes the ACL
check, and `CHANNELS_FETCH` sends the one `GameDirectory` request for its game that a campaign without an ACL
costs. Such a drop counts as having no precondition, so the app may show it, or estimate minutes for it,
before its precondition is claimed. Neither ends the run.

## Invariants

- Only `clear_error_field` changes its argument. `merge_data`, `user_inventory` and `complete_campaigns` build
  new dicts but share the other values, such as lists, with their arguments.
- No function sends a request, and no caller sends one again for a null item: a campaign or drop left out
  waits for the next reload, and a summary left out sends no `CampaignDetails` operation. A null `CurrentDrop`
  user means no drop data for that request, and a null `ClaimDrop` result is a failed claim
  ([inventory.md](inventory.md#claiming)). `tests/test_twitch_null_watch.py` sets each value of a complete
  `CurrentDrop` and `ClaimDrop` response to null in turn and checks these outcomes.

**Dependencies.** `exceptions` (`GQLException`, `MinerException`). `constants` (`JsonType`) is imported for type
checking only.
