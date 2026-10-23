# ADR-0009: Watching by playlist HEAD requests

**Status:** Accepted (2026-10-23)

## Context

A drop progresses while the account watches a live stream that counts toward the drop's campaign. The app has
to make Twitch count the account as a viewer of one channel without playing the video. `channel/` holds
three ways to do this:

- **Playlist HEAD requests,** `Channel.send_watch`: get the stream's video playlist as a video player does,
  and send a `HEAD` request, which returns only the headers, for each video segment in it.
- **Spade,** `Channel._send_watch_spade`: POST a `minute-watched` event, encoded in base64, to the spade URL
  that `get_spade_url` reads from the channel page or from the settings script it links.
- **GQL,** `Channel._send_watch_gql`: send the same event with the `sendSpadeEvents` GQL mutation.

The original project has switched between these methods five times since 2024-06-22
([task 022](../refinements/tasks/022-unused-code.md#how-it-came-about) lists the commits). The last switch,
"Change the mining method to playlist HEAD requests" (2026-10-09), made `send_watch` the HEAD method with a
`HEAD` request for every segment instead of only the last one, and changed `WATCH_INTERVAL` from 59 to 20
seconds. This project took it and changed two things: an online check after a failed playlist request, and a
watch restart that counts at any time in a cycle.
None of the five commits has a message body, so the code comments are the only written reasons, quoted below.

## Decision

1. **`Channel.send_watch` is the watch method.** `Twitch._watch_loop` calls it and no other method. One call:
   1. Calls `Stream.get_stream_url()`. The first call for a `Stream` object sends one `PlaybackAccessToken`
      GQL query with the channel login, then GETs `https://usher.ttvnw.net/api/channel/hls/<login>.m3u8` with
      the token and its signature. The code comment calls the response "a list of all available stream
      qualities". The method keeps its last line, "usually with the lowest quality stream" in the comment's
      words, and stores it on the `Stream`. Once it is stored, later calls for the same `Stream` send nothing.
   2. GETs that playlist with the header `Connection: close`. The code comment says the server closes the
      connection shortly after it sends the list.
   3. Sends one `HEAD` request for each line of the playlist that starts with `http`, one at a time, in the
      playlist's order. The code comment counts "~15 chunks of the stream at ~2s intervals", and says a `HEAD`
      request "is enough to advance the drops, without downloading the actual stream data".

   It returns False when the playlist request returns a status of 400 or more or JSON, or at the first
   segment request that returns a status other than 200, and True when every segment returned 200.

   After a playlist status of 400 or more, when no online check waits, it also clears the stored playlist
   URL and calls `check_online()`. The code comment says the playlist returns 404 once the stream has ended.
   This step stops a missed `stream-down` event from keeping the app on an ended stream until the next reload.

2. **A cycle starts every `WATCH_INTERVAL`, 20 seconds** (`constants.py`). The `send_watch` docstring says:
   "Optimally, send every ~20 seconds to advance drops." `_watch_loop` notes the time and awaits `send_watch`.
   Once 15 seconds have passed since the noted time, it sends one `CurrentDrop` GQL query when
   `gui.progress.minute_almost_done()` is True: the minute countdown has stopped or has at most 10 seconds
   (`ALMOST_DONE_SECONDS`) left. It then waits until 20 seconds after the noted time, or not at all when
   `send_watch` took longer. `restart_watching` ends only that last wait. A call earlier in the cycle ends it
   as soon as it starts, because the loop clears the event that the call sets only as it sends the next watch
   request. So the `CurrentDrop` check keeps its place, and a call starts the next cycle at most 5 seconds
   early.

3. **The Spade and GQL methods stay in `channel/watch.py` with no caller.** No code calls them, or `get_spade_url`,
   `Channel.url`, `Stream.spade_payload`, `Stream.gql_payload` and `Stream._watch_payload`, which only they
   use. Keeping them sends the same requests as removing them would, and changes less code. If Twitch stops
   counting the HEAD requests, a switch back starts from a method that exists, and an upstream fix to one of
   them applies without a conflict ([upstream-fixes.md](../runbooks/upstream-fixes.md)). A comment
   above each method says why it stays. The comment `# async def _send_watch_playlist(self) -> bool:` above
   `send_watch` is the HEAD method's name from 2026-04-28 to 2026-10-09.

## Consequences

### The cost of watching

One cycle, once the `Stream` has its playlist URL, sends:

- 1 GET of the playlist and 1 `HEAD` per segment: about 16 requests with the code comment's count of 15
  segments. `Twitch.request` sends them to the hosts that the usher response and the playlist name. None of them
  passes the GQL limiter.
- At most 1 `CurrentDrop` query, through `Twitch.gql_request` and its limiter of 5 per second
  ([ADR-0002](ADR-0002-twitch-traffic-budget.md)).

A new `Stream` object adds 1 `PlaybackAccessToken` query and 1 GET of the usher list. The watched channel gets
a new `Stream` object when a full reload builds the channel list again, and when `update_stream` runs for it,
`ONLINE_DELAY` (120 seconds) after a `stream-up` or `broadcast-settings-update` PubSub event or a failed
playlist request ([channel.md](../modules/channel.md#online-checks)). A stream refresh keeps each tracked
`Channel` object that its cleanup does not remove, with its `Stream` ([ADR-0003](ADR-0003-stream-refresh.md)).

At one cycle per 20 seconds, an hour has 180 cycles: 180 playlist GETs and about 2700 `HEAD` requests, about
2880 HTTP requests in all, and at most 180 `CurrentDrop` queries. These figures are counted from the code and
the comment's segment count. Nothing in this repo measures the segment count of a real playlist.

A `restart_watching` call adds at most one cycle, because it starts the next cycle at most 5 seconds early.
`process_drops` calls it after a drop claim whose campaign continues on the channel, and `State.GAMES_UPDATE`
after each reload and each change of the detected games.

A playlist request that fails every cycle while `GetStreamInfo` still returns the stream adds, per online check
of about 120 seconds, 1 `GetStreamInfo` and 2 each of `PlaybackAccessToken` and the usher GET: one after the
URL is cleared, one for the `Stream` object that the check stores. That is at most 30, 60 and 60 an hour, plus
30 `AvailableDrops` with the extra drops check on. While a check waits, a failed playlist request clears
nothing, so usher is not requested every cycle.

A `PlaybackAccessToken` response with a null token sends no usher GET and starts an online check. The `Stream`
sends no second token query, so a token that stays null adds 1 `PlaybackAccessToken` and 1 `GetStreamInfo` per
check: at most 30 of each an hour, plus 30 `AvailableDrops` with the extra drops check on
([channel.md](../modules/channel.md#a-null-playback-token)).

### What else follows

- The requests of one call go one at a time. `Twitch.request` retries a status of 500 or more, or a connection
  error, with backoff up to 3 minutes, so a failing server makes the cycle longer and sends none in parallel.
- A failed watch is logged at the `CALL` level as "Watch requested failed for channel", and the loop goes on.
  The `stream-down` event sets the channel offline, and the next cycle stops watching it. When that event is
  missed, the next cycle requests usher, because decision 1 cleared the stored URL, and `get_stream_url` sets
  the channel offline when usher returns an error. When usher still lists a playlist, the online check sets
  the channel offline 120 seconds later, once `GetStreamInfo` returns no stream. A failed segment request
  changes nothing.
- An exception from `send_watch`, or one other than `GQLException` from the `CurrentDrop` check, ends
  `_watch_loop`, which runs under `task_wrapper(critical=True)`, and so ends the run as a fatal error
  ([ADR-0006](ADR-0006-restart-after-fatal-error.md)). After a failed playlist request,
  `PlaybackAccessToken` is sent for a stream that may have ended. A null token fails the cycle and starts an
  online check, as above, and nothing in this repo shows whether Twitch returns a token for an ended stream.
- The README warns against watching a stream on the account the app uses ([Notes](../../README.md#notes)). No
  code comment or commit links that warning to a watch method, so this record states nothing about it.

## Alternatives rejected

- **Removing the Spade and GQL methods.** It sends no fewer requests, a switch back would have to write a
  method again, and an upstream fix to one of them would conflict when it is brought in.
- **Going back to Spade or GQL to send fewer requests.** After the first cycle, either one sends one request
  per cycle in place of about 16. The original project switched away from each of them without a written
  reason, and nothing in this repo shows that Twitch still counts their events.
- **One `HEAD` request for the last segment only.** The HEAD method did this while it was in use from
  2024-06-22 to 2025-08-17, and the 2026-10-09 commit changed it to every segment without a written reason.
  Nothing here shows that Twitch counts one segment today.
- **Ending the 15 second wait on a restart too.** The next watch request would go out at once, but the
  `CurrentDrop` check would then come with no time for a progress update, and each call would start the next
  cycle up to 20 seconds early instead of 5, which sends more requests.

## Related

- [channel.md](../modules/channel.md#watching), [twitch.md](../modules/twitch.md#watch-loop),
  [constants.md](../modules/constants.md#intervals-and-limits) and
  [ARCHITECTURE.md](../ARCHITECTURE.md#twitch-traffic).
- [ADR-0002](ADR-0002-twitch-traffic-budget.md): the GQL limiter. [ADR-0010](ADR-0010-device-code-login.md):
  the user agent that every request sends. [How It Works](../../README.md#how-it-works) in the README.
- [gql-operations.md](../runbooks/gql-operations.md): the `PlaybackAccessToken` and `CurrentDrop` hashes.
  [upstream-fixes.md](../runbooks/upstream-fixes.md): bringing in a change of method from upstream.
- Tasks [022](../refinements/tasks/022-unused-code.md) (the code that nothing calls, which kept these methods) and
  [013](../refinements/tasks/013-crashed-task-ends-the-app.md) (an exception in the watch loop).
