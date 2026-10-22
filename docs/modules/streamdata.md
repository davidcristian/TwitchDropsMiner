# `streamdata.py`

**Purpose.** Reads the stream and channel data of GQL responses for `twitch.py` and `channel.py`: the
`GetStreamInfo`, `GameDirectory`, `AvailableDrops` and `PlaybackAccessToken` responses. After a `server error`,
`Twitch.gql_request` sets the field that the error's `path` names to null ([twitch.md](twitch.md#gql-requests)),
so each function here leaves out a null item or reads it as no value instead of raising. A raise in
`CHANNELS_FETCH` ends the run, a raise in an online check ends that check, and a raise in the watch loop ends
the app ([task 013](../refinements/tasks/013-crashed-task-ends-the-app.md)). The functions read a field with
`get_field` from [gqldata.md](gqldata.md), which reads the campaign data in the same way. The module sends no
request and needs neither Twitch nor a display.

## Public contract

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

- No function changes its argument. The readers build new dicts but share the other values, such as lists,
  with their arguments.
- No function sends a request, and no caller sends one again for a null item: a game with a null directory
  waits for the next `CHANNELS_FETCH`. A null playback token is requested again only for the `Stream` that the
  online check stores ([channel.md](channel.md#a-null-playback-token)). A channel read as offline sends no
  request of its own until a websocket event starts an online check ([Null stream fields](#null-stream-fields)).

**Dependencies.** `gqldata` (`get_field`). `constants` (`JsonType`) is imported for type checking only.
