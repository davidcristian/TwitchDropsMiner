# `channel/`

**Purpose.** `Channel` is one Twitch channel the app tracks, and `Stream` is that channel's current broadcast.
The package checks whether a channel is live, keeps its game, title, viewer count and drops status, and sends the
watch requests that make drop progress. `Twitch` keeps the tracked channels in `Twitch.channels`
([twitch.md](twitch.md)).

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | Imports `Channel` and `Stream`. Callers import from `channel`, never from a file of it |
| `tracked.py` | `Channel`: its attributes, its properties, `display`, `cancel_online_check` and `remove` |
| `online.py` | `OnlineMixin`, a base class of `Channel` that holds its [online checks](#online-checks): `get_stream`, `update_stream`, `external_update`, `check_online`, `set_offline` and their helpers |
| `watch.py` | `WatchMixin`, a base class of `Channel` that holds its [watch requests](#watching): `send_watch`, `get_spade_url`, `_send_watch_spade` and `_send_watch_gql` |
| `stream.py` | `Stream`, its playlist URL and the watch payloads |

## Public contract

### `Channel`

- `Channel(twitch, *, id, login, display_name=None, acl_based=False)`.
- `Channel.from_acl(twitch, data)` builds a channel from a campaign's ACL (access control list, the channels a
  campaign allows), with `acl_based=True` and no stream.
- `Channel.from_directory(twitch, data, *, drops_enabled=False)` builds a live channel, with its `Stream`, from a
  `GameDirectory` result that `directory_streams` read ([streamdata.md](streamdata.md#null-stream-fields)).
- Two channels are equal when their `id` is equal, and the hash is the `id`.
- Properties: `id`, `name` (the display name, or the login), `url`, `iid` (the row key in the GUI channel list),
  `game`, `viewers` (settable), `drops_enabled`, `acl_based`, and `stream_gql`, the `GetStreamInfo` operation for
  this channel.
- Status: `online` is True when the channel has a `Stream`. `pending_online` is True while an online check is
  pending and there is no stream yet; the channel list shows it as `OFFLINE ⏳`. `offline` is True when neither is.
- `check_online()` starts the delayed check [below](#after-a-stream-up-event), unless one is already pending.
- `cancel_online_check()` cancels a pending check. `set_offline()` cancels it too, and when the channel was
  online, it drops the stream and calls `Twitch.on_channel_update`.
- `get_stream()` fetches the stream with GQL and returns it, or None when the channel is offline or its stream
  has a null ID ([streamdata.md](streamdata.md#null-stream-fields)). `update_stream(*, tries=1)` stores that
  result, calls `Twitch.on_channel_update(channel, before, after)` and returns True when the channel is online.
  A channel that was offline is fetched up to `tries` times, `ONLINE_DELAY` apart, while it has no stream.
- `external_update(channel_data, available_drops)` sets the stream from the `GetStreamInfo` data that
  [`bulk_check_online`](#bulk-check) fetched, or drops it when that data has no stream.
- `send_watch()` sends one watch cycle; see [Watching](#watching).
- `display(*, add=False)` adds or updates the channel's row in the GUI. `remove()` removes the row and cancels a
  pending check.

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
  `can_earn(channel, ignore_channel_status=True)` is True. A null `channel` in the response lists no campaigns,
  and a null campaign or campaign ID is left out ([streamdata.md](streamdata.md#null-available-drops)).
- A stream from `GameDirectory` takes `drops_enabled` from the caller instead. `CHANNELS_FETCH` queries the
  directory with the `DROPS_ENABLED` filter and passes True.

## Online checks

These change a channel's status:

1. `CHANNELS_FETCH` in `Twitch._run` creates directory channels with their stream, and checks the untracked
   ACL channels with [`bulk_check_online`](#bulk-check).
2. On the websocket ([websocket.md](websocket.md#topics)), `Twitch.process_stream_state` calls `check_online()`
   for a `stream-up` event and for a `viewcount` event on a channel that is not online. It calls `set_offline()`
   for `stream-down`, and stores the viewer count of a `viewcount` event on an online channel.
3. `Twitch.process_stream_update` calls `check_online()` for every message on the `broadcast-settings-update`
   topic, to read the new title, game and drops status. The delay groups several changes in a row into one fetch.
4. `Stream.get_stream_url` calls `set_offline()` when the request for the stream qualities returns an error,
   and `check_online()` when the token is null ([A null playback token](#a-null-playback-token)).
5. `send_watch` calls `check_online()` when the watched channel's playlist request fails
   ([Watching](#watching)).

### After a stream-up event

Twitch sends `stream-up` before the stream data is available, as the `pending_online` docstring says. So
`check_online` does not fetch at once. It starts `_online_delay`, which waits `ONLINE_DELAY` (120 seconds) and
then calls `update_stream` with `ONLINE_TRIES` (3). `update_stream` sends one `GetStreamInfo` query, plus
`AvailableDrops` when the extra check is on and the channel is live. The stream data can come more than 120
seconds after the event, so when a channel that was offline still has no stream, `update_stream` waits
`ONLINE_DELAY` and sends the query again, up to 3 queries in all. A channel that was online gets one query, in
which no stream means that its stream ended. The check stays pending until its last request returns, so events
during the waits or the requests start no second check, and a cancelled check stores no result. The check ends
before `update_stream` passes the old and new stream to `Twitch.on_channel_update`, so the row shows the new
status:

- Offline to online: `Twitch` watches the channel when `should_switch` allows it, and prints
  "`{channel} goes ONLINE, switching...`".
- Offline to offline, after the third query: `update_stream` logs "`{channel} has no stream after 3 checks`" at
  `INFO`. Nothing checks the channel again until its next websocket event, such as a `viewcount`, or until
  `CHANNELS_FETCH` adds it anew, which for a tracked ACL channel is the next reload.
- Online before the check, after a settings update or a failed playlist request: when the watched channel can
  no longer be watched, or streams a game of a lower priority than before, `Twitch` enters
  `State.CHANNEL_SWITCH`, and prints "`{channel} goes OFFLINE, switching...`" when the stream ended.
  Another channel that is still online is watched when `should_switch` allows it.

A query that raises `MinerException` ends the check without a further try, because `Twitch.request` and
`Twitch.gql_request` already retry a timeout, a connection error, a 5xx status and a `service error`
([twitch.md](twitch.md#gql-requests)). `_online_delay` logs the error at `WARNING` with its traceback and
updates the row, and the stream stays as it was. An error that wraps an `ExitRequest`, from a window that is
closing, ends the check with no log line.

One check sends at most 3 `GetStreamInfo` queries in 6 minutes, 2 more than a single try, and the 2 go out only
while an offline channel has no stream. Each query follows a wait of 120 seconds, and a channel has one check at
a time, so one channel still sends at most 30 an hour ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)).

## Bulk check

`Twitch.bulk_check_online(channels)`, in `twitch/`, checks many channels at once. It sends their `stream_gql`
operations in batches of 20 per GQL request. With the extra drops check on, it also sends `AvailableDrops` for the
online channels, again 20 per request. So `n` channels cost `ceil(n / 20)` GQL requests, plus one per 20 online
channels with the extra check.

It then calls `external_update` on each channel in the response, with no campaigns for one whose `AvailableDrops`
result or channel ID is null ([streamdata.md](streamdata.md#null-available-drops)). `external_update` drops the
stream of an offline channel, so a channel that went offline after the cut at `MAX_CHANNELS` ranks as offline at
the next `CHANNELS_FETCH`. A channel missing from the response, because its `user` or the user's `id` is null,
keeps its current stream: a server error also sets `user` to null
([streamdata.md](streamdata.md#null-stream-fields)).

`external_update` does not call `Twitch.on_channel_update`. `CHANNELS_FETCH` handles the new status after the
check instead: it displays each channel it keeps, stops watching the watched channel when `can_watch` fails for
it, and then enters `CHANNEL_SWITCH`.

## Watching

`Twitch._watch_loop` calls `send_watch()` on the watched channel every `WATCH_INTERVAL` (20 seconds).
`send_watch` requests the stream the way a video player does, without downloading the video:

1. `Stream.get_stream_url()`. On the first call for a `Stream`, it sends a `PlaybackAccessToken` GQL query for
   the channel login, then GETs `https://usher.ttvnw.net/api/channel/hls/<login>.m3u8` with the token and its
   signature. The response lists the stream qualities. The method keeps the last URL in the list, which the code
   comment says is usually the lowest quality, and caches it on the `Stream`. For a JSON response it returns
   None. When that response has an `error` key, the error is logged and the channel is set offline. For a null
   token it returns None ([A null playback token](#a-null-playback-token)).
2. A GET of that media playlist with `Connection: close`. A status of 400 or above returns False; the playlist
   returns 404 once the stream has ended. `Twitch.request` retries a status of 500 or above, so only a 4xx
   status gets here. For a JSON response it also returns False.
3. A HEAD request to each segment URL in the playlist, which is each line that starts with `http`. The code
   comment counts about 15 segments of about 2 seconds each. A status other than 200 returns False.

`send_watch` returns True when every HEAD request returned 200. The playlist and segment requests go through
`Twitch.request`, so they use the proxy and the retries but not the GQL rate limiter. After the first cycle of a
stream, a cycle sends one GET and about 15 HEAD requests to the hosts the playlist names, and no GQL request.

Two other watch methods stay, and nothing calls them: `_send_watch_spade` POSTs a `minute-watched` event to the
spade URL that `get_spade_url` reads from the channel page, and `_send_watch_gql` sends the same event with the
`sendSpadeEvents` GQL mutation. They are kept in case Twitch stops counting the HEAD requests
([ADR-0009](../adr/ADR-0009-watch-method.md#decision)).

### A failed playlist request

A missed `stream-down` event leaves an ended stream online in the app. So when the playlist request returns a
status of 400 or above and no online check is pending, `send_watch` also clears the cached URL and calls
`check_online()`:

- The next cycle sends `PlaybackAccessToken` and the usher GET again. When usher returns an error,
  `get_stream_url` sets the channel offline, which cancels the check.
- Otherwise the check sends `GetStreamInfo` 120 seconds later. A response with no stream sets the channel
  offline. A response with a stream replaces the `Stream`, so the next cycle requests usher once more.
- While the check is pending, a failed playlist request clears nothing, so usher is not requested every cycle. A
  playlist that fails every cycle while Twitch reports the stream live costs at most 30 `GetStreamInfo`, 60
  `PlaybackAccessToken` and 60 usher GETs an hour ([ADR-0009](../adr/ADR-0009-watch-method.md#the-cost-of-watching)).
- Nothing changes when the channel's stream changed during the request, such as after a `stream-down` event.

### A null playback token

A server error can set `streamPlaybackAccessToken`, or its `value` or `signature`, to null
([streamdata.md](streamdata.md#public-contract)). `get_stream_url` then logs a warning, marks the `Stream`, calls
`check_online()` and returns None, so the cycle fails. For a marked `Stream` it sends no request: it calls
`check_online()` again, which starts a check only when none is pending, and returns None. The check stores a new
`Stream` when the channel is still live, and the next cycle requests a token for it.

So a token that stays null costs one `PlaybackAccessToken` and one `GetStreamInfo` query per check, at most 30
of each an hour, plus 30 `AvailableDrops` with the extra drops check on. No usher GET is sent. A check that
fails leaves the marked `Stream` in place, and the next cycle starts another one.

## Invariants

- A channel's identity is its `id`. `CHANNELS_FETCH` builds the channel list with sets, and `set.update` keeps
  the tracked object when a new one has the same `id`, so a tracked channel keeps its stream and its pending check.
- Each channel has at most one pending check (`_pending_stream_up`). `cancel_online_check()` cancels it, and
  `remove()` and `set_offline()` call it, so a removed channel does not call `on_channel_update` later. `Twitch`
  calls it for every channel in `shutdown`, and for each channel that `CHANNELS_FETCH` cuts at `MAX_CHANNELS`.
  It does not call `remove()` there, because a new channel that is cut has no row to remove.
- `Channel` uses `__slots__`, so a new attribute must be added to the `__slots__` tuple. Its mixins set
  `__slots__ = ()`, because a base class without `__slots__` gives every `Channel` a `__dict__`.
- Every GQL query goes through `Twitch.gql_request`, and every other request through `Twitch.request`
  ([ADR-0002](../adr/ADR-0002-twitch-traffic-budget.md)).
- `on_channel_update` ends with `display()`, so the GUI row matches the status after every change.

**Dependencies.** `streamdata` (`playback_token`, `channel_stream`, `available_campaigns`), `utils` (`Game`,
`json_minify`, `isonow`), `exceptions` (`ExitRequest`, `MinerException`, `RequestException`), `twitchapi`
(`GQL_QUERIES`, `GQLQuery`) and `constants` (`ONLINE_DELAY`, `ONLINE_TRIES`, `CALL`, `URLType`). Third party:
aiohttp and yarl.
`Twitch` and the GUI's `ChannelList` are imported for type checking only.
