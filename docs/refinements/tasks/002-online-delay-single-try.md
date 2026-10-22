# A stream-up check makes a single try

**Status:** done 2026-10-22
**Area:** channel (online checks)
**Origin:** [ADR-0003](../../adr/ADR-0003-stream-refresh.md)
**Verified:** 2026-10-22

When PubSub sends `stream-up` for a tracked channel, `Twitch.process_stream_state` calls
`Channel.check_online` in [channel.py](../../../channel.py). That starts `Channel._online_delay`, which waits
`ONLINE_DELAY` (120 seconds in `constants.py`) and then calls `update_stream` once. The wait exists because
Twitch sends `stream-up` before the stream information is available.

If `GetStreamInfo` still returns no stream after 120 seconds, `get_stream` returns `None`, the channel stays
offline and nothing schedules another try. `on_channel_update` logs `"{channel.name} stays OFFLINE"` at the
`CALL` level, which the Output box (and `log.txt`, with `--log`) shows only with `-vvv` or `-vvvv`. If
`get_stream` raises instead, the exception ends the task and nothing awaits it. Below `-vvvv`, `main.py` sends
the root logger to a `NullHandler`, so the asyncio message about that exception is discarded.

What checks the channel again:

- Another PubSub message for it: a second `stream-up`, a `viewcount` while the channel is not online, or any
  message on the `broadcast-settings-update` topic. Each one calls `check_online`, so a retry depends on
  Twitch sending one.
- For a channel without an ACL, the next `State.CHANNELS_CLEANUP` removes it while it is offline, and
  `get_live_streams` adds it back if the game directory lists it as live.
- For an ACL channel, the refresh does not check it again. `State.CHANNELS_CLEANUP` keeps ACL channels, and
  `State.CHANNELS_FETCH` skips tracked channels in `bulk_check_online`. The next reload checks it, because a
  reload removes every channel first.

So, unless another PubSub message arrives, an ACL channel whose stream was not ready after 120 seconds stays
offline in the app until the next reload, up to an hour later, while it streams.

A fix tries again a fixed number of times after an empty result, for example two more tries `ONLINE_DELAY`
apart, and logs at `INFO` when it gives up. Each extra try costs one `GetStreamInfo` request for that channel,
within the budget in [ADR-0002](../../adr/ADR-0002-twitch-traffic-budget.md). The same change catches and logs
an exception from `get_stream`.

Deferred on 2026-08-03, when the new stream check in ADR-0003 was added: the smallest change that fixes the
common case was chosen. See [channel.md](../../modules/channel.md).

## History

- 2026-08-03: Found and deferred when the new stream check was decided.
- 2026-10-18: Opened. Written down while the docs were written. Checking it against the code showed that the
  empty result is logged at the `CALL` level, and that a later PubSub message can start a new check.
- 2026-10-22: Done. Checked against the code first: the single `update_stream` call, the `CALL` level log
  and the unawaited exception were as described, and a check that a settings update or a `viewcount` started
  also kept a later `stream-up` from starting its own. An online check of a channel that was offline now
  queries up to 3 times, 120 seconds apart, while it has no stream, and logs at `INFO` when it ends without
  one. A `MinerException` from `get_stream` ends the check and is logged at `WARNING`, unless it wraps the
  `ExitRequest` of a closing window ([channel.md](../../modules/channel.md#after-a-stream-up-event)). Twitch
  requests: at most 2 more `GetStreamInfo` per check, and still at most 30 an hour per channel.
