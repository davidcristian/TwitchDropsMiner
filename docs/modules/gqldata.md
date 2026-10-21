# `gqldata.py`

**Purpose.** Reads the data of GQL responses for `twitch.py`, `inventory.py` and `channel.py`. After a
`server error`, `Twitch.gql_request` sets the field that the error's `path` names to null
([twitch.md](twitch.md#gql-requests)), so each function here leaves out a null item instead of raising. A raise
inside `Twitch._run` ends the run, and the restart after it begins with a full reload
([task 019](../refinements/tasks/019-restart-runs-a-full-reload.md)). An inventory that cannot be read at all
still raises ([A null inventory](#a-null-inventory)). Which fields Twitch names in a server error has
not been observed, so the functions accept a null object or list item at any level. A null value inside an
object is checked only for the times, the award times, the game fields, the required minutes, the ACL
channel fields and the stream fields named below. The module sends no request and needs neither Twitch nor a
display.

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
  `dropCampaignsInProgress`, and with an empty list for a null one. It raises `GQLException` when `data`,
  `currentUser`, `inventory` or `gameEventDrops` is null, or an item of `gameEventDrops` or its
  `lastAwardedAt` is null.
- `campaign_summaries(response)` maps each campaign ID to the summary of a `Campaigns` response whose `status`
  is `ACTIVE` or `UPCOMING`. It leaves out a null summary, returns no campaigns for a null `dropCampaigns`, and
  raises `GQLException` when `data` or `currentUser` is null.
- `campaign_details(responses)` maps each campaign ID to the `dropCampaign` of a `CampaignDetails` response,
  and leaves out a response whose `data`, `user` or `dropCampaign` is null.
- `complete_campaigns(campaigns)` returns the campaigns in which none of `CAMPAIGN_FIELDS` (`game`, `self`,
  `allow` and `timeBasedDrops`) is null or missing. `DropsCampaign` reads all four. It also leaves out a
  campaign with a null time or ACL ([Null times and ACL channels](#null-times-and-acl-channels)), or with a null
  game field ([Null game fields](#null-game-fields)). In each campaign it returns, `timeBasedDrops` holds only
  the drops that `TimedDrop` can read ([Null drops](#null-drops)), and `allow.channels` only the channels that
  `Channel.from_acl` can read.
- `directory_streams(response)` returns the stream nodes of a `GameDirectory` response that
  `Channel.from_directory` can read, and an empty list when the game, its streams or their edges are null. It
  leaves out a null node or one whose `broadcaster` is null, and reads the other stream fields as
  [Null stream fields](#null-stream-fields) says.
- `channel_streams(responses)` maps each channel ID, as an int, to the `user` of a `GetStreamInfo` response. It
  leaves out a response whose `data` or `user` is null, and reads the other fields as
  [Null stream fields](#null-stream-fields) says.
- `channel_stream(response, channel_id)` returns the `user` of one channel's `GetStreamInfo` response, read in
  the same way, or None when `data` or `user` is null. `channel_id` names the channel in a warning.
- `channel_campaigns(responses)` maps each channel ID, as an int, to the `viewerDropCampaigns` of an
  `AvailableDrops` response, with an empty list for null, and leaves out a response whose `channel` is null.
- `playback_token(response)` returns the `value` and `signature` of a `PlaybackAccessToken` response, or None
  when `data`, `streamPlaybackAccessToken` or either of the two is null. `Stream.get_stream_url` then starts an
  online check ([channel.md](channel.md#a-null-playback-token)).
- `current_drop(response)` returns the `dropCurrentSession` of a `CurrentDrop` response, or None when it,
  `currentUser` or `data` is null.
- `claim_succeeded(response)` returns True when the `claimDropRewards.status` of a `ClaimDrop` response is in
  `CLAIMED_STATUSES` (`ELIGIBLE_FOR_ALL` and `DROP_INSTANCE_ALREADY_CLAIMED`) and its data has no `errors`.
  It returns False for any other response, a null `data` or `claimDropRewards` included.

## A null inventory

`Twitch.fetch_inventory` sends `Inventory`, then `Campaigns`. When `user_inventory` or `campaign_summaries`
raises, the reload stops after these 1 or 2 requests, before the `CampaignDetails` and channel requests. The run
ends, and it restarts after the "Restart after a crash after" delay, as after any fatal error
([twitch.md](twitch.md#restart-after-a-fatal-error)).

Reading the null as an empty inventory was rejected. A drop without `self` data counts as claimed only through
the claimed benefits in `gameEventDrops` ([inventory.md](inventory.md#claiming)). Without them, the app would
mine drops that are already claimed until the next hourly reload. Without the `Campaigns` list, it would miss
every campaign that is not in progress.

A null campaign in progress or a null summary is only left out. A campaign in progress is then built from its
summary and details, without the drop minutes and claim IDs of its `Inventory` data, until the next reload. A
campaign with a null summary that is not in progress is not fetched in this reload.

## Null campaign details

`Twitch.fetch_inventory` merges three responses: `Inventory` (the campaigns in progress, with their drops), the
`Campaigns` summary of every campaign, and `CampaignDetails`. When the details of a campaign are null, its
summary is kept. A campaign in progress still has its `Inventory` data and is mined. Any other campaign has
only its summary, and `complete_campaigns` leaves it out unless the summary has every field in
`CAMPAIGN_FIELDS`. The next reload fetches its details again.

## Null drops

`complete_campaigns` reads the drops of each campaign it keeps:

- A null drop is left out.
- A drop whose `startAt` or `endAt` is null or missing is left out, because `BaseDrop` cannot tell when it
  can progress.
- A drop whose `requiredMinutesWatched` is null or missing is left out, because `TimedDrop` cannot tell how
  many minutes it needs.
- A drop with a null item in `preconditionDrops` is left out, because its precondition is unknown.
- A drop whose precondition drop was left out is left out too, and so on along the chain. `TimedDrop` looks up
  each precondition in its campaign, and a missing one raises `KeyError`.
- A null benefit edge, or one whose `benefit` is null, is left out, and the drop is kept. A drop without
  benefits cannot progress unless another drop needs it ([inventory.md](inventory.md#when-a-drop-can-progress)).
- A null `self` is read as no `self`: the drop has no claim ID and no minutes, and counts as claimed when its
  benefits are in `gameEventDrops` ([inventory.md](inventory.md#claiming)).

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

## Null game fields

`Game` reads a game's `id`, and its name from `displayName`, or from `name` when `displayName` is null.
`DropsCampaign` reads the game's `boxArtURL` as the campaign image. A campaign whose game has a null or missing
`id`, name or `boxArtURL` after `merge_data` is left out, with a warning that names the campaign. `GAMES_UPDATE`
compares games by ID to build the wanted games and matches the priority and exclude lists against the name, and
the Settings tab sorts the game names. A null `slug` is read as missing, so `Game` forms the slug from the name,
as for a game without one. `get_live_streams` sends that slug in `GameDirectory`.

## Null stream fields

`Channel` and `Stream` read a channel's stream from `GetStreamInfo`, through `channel_streams` in the bulk check
and `channel_stream` in an online check, and from `GameDirectory`, through `directory_streams`
([channel.md](channel.md#online-checks)). Each case below logs a warning:

- A stream whose `id` is null is read as no stream, because `Stream` needs the broadcast ID. In `GetStreamInfo`
  the channel counts as offline, as for a null `stream`. In `GameDirectory` the stream is left out.
- A `GameDirectory` stream whose broadcaster has a null `id` or `login` is left out. `Channel` needs both, and
  each request about a channel names it by its login.
- A `GetStreamInfo` user whose `id` is null is left out of `channel_streams`, because the bulk check finds each
  channel by its ID. The channel keeps its current stream, as for a null user ([channel.md](channel.md#bulk-check)).
  An online check does not read that ID.
- A game whose `id` is null, or whose `displayName` and `name` are both null, gives a stream without a game, as
  a stream with no category has. Null `broadcastSettings` give a stream without a game and with a null `title`,
  which nothing reads.

A game with a null field is read as no game rather than as offline because the app already handles a stream
without a game, and such a stream adds no request. The channel then has no game to match the wanted games, and
its `viewcount` events only update its viewers. It stays so until an online check reads the channel again, or
until `CHANNELS_CLEANUP` removes the channel and `CHANNELS_FETCH` adds it again.

A live channel read as offline still sends `viewcount` events, and `Twitch.process_stream_state` calls
`check_online()` for each one ([channel.md](channel.md#after-a-stream-up-event)). A check starts only when none
is pending, and waits `ONLINE_DELAY` (120 seconds) before its one `GetStreamInfo` query. So while the stream ID
stays null, the channel costs at most 30 `GetStreamInfo` queries an hour, the rate of any online check, and no
`AvailableDrops` query. The bulk check sends no `AvailableDrops` query for it either.

## Invariants

- Only `clear_error_field` changes its argument. `merge_data`, `user_inventory`, `complete_campaigns` and the
  stream readers build new dicts but share the other values, such as lists, with their arguments.
- No function sends a request, and no caller sends one again for a null item: a campaign or drop left out
  waits for the next reload, and a game with a null directory for the next `CHANNELS_FETCH`. A null
  `CurrentDrop` user means no drop data for that request, and a null `ClaimDrop` result is a failed claim
  ([inventory.md](inventory.md#claiming)). A null playback token is requested again only for the `Stream`
  that the online check stores ([channel.md](channel.md#a-null-playback-token)). A channel read as offline
  sends no request of its own until a websocket event starts an online check
  ([Null stream fields](#null-stream-fields)).

**Dependencies.** `exceptions` (`GQLException`, `MinerException`). `constants` (`JsonType`) is imported for type
checking only.
