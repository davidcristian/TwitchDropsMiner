# A null field in stream data still raises

**Status:** done 2026-10-22
**Area:** channel, twitch
**Origin:** Found on 2026-10-22 while the campaign reads were changed to leave out a campaign whose game has a
null ID: `Stream` reads the game of a stream in the same way
**Verified:** 2026-10-22

After a `server error`, `Twitch.gql_request` sets the field that the error's `path` names to null
([twitch.md](../../modules/twitch.md#gql-requests)). The reads of stream data leave out a null user or a stream
node without a broadcaster ([gqldata.md](../../modules/gqldata.md)), but `Channel` and `Stream` in `channel.py`
read the fields inside them without a check. A check with stub data raised `TypeError` for each null field in
this table:

| Where | Field that is null | What the raise does |
| --- | --- | --- |
| `Twitch.bulk_check_online`, through `Channel.external_update` | the user's `id`, `broadcastSettings`, the stream's `id` or the game's `id` in a `GetStreamInfo` response | ends the run in `CHANNELS_FETCH`, and the restart begins with a full reload ([task 019](019-restart-runs-a-full-reload.md)) |
| `Twitch.get_live_streams`, through `Channel.from_directory` | the node's `id`, the broadcaster's `id` or the game's `id` in a `GameDirectory` stream node | ends the run in `CHANNELS_FETCH`, as above |
| `Channel.get_stream`, from an online check | `broadcastSettings`, the stream's `id` or the game's `id` in a `GetStreamInfo` response | ends the online check task, and the channel's stream is not updated |

A game whose `displayName` and `name` are both null gives a `Game` whose name is None, and `str` of that game
raises `TypeError`.

## What a fix involves

Each read goes through a reader in `gqldata.py`, as the campaign reads do
([gqldata.md](../../modules/gqldata.md#null-game-fields)). A stream with a null ID, or a channel with a null
ID, is left out with a warning, and a stream whose game has a null ID or name counts as a stream without a game.
No fix adds a request.

## History

- 2026-10-22: Opened. Found while the campaign reads were changed to leave out a campaign whose game has a null
  ID, name or box art, which closed [task 037](037-null-fields-in-other-gql-reads.md).
- 2026-10-22: Done. The stream data of `GetStreamInfo` and `GameDirectory` goes through readers in `gqldata.py`
  ([streamdata.md](../../modules/streamdata.md#null-stream-fields)). A stream with a null ID reads as an offline
  channel, and a directory stream with a null ID, broadcaster ID or login is left out. A user with a null ID is
  left out of the bulk check. A game with a null ID or name, and null broadcast settings, give a stream without
  a game. A live channel read as offline costs at most one `GetStreamInfo` per `ONLINE_DELAY`, through its
  online check. `tests/test_twitch_streams.py` sends each null through `Twitch.gql_request`. A null item in the
  `AvailableDrops` data of the same checks still raises, which [task 060](060-null-fields-in-available-drops.md)
  records.
