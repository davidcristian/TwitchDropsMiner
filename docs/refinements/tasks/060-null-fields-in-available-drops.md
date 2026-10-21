# A null item in `AvailableDrops` data still raises

**Status:** open
**Area:** channel, twitch
**Origin:** Found on 2026-10-22 while the stream reads were changed to read a null stream field as an offline
channel or a stream without a game: the `AvailableDrops` data that the same checks read was not changed
**Verified:** 2026-10-22

With "Enable extra available drops check" on (`available_drops_check`, off by default), `Twitch.bulk_check_online`
and `Channel.get_stream` send `AvailableDrops` for each live channel
([channel.md](../../modules/channel.md#drops-enabled)). After a `server error`, `Twitch.gql_request` sets the
field that the error's `path` names to null ([twitch.md](../../modules/twitch.md#gql-requests)). A check with
stub data raised `TypeError` for each null field in this table:

| Where | Field that is null | What the raise does |
| --- | --- | --- |
| `Twitch.bulk_check_online`, through `channel_campaigns` | the channel's `id` | ends the run in `CHANNELS_FETCH`, and the restart begins with a full reload ([task 019](019-restart-runs-a-full-reload.md)) |
| `Twitch.bulk_check_online`, through `Channel.external_update` | an item of `viewerDropCampaigns` | ends the run in `CHANNELS_FETCH`, as above |
| `Channel.get_stream`, from an online check | an item of `viewerDropCampaigns` | ends the online check task, and the channel's stream is not updated |

`Channel.get_stream` does not read the channel's `id` in this response, so a null one there raises nothing.

## What a fix involves

`channel_campaigns` in `gqldata.py` leaves out a channel with a null ID and a null campaign, with a warning, and
`get_stream` reads its response through the same function, as the stream reads do
([gqldata.md](../../modules/gqldata.md#null-stream-fields)). A stream whose campaigns were left out counts as not
drops enabled until its next check, as a stream with no campaigns does. No fix adds a request.

## History

- 2026-10-22: Opened. Found while the stream reads were changed to read a null stream field as an offline
  channel or a stream without a game, which closed [task 059](059-null-fields-in-stream-data.md).
