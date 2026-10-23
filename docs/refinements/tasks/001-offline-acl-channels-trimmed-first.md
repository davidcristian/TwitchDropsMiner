# Offline ACL channels are trimmed first

**Status:** done 2026-10-22
**Area:** twitch (channel selection)
**Origin:** [ADR-0003](../../adr/ADR-0003-stream-refresh.md)
**Verified:** 2026-10-22

A campaign's ACL (access control list) is its `allowed_channels` list, and only the channels on it can
progress that campaign. These are ACL channels. The app tracks at most `MAX_CHANNELS` channels, because each
tracked channel uses two PubSub topics (`TOPICS_PER_CHANNEL`) and the websocket pool holds `MAX_TOPICS`. With
the values in `constants.py` (`MAX_WEBSOCKETS` 8, `WS_TOPICS_LIMIT` 50, `BASE_TOPICS` 2) that is
`(8 * 50 - 2) // 2` = 199 channels.

In the `State.CHANNELS_FETCH` branch of `Twitch._run` in [twitch/client.py](../../../twitch/client.py), the channel list is
sorted three times and then cut to its first `MAX_CHANNELS` entries. The sorts are by viewers (descending), by
`acl_based` (ACL first) and by `Twitch.get_priority`. Python's sort is stable, so the last sort sets the order
and the earlier ones only order channels that tie in it. `get_priority` returns `MAX_INT` when `channel.game`
is `None`, and `Channel.game` is `None` for every offline channel. So every offline ACL channel ranks below
every online channel of a wanted game, including the up to 20 live channels that `get_live_streams` returns
for each game whose campaign has no ACL. The cut removes offline ACL channels first. All offline ACL channels
have the same three sort keys, so which of them keep a slot depends on set iteration order.

A channel that is cut gets no `StreamState` or `StreamUpdate` subscription, so its `stream-up` event never
arrives. A subscribed channel is found `ONLINE_DELAY` (120 seconds) after that event, when that one check
succeeds ([002](002-online-delay-single-try.md)). A cut channel is found only by the next
`State.CHANNELS_FETCH`: there `acl_channels.difference_update(new_channels)` leaves every untracked ACL
channel in the set that `bulk_check_online` queries. When to expect that pass:

- With the default `refresh_interval` of 5, `_maintenance_task` changes the state to `State.CHANNELS_CLEANUP`,
  which moves on to `State.CHANNELS_FETCH`, every 5 minutes plus up to 60 seconds (`REFRESH_JITTER`).
- With the setting at "Never (hourly reload only)", it runs at the next reload, or earlier at the start or end
  time of a campaign or drop (`_mnt_triggers`).

Each of those passes queries every cut channel again. `bulk_check_online` sends 20 operations per request, so
a pass costs one extra GQL request per 20 cut channels. When `available_drops_check` is on, it adds one
`AvailableDrops` request per 20 cut channels that are online.

The cut happens only when the ACL lists of the wanted campaigns and the directory channels add up to more than
199 channels. Mining many games at once makes that more likely. One campaign with a long ACL list can reach it
on its own.

A fix decides which channels give up their slot. The directory channels of games without an ACL are the
candidates, because `get_live_streams` finds them again on every pass and they need no subscription to be
found. Changing the sort order costs no Twitch requests. Any fix keeps the cost of a pass within the budget in
[ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md).

Deferred on 2026-08-03, when the new stream check in ADR-0003 was added: the smallest change that fixes the
common case was chosen. See [twitch.md](../../modules/twitch.md) for the state machine.

## History

- 2026-08-03: Found and deferred when the new stream check was decided.
- 2026-10-18: Opened. Written down while the docs were written. Checking it against the code showed that the
  refresh queries the cut channels again, so they are found at the next pass, not only at the next reload.
- 2026-10-22: Done. Checked against the code first: the three sorts, `get_priority` and the cut were as
  described. `CHANNELS_FETCH` now keeps first the channels that `CHANNEL_SWITCH` can watch next, which are those
  of the best game that `can_watch` accepts and the selected one, and ranks the others by the priority of a
  game, an offline ACL channel by that of its campaign. The channel list keeps its order
  ([ADR-0018](../../adr/ADR-0018-channel-slots.md)). Twitch requests: none added.
