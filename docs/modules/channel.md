# `channel.py`

**Purpose.** `Channel` is one Twitch channel the app tracks, and `Stream` is that channel's current broadcast.
The module checks whether a channel is live, keeps its game, title, viewer count and drops status, and sends the
watch requests that make drop progress. `Twitch` keeps the tracked channels in `Twitch.channels`
([twitch.md](twitch.md)).

## Public contract

### `Channel`

- `Channel(twitch, *, id, login, display_name=None, acl_based=False)`.
- `Channel.from_acl(twitch, data)` builds a channel from a campaign's ACL (access control list, the channels a
  campaign allows), with `acl_based=True` and no stream.
- `Channel.from_directory(twitch, data, *, drops_enabled=False)` builds a live channel, with its `Stream`, from a
  `GameDirectory` result.
- Two channels are equal when their `id` is equal, and the hash is the `id`.
- Properties: `id`, `name` (the display name, or the login), `url`, `iid` (the row key in the GUI channel list),
  `game`, `viewers` (settable), `drops_enabled`, `acl_based`, and `stream_gql`, the `GetStreamInfo` operation for
  this channel.
- Status: `online` is True when the channel has a `Stream`. `pending_online` is True while an online check waits
  and there is no stream yet; the channel list shows it as `OFFLINE ⏳`. `offline` is True when neither is.
