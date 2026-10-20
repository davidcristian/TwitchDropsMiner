# `gqldata.py`

**Purpose.** Reads the data of GQL responses for `twitch.py` and `channel.py`. After a `server error`,
`Twitch.gql_request` sets the field that the error's `path` names to null ([twitch.md](twitch.md#gql-requests)),
so each function here leaves out a null item instead of raising. A raise inside `Twitch._run` ends the run, and
the restart after it begins with a full reload
([task 019](../refinements/tasks/019-restart-runs-a-full-reload.md)). Which fields Twitch names in a server
error has not been observed, so the functions accept a null at any level. The module sends no request and needs
neither Twitch nor a display.

## Public contract

- `get_field(data, *path)` returns the value at `path`, a sequence of dict keys and list indexes. It returns
  None when a value on the way is null, missing, or not a dict or a list. With no path it returns `data`.
- `clear_error_field(data, path)` sets the field at a server error's `path` to None and returns True. It
  returns False and changes nothing when the path is empty or the field's parent is null or missing, and
  `gql_request` then logs the error and returns the response as it is.
- `merge_data(primary, secondary)` returns a dict with the keys of both. Where both have a dict, it merges the
  two in the same way; where both have another value, it keeps `primary`'s. A None value counts as no value, so
  the value of the other side is kept. Two values of different types raise
  `MinerException("Inconsistent merge data")`.
- `campaign_details(responses)` maps each campaign ID to the `dropCampaign` of a `CampaignDetails` response,
  and leaves out a response whose `data`, `user` or `dropCampaign` is null.
- `complete_campaigns(campaigns)` returns the campaigns in which none of `CAMPAIGN_FIELDS` (`game`, `allow` and
  `timeBasedDrops`) is null or missing. `DropsCampaign` reads all three.
- `directory_streams(response)` returns the stream nodes of a `GameDirectory` response whose `broadcaster` is
  not null, and an empty list when the game, its streams or their edges are null.
- `channel_campaigns(responses)` maps each channel ID, as an int, to the `viewerDropCampaigns` of an
  `AvailableDrops` response, with an empty list for null, and leaves out a response whose `channel` is null.

## Null campaign details

`Twitch.fetch_inventory` merges three responses: `Inventory` (the campaigns in progress, with their drops), the
`Campaigns` summary of every campaign, and `CampaignDetails`. When the details of a campaign are null, its
summary is kept. A campaign in progress still has its `Inventory` data and is mined. Any other campaign has
only its summary, and `complete_campaigns` leaves it out unless the summary has every field in
`CAMPAIGN_FIELDS`. The next reload fetches its details again.

## Invariants

- Only `clear_error_field` changes its argument. `merge_data` builds new dicts but shares the other values,
  such as lists, with its arguments.
- No function sends a request, and no caller sends one again for a null item: a campaign left out waits for
  the next reload, and a game with a null directory for the next `CHANNELS_FETCH`.

**Dependencies.** `exceptions` (`MinerException`). `constants` (`JsonType`) is imported for type checking only.
