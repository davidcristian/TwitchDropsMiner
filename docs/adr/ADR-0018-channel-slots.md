# ADR-0018: The channels kept at the channel limit

**Status:** Accepted (2026-10-25)

## Context

The app tracks at most `MAX_CHANNELS` channels, 199, because each tracked channel takes two PubSub topics and
the websocket pool holds 398 ([websocket.md](../modules/websocket.md#the-199-channel-limit)). Only a tracked
channel sends the `stream-up` event that starts its online check, and only a tracked channel can be watched.
`State.CHANNELS_FETCH` collects the ACL channels of the wanted campaigns, an ACL (access control list) being
the list of channels whose streams count toward a campaign's drops. It adds up to 20 live channels from the
game directory for each wanted game whose campaign has no ACL. When these number more than 199, the rest lose
their slot.

The fetch sorted the channels by priority, ACL first, then viewers, and kept the first 199. An offline channel
has no game, so `Twitch.get_priority` gives it `MAX_INT`, and every offline ACL channel sorted after every live
channel of a wanted game. The directory channels of the last games on the Priority list then took the slots of
the offline ACL channels of the first ones. Such a channel was found at the next stream refresh, or at the next
reload with the refresh off, instead of about 2 minutes after its stream started. Mining many games makes this
likely: ten games without an ACL list up to 200 directory channels.

Keeping the offline ACL channels has a cost of its own. When the channels of the best game all end their
streams before the next channel fetch, the live channels of the next games can be off the list. The app then
watched a channel of a game further down the list, or none, until the next stream refresh, up to 6 minutes
later with the default `refresh_interval` ([ADR-0003](ADR-0003-stream-refresh.md)).

## Decision

1. **The list keeps its order.** The channel list shows the kept channels by priority, ACL first, then
   viewers, as before. Only the choice of the channels that lose their slot changes.
2. **The channels that `CHANNEL_SWITCH` can watch next keep their slots first.** These are the channels that
   `can_watch` accepts with the best priority among them, and the selected channel when `can_watch` accepts
   it. So the limit never removes the channel that the switch would watch, or the one the user selected.
3. **Every other channel keeps its slot by the priority of a game.** A live channel of a wanted game ranks with
   its game. An ACL channel that is offline, or streams a game that is not wanted, ranks with the best of the
   wanted games whose campaigns list it. Any other channel ranks last. At equal priority the list order
   decides, so a live channel comes before an offline one. So an offline ACL channel keeps its slot ahead of
   the live channels of games with a lower priority than its campaign's, and behind those of the same game or
   a higher one. `Twitch._slot_order` returns this order, and `CHANNELS_FETCH` keeps the first 199 channels in
   it.
4. **A stop of the watched channel starts a stream refresh at once when a channel off the list is better.**
   `CHANNELS_FETCH` stores in `_cut_priority` the best priority of the channels it leaves off the list that
   `can_watch` accepts. When the watched channel ends its stream or can no longer be watched,
   `on_channel_update` sets `_watched_stopped`. The `CHANNEL_SWITCH` that follows clears it, and when its
   choice is no channel, or a channel of a lower priority than `_cut_priority`, it stops watching and enters
   `CHANNELS_CLEANUP` instead. That stream refresh ends in a `CHANNEL_SWITCH`, which watches the first choice
   when the refresh finds no better channel. A selected channel that `can_watch` accepts is watched without a
   refresh, because every switch watches it.
5. **The setting "Never (hourly reload only)" turns this refresh off too.** With it, the channel fetch runs
   only at a reload, a campaign time and a change of the detected games
   ([ADR-0003](ADR-0003-stream-refresh.md#consequences)), and a user chooses it for the fewest requests.

## Consequences

- The order sends no request. When an ACL channel takes the slot of a directory channel, one ACL channel fewer
  is left off the list, and the stream refresh checks the channels left off the list again each time
  ([ADR-0003](ADR-0003-stream-refresh.md#consequences)), one `GetStreamInfo` request per 20. A directory
  channel that loses its slot costs nothing, because each refresh sends its `GameDirectory` request anyway.
- A tracked ACL channel sends its own events instead: a `stream-up` event starts an online check
  ([channel.md](../modules/channel.md#after-a-stream-up-event)).
- The refresh at a stop costs what a stream refresh costs ([ADR-0003](ADR-0003-stream-refresh.md#consequences)):
  one `GameDirectory` request per wanted game whose campaign has no ACL, and one `GetStreamInfo` request per
  20 ACL channels off the list. It runs at most once per stop of the watched channel. The switch at its end
  finds `_watched_stopped` cleared, and no better channel off the list either, because the fetch keeps first
  the channels that this switch can watch.
- The switch requests the refresh through `change_state` ([ADR-0017](ADR-0017-state-requests.md)), so an
  exit, a restart or a reload requested in the same pass runs first, and a reload ends in its own switch.
  `_maintenance_task` keeps its schedule, so the next scheduled refresh comes when it would without this one.
- No channel is watched while the requests of the refresh run. At 5 GQL requests per second, each 100 ACL
  channels off the list add one second.
- With the refresh set to "Never", the gap stays: the app watches a channel of a game further down the list,
  or none, until the next channel fetch, at most an hour later.
- Offline ACL channels of the same game have the same rank, so the set order decides which of them keep a
  slot, as before.

## Alternatives rejected

- **Directory channels lose their slots first.** When the ACLs of the wanted campaigns list 199 channels or
  more, the fetch then keeps no directory channel, and the app watches nothing while a game without an ACL
  streams.
- **Every channel ranks by a game's priority, with no channels kept first.** A campaign whose ACL lists 199
  offline channels or more then takes every slot, and the app watches nothing while a game with a lower
  priority streams. Campaigns with about 1200 ACL channels exist
  ([ADR-0002](ADR-0002-twitch-traffic-budget.md#context)).
- **Watching the first choice while the refresh runs.** It sends a watch request to a channel that the
  refresh's switch can replace a second later, and prints a second "Watching" line.
- **The refresh at a stop with the setting at "Never".** It closes the gap for that setting too, but adds a
  channel fetch that the name of the setting rules out.

## Related

- [twitch.md](../modules/twitch.md#state-machine): `CHANNELS_FETCH` and the cut.
- [websocket.md](../modules/websocket.md#the-199-channel-limit): where the limit of 199 comes from.
- [ADR-0003](ADR-0003-stream-refresh.md): the stream refresh, which checks the ACL channels left off the list.
- [ADR-0017](ADR-0017-state-requests.md): `change_state`, through which the switch requests the refresh.
- [001-offline-acl-channels-trimmed-first.md](../refinements/tasks/001-offline-acl-channels-trimmed-first.md):
  the task this decision closed.
- [079-watched-channel-on-a-lower-game-stays-watched.md](../refinements/tasks/079-watched-channel-on-a-lower-game-stays-watched.md):
  a watched channel that changes to a game of a lower priority, which gets no refresh at once.