- `check_online()` starts the delayed check [below](#after-a-stream-up-event), unless one is already waiting.
- `set_offline()` cancels a waiting check. When the channel was online, it drops the stream and calls
  `Twitch.on_channel_update`.
- `get_stream()` fetches the stream with GQL and returns it, or None when the channel is offline.
  `update_stream()` stores that result, calls `Twitch.on_channel_update(channel, before, after)` and returns True
  when the channel is online.
- `external_update(channel_data, available_drops)` sets the stream from data fetched elsewhere, by
  [`bulk_check_online`](#bulk-check).
- `send_watch()` sends one watch cycle; see [Watching](#watching).
- `display(*, add=False)` adds or updates the channel's row in the GUI. `remove()` removes the row and cancels a
  waiting check.

### `Stream`

`Stream(channel, *, id, game, viewers, title)` has `broadcast_id`, `game`, `viewers`, `title` and
`drops_enabled`. `Stream.from_get_stream(channel, channel_data)` builds one from a `GetStreamInfo` result, and
`Stream.from_directory` from a `GameDirectory` result. Two streams are equal when their `broadcast_id` is equal.
`get_stream_url()` returns the playlist URL that `send_watch` uses, or None.

## Drops enabled

`Stream.drops_enabled` starts as `not settings.available_drops_check`:

- With "Enable extra available drops check" off (the default), every stream counts as drops enabled, and no
  extra request is sent.
- With it on, `get_stream` sends one more GQL query, `AvailableDrops`. The stream counts as drops enabled when
  one of the campaigns it lists is in `Twitch._campaigns` and that campaign's
  `can_earn(channel, ignore_channel_status=True)` is True.
- A stream from `GameDirectory` takes `drops_enabled` from the caller instead. `CHANNELS_FETCH` queries the
  directory with the `DROPS_ENABLED` filter and passes True.

## Online checks

These change a channel's status:

1. `CHANNELS_FETCH` in `Twitch._run` creates directory channels with their stream, and checks new ACL channels
   with `bulk_check_online`.
2. On the websocket ([websocket.md](websocket.md#topics)), `Twitch.process_stream_state` calls `check_online()`
   for a `stream-up` event and for a `viewcount` event on a channel that is not online. It calls `set_offline()`
   for `stream-down`, and stores the viewer count of a `viewcount` event on an online channel.
3. `Twitch.process_stream_update` calls `check_online()` for every message on the `broadcast-settings-update`
   topic, to read the new title, game and drops status. The delay groups several changes in a row into one fetch.
4. `Stream.get_stream_url` calls `set_offline()` when the request for the stream qualities returns an error.

### After a stream-up event

Twitch sends `stream-up` before the stream data is available, as the `pending_online` docstring says. So
`check_online` does not fetch at once. It starts `_online_delay`, which waits `ONLINE_DELAY` (120 seconds) and
then calls `update_stream` once. More events during the wait start no second wait. `update_stream` sends one
`GetStreamInfo` query, plus `AvailableDrops` when the extra check is on, and passes the old and new stream to
`Twitch.on_channel_update`:

- Offline to online: `Twitch` watches the channel when `should_switch` allows it, and prints
  "`{channel} goes ONLINE, switching...`".
- Offline to offline: the result is only logged. Nothing checks the channel again until its next websocket
  event, such as a `viewcount`, or until `CHANNELS_FETCH` adds it anew. A tracked ACL channel stays tracked, so
  that happens at the next reload ([task 002](../refinements/tasks/002-online-delay-single-try.md)).
- Online before the check, after a settings update: when the watched channel can no longer be watched, `Twitch`
  enters `State.CHANNEL_SWITCH`, and prints "`{channel} goes OFFLINE, switching...`" when the stream ended.
  Another channel that is still online is watched when `should_switch` allows it.

## Bulk check

`Twitch.bulk_check_online(channels)`, in `twitch.py`, checks many channels at once. It sends their `stream_gql`
operations in batches of 20 per GQL request. With the extra drops check on, it also sends `AvailableDrops` for the
online channels, again 20 per request. It then calls `external_update` on each online channel. A channel that is
offline or missing in the response keeps its current stream. So `n` channels cost `ceil(n / 20)` GQL requests,
plus one per 20 online channels with the extra check.

## Watching

`Twitch._watch_loop` calls `send_watch()` on the watched channel every `WATCH_INTERVAL` (20 seconds).
`send_watch` requests the stream the way a video player does, without downloading the video:

1. `Stream.get_stream_url()`. On the first call for a `Stream`, it sends a `PlaybackAccessToken` GQL query for
   the channel login, then GETs `https://usher.ttvnw.net/api/channel/hls/<login>.m3u8` with the token and its
   signature. The answer lists the stream qualities. The method keeps the last URL in the list, which the code
   comment says is usually the lowest quality, and caches it on the `Stream`. A JSON answer returns None. When it
   has an `error` key, the error is logged and the channel is set offline.
2. A GET of that media playlist with `Connection: close`. A status of 400 or above returns False; the playlist
   returns 404 once the stream has ended. A JSON answer also returns False.
3. A HEAD request to each segment URL in the playlist, which is each line that starts with `http`. The code
   comment counts about 15 segments of about 2 seconds each. A status other than 200 returns False.

`send_watch` returns True when every HEAD request returned 200. The playlist and segment requests go through
`Twitch.request`, so they use the proxy and the retries but not the GQL rate limiter. After the first cycle of a
stream, a cycle sends one GET and about 15 HEAD requests to the hosts the playlist names, and no GQL request.

Two other watch methods remain, and nothing calls them: `_send_watch_spade` POSTs a `minute-watched` event to the
spade URL that `get_spade_url` reads from the channel page, and `_send_watch_gql` sends the same event with the
`sendSpadeEvents` GQL mutation ([task 022](../refinements/tasks/022-unused-code.md)).

## Invariants

- A channel's identity is its `id`. `CHANNELS_FETCH` builds the channel list with sets, and `set.update` keeps
  the tracked object when a new one has the same `id`, so a tracked channel keeps its stream and its waiting check.
- Each channel has at most one waiting check (`_pending_stream_up`). `remove()` and `set_offline()` cancel it, so
  a removed channel does not call `on_channel_update` later. A tracked channel that `CHANNELS_FETCH` cuts at
  `MAX_CHANNELS` loses its topics but does not go through `remove()`, so its waiting check still runs.
- `Channel` uses `__slots__`, so a new attribute must be added to the `__slots__` tuple.
- Every GQL query goes through `Twitch.gql_request`, and every other request through `Twitch.request`
  ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)).
- `on_channel_update` ends with `display()`, so the GUI row matches the status after every change.

**Dependencies.** `utils` (`Game`, `json_minify`, `isonow`), `exceptions` (`MinerException`,
`RequestException`) and `constants` (`GQL_QUERIES`, `ONLINE_DELAY`, `CALL`, `URLType`, `GQLQuery`). Third party:
aiohttp and yarl. `Twitch` and the GUI's `ChannelList` are imported for type checking only.
