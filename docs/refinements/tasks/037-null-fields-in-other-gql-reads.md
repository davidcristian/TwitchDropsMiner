# Some GQL reads still raise on a null field

**Status:** done 2026-10-22
**Area:** twitch, inventory
**Origin:** Found on 2026-10-20 while the reads of the campaign details, the game directory and the available
drops were changed to leave out a field that a GQL server error set to null
**Verified:** 2026-10-22

After a `server error`, `Twitch.gql_request` sets the field that the error's `path` names to null and returns
the response. When the path names no field, it logs the error and returns the response as Twitch sent it
([twitch.md](../../modules/twitch.md#gql-requests)). The reads in `fetch_campaigns`, `get_live_streams`,
`bulk_check_online` and `Channel.get_stream` leave out a null item ([gqldata.md](../../modules/gqldata.md)).
These reads index a null field and raise `TypeError`:

| Where | Field that is null | What the raise does |
| --- | --- | --- |
| `Twitch.fetch_inventory` | `currentUser`, `inventory` or `gameEventDrops` of `Inventory`, `currentUser` of `Campaigns` | ends the run, and the restart begins with a full reload ([task 019](019-restart-runs-a-full-reload.md)) |
| `DropsCampaign` and `TimedDrop`, built in `fetch_inventory` | a field inside a drop, such as the `benefit` of a benefit edge or the drop's `self` | ends the run, as above |
| `Twitch.process_drops`, after a `drop-claim` | `currentUser` of `CurrentDrop` | ends the handler task, which `task_wrapper` logs, so the watch restart or the reload that follows a claim does not happen |
| `BaseDrop._claim`, from `process_drops` | the whole `data` of `ClaimDrop` | ends the handler task, as above |

The `CurrentDrop` read in `_watch_loop` and the `PlaybackAccessToken` read in `Stream.get_stream_url` end the
app, as [task 013](013-crashed-task-ends-the-app.md) describes.

## What a fix involves

Each read uses `gqldata.get_field` or a reader in `gqldata.py` and treats a null item as missing. The
`Inventory` read needs a decision first: without `gameEventDrops`, `fetch_inventory` cannot tell which drops
were claimed, so ending the run may be the correct result there. No fix adds a request.

## History

- 2026-10-20: Opened. The reads of the campaign details, the game directory and the available drops were
  changed to leave out a null item, and these reads were left as they were.
- 2026-10-21: The reads in the table and the `CurrentDrop` read in `_watch_loop` now go through `gqldata.py`
  ([gqldata.md](../../modules/gqldata.md)). A null drop, benefit or precondition is left out, a null drop `self`
  counts as none, a null campaign `self` leaves the campaign out, a null `CurrentDrop` user counts as no drop and a
  null `ClaimDrop` result as a failed claim. A null user, inventory or claimed drop in `Inventory` or `Campaigns`
  still ends the run, now as `GQLException`, because the reload cannot tell which campaigns exist or which drops
  are claimed. Still open: the `PlaybackAccessToken` read, where a skip would send the query again every watch
  cycle; a null channel in `allow.channels`, which `Channel.from_acl` reads, and which would read as no ACL if
  every channel were left out; and a null value such as a drop's `startAt`, which `timestamp` reads.
- 2026-10-22: A null token, value or signature in `PlaybackAccessToken` fails the watch cycle and starts an
  online check, and that `Stream` sends no second query: at most 30 token and 30 `GetStreamInfo` queries an hour
  while it stays null ([channel.md](../../modules/channel.md#a-null-playback-token)). An ACL channel that is
  null or has a null ID or name is left out, and so is a campaign whose enabled ACL keeps no channel. A drop or
  campaign with a null `startAt` or `endAt` is left out
  ([gqldata.md](../../modules/gqldata.md#null-times-and-acl-channels)). A null `lastAwardedAt` ends the run as
  `GQLException`. Still open: a null game `id` or `boxArtURL`, or a null drop `requiredMinutesWatched`, raises
  `TypeError` in `DropsCampaign`, which ends the run. A check with stub data confirmed each of the three.
- 2026-10-22: Done. A campaign whose game has a null or missing ID, name or box art is left out, and a null game
  `slug` is read as missing, so `Game` forms it from the name. A drop with null or missing required minutes is
  left out, with the drops that need it ([gqldata.md](../../modules/gqldata.md#null-game-fields)).
  `tests/test_twitch_drops.py` reloads with each of the three set to null by a server error. A null field in
  stream data, such as the game ID of a stream, still raises, which [task 059](059-null-fields-in-stream-data.md)
  records.
