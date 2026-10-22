# `streamdata.py`

**Purpose.** Reads the stream and channel data of GQL responses for `twitch.py` and `channel.py`: the
`GetStreamInfo`, `GameDirectory`, `AvailableDrops` and `PlaybackAccessToken` responses. After a `server error`,
`Twitch.gql_request` sets the field that the error's `path` names to null ([twitch.md](twitch.md#gql-requests)),
so each function here leaves out a null item or reads it as no value instead of raising. A raise in
`CHANNELS_FETCH` ends the run, a raise in an online check ends that check, and a raise in the watch loop ends
the run as well ([utils.md](utils.md#tasks)). The functions read a field with
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
  `AvailableDrops` response, with an empty list for null. It leaves out a response whose `data` or `channel` is
  null, and reads the other fields as [Null available drops](#null-available-drops) says.
- `available_campaigns(response, channel_id)` returns the `viewerDropCampaigns` of one channel's
  `AvailableDrops` response, read in the same way, or an empty list when `data`, `channel` or the list is null.
  `channel_id` names the channel in a warning.
- `playback_token(response)` returns the `value` and `signature` of a `PlaybackAccessToken` response, or None
  when `data`, `streamPlaybackAccessToken` or either of the two is null. `Stream.get_stream_url` then starts an
  online check ([channel.md](channel.md#a-null-playback-token)). The response's other fields are not read.
  `tests/test_twitch_null_watch.py` sets each value of a complete response to null in turn.

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

These cases log no warning, because each has a reading that the app already handles:

- A null `data` or `user` in `GetStreamInfo` leaves the channel's stream as it is in the bulk check, and reads
  as an offline channel in an online check. A null `stream` reads as an offline channel.
- A null `GameDirectory` game, `streams` or `edges` lists no streams, and a null edge, `node` or `broadcaster` is
  left out.
- A null game reads as a stream with no category. A null game `name` or `displayName` is read from the other one.
- A null `viewersCount` gives a stream whose viewers are unknown, until a `viewcount` event sets them. The
  Channels list shows no count, and `CHANNELS_FETCH` sorts the channel as if it had no viewers.
- A null `title` is kept, and nothing reads it.
- A null `displayName` of a user or a broadcaster leaves the channel named by its login.

A null in any other field changes nothing, because the app does not read it. `tests/test_twitch_null_streams.py`
sets each value of a complete response to null in turn and checks each outcome in this section and the next.

A game with a null field is read as no game rather than as offline because the app already handles a stream
without a game, and such a stream adds no request. The channel then has no game to match the wanted games, and
its `viewcount` events only update its viewers. It stays so until an online check reads the channel again, or
until `CHANNELS_CLEANUP` removes the channel and `CHANNELS_FETCH` adds it again.

A live channel read as offline still sends `viewcount` events, and `Twitch.process_stream_state` calls
`check_online()` for each one ([channel.md](channel.md#after-a-stream-up-event)). A check starts only when none
is pending, and waits `ONLINE_DELAY` (120 seconds) before each of its `GetStreamInfo` queries. So while the stream ID
stays null, the channel costs at most 30 `GetStreamInfo` queries an hour, the rate of any online check, and no
`AvailableDrops` query. The bulk check sends no `AvailableDrops` query for it either.

## Null available drops

With the extra drops check on, the bulk check and an online check send `AvailableDrops` for each live channel
and read the campaigns it lists, through `channel_campaigns` and `available_campaigns`
([channel.md](channel.md#drops-enabled)). Each case below logs a warning:

- A channel whose `id` is null is left out of `channel_campaigns`, because the bulk check finds each channel by
  its ID. An online check does not read that ID.
- A campaign that is null, or whose `id` is null, is left out, because `Channel` finds each campaign in
  `Twitch._campaigns` by its ID.

A null `data`, `channel` or `viewerDropCampaigns` lists no campaigns, without a warning. A stream whose
campaigns were left out counts as not drops enabled until its next check, as a stream with no campaigns does.
No case adds a request.

## Invariants

- No function changes its argument. The readers build new dicts but share the other values, such as lists,
  with their arguments.
- No function sends a request, and no caller sends one again for a null item: a game with a null directory
  waits for the next `CHANNELS_FETCH`. A null playback token is requested again only for the `Stream` that the
  online check stores ([channel.md](channel.md#a-null-playback-token)). A channel read as offline sends no
  request of its own until a websocket event starts an online check ([Null stream fields](#null-stream-fields)).

**Dependencies.** `gqldata` (`get_field`). `constants` (`JsonType`) is imported for type checking only.
