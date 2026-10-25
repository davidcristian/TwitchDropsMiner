# A watched channel that changes to a game of a lower priority stays watched until the next switch

**Status:** open
**Area:** twitch
**Origin:** The stream refresh at a stop of the watched channel
([ADR-0018](../../adr/ADR-0018-channel-slots.md#decision)), on 2026-10-25
**Verified:** 2026-10-25

`on_channel_update` in [twitch/pubsub.py](../../../twitch/pubsub.py) enters `State.CHANNEL_SWITCH` for the
watched channel only when `can_watch` no longer accepts it. A watched channel that changes its stream to
another wanted game with a lower priority, whose campaign can progress on it, stays watched with no switch.
Another tracked channel of a game with a higher priority is then watched only when it sends an update of its
own that `should_switch` accepts, or at the next `CHANNEL_SWITCH`: the next stream refresh, at most 6 minutes
later with the default `refresh_interval`, a campaign time, a `Switch` press or a reload. With the refresh set
to "Never", that can be an hour later. At the channel limit, the channels of better games that
`CHANNELS_FETCH` left off the list wait in the same way, because the refresh at once runs only after a stop.

## What a fix involves

`on_channel_update` would enter `State.CHANNEL_SWITCH` also when the priority of the watched channel drops,
with `_watched_stopped` set, so that the switch watches a better tracked channel or refreshes at the limit.
The switch sends no request; a refresh at the limit costs what a stream refresh costs
([ADR-0003](../../adr/ADR-0003-stream-refresh.md#consequences)). It was left out of the change that added the
refresh at a stop, which covers a stream that ends or can no longer be watched.

## History

- 2026-10-25: Opened. Found while adding the stream refresh at a stop of the watched channel.
