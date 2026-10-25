# `twitchapi/`

**Purpose.** Defines what the app sends to Twitch: the clients it acts as (`ClientType`), the GQL operations with
their hashes (`GQL_QUERIES`) and the PubSub topics it subscribes to (`WebsocketTopic`). It sends nothing itself:
`twitch/`, `channel/` and `inventory/` send the GQL requests, and `websocket/` the PubSub messages. It needs
neither Twitch nor a display, and `tests/test_twitchapi.py` tests it with plain values.
[gql-operations.md](../runbooks/gql-operations.md) says how to update a hash, the client ID or the user agent.

## Files

| File | What it holds |
| --- | --- |
| `__init__.py` | Imports the public names listed in `__all__`. Callers import from `twitchapi`, never from a file of it |
| `clients.py` | `ClientInfo` and `ClientType` |
| `gql.py` | `GQLPersistedQuery`, `GQLQuery`, `GQLOperation` and `GQL_QUERIES` |
| `topics.py` | `WebsocketTopic` and `WEBSOCKET_TOPICS` |

## Public contract

### GQL operations

`GQLPersistedQuery(name, sha256, *, variables=None)` is a `dict` with `operationName`, the hash under
`extensions.persistedQuery.sha256Hash` (with `version` 1) and, when given, `variables`. The request contains the
hash and no query text. `with_variables(variables)` returns a deep copy with the given variables merged in; the
stored template does not change. In a template, `...` marks a variable that the caller must give. The merge
raises `RuntimeError` when a `...` is left unset in a dict the caller passes (`Unspecified variable: 'channel'`)
or when a dict meets a value that is not a dict. A `...` inside a dict the caller leaves out stays in the copy:
`ClaimDrop` with `{}` keeps `{"input": {"dropInstanceID": ...}}`, and `aiohttp` raises `TypeError` when it
encodes that body, before the request is sent.

`GQLQuery(query, g64data)` sends its query text, with gzip and base64 encoded data. Only `Stream.gql_payload` in
`channel/stream.py` uses it, for the `sendSpadeEvents` watch mutation, and only `Channel._send_watch_gql` reads that
payload. Nothing calls that method ([channel.md](channel.md#watching)), so its read of the response, which
raises on a null field, never runs. `GQLOperation` is either type, and `Twitch.gql_request` takes one operation
or a list.

`GQL_QUERIES` maps the key the code uses to the operation Twitch knows. To update a hash, follow
[gql-operations.md](../runbooks/gql-operations.md). The last column names the functions that read the response,
in [gqldata.md](gqldata.md) and [streamdata.md](streamdata.md). Each one has a test that sets each value of a
complete response to null in turn ([ADR-0013](../adr/ADR-0013-test-standard.md)).

| Key | `operationName` | Used in | Response read by |
| --- | --- | --- | --- |
| `GetStreamInfo` | `VideoPlayerStreamInfoOverlayChannel` | `channel/` | `channel_streams`, `channel_stream` |
| `ClaimDrop` | `DropsPage_ClaimDropRewards` | `inventory/` | `claim_succeeded` |
| `Inventory` | `Inventory` | `twitch/` | `user_inventory`, `complete_campaigns` |
| `CurrentDrop` | `DropCurrentSessionContext` | `twitch/` | `current_drop` |
| `Campaigns` | `ViewerDropsDashboard` | `twitch/` | `campaign_summaries`, `complete_campaigns` |
| `CampaignDetails` | `DropCampaignDetails` | `twitch/` | `campaign_details`, `complete_campaigns` |
| `AvailableDrops` | `DropsHighlightService_AvailableDrops` | `channel/`, `twitch/` | `channel_campaigns`, `available_campaigns` |
| `PlaybackAccessToken` | `PlaybackAccessToken` | `channel/` | `playback_token` |
| `GameDirectory` | `DirectoryPage_Game` | `twitch/` | `directory_streams` |
| `NotificationsDelete` | `OnsiteNotifications_DeleteNotification` | `twitch/` | not read |

### Client identities

`ClientInfo(client_url, client_id, user_agents)` has the attributes `CLIENT_URL`, `CLIENT_ID` and `USER_AGENT`,
and iterates as that tuple. When `user_agents` is a list, `random.choice` picks one when the `ClientType` class
body runs at import, so one run uses one user agent from start to end.

| `ClientType` member | `CLIENT_URL` | User agents |
| --- | --- | --- |
| `WEB` | `https://www.twitch.tv` | one desktop Chrome |
| `MOBILE_WEB` | `https://m.twitch.tv` | a list of Android Chrome |
| `ANDROID_APP` | `https://www.twitch.tv` | a list of the Twitch Android app |
| `SMARTBOX` | `https://android.tv.twitch.tv` | one Android TV box |

`Twitch.__init__` sets `_client_type` to `ClientType.ANDROID_APP`, and the login switches it to the entry whose
`CLIENT_ID` the token check returns ([tokencheck.md](tokencheck.md#the-client-of-the-token)). The `aiohttp`
session sends its user agent with every request, and `twitch/session.py` adds its client ID to the login and GQL
requests. [gql-operations.md](../runbooks/gql-operations.md) covers updating them.

### PubSub topics

`WEBSOCKET_TOPICS` maps a category (`"User"` or `"Channel"`) and a name to the Twitch topic.
`WebsocketTopic(category, topic_name, target_id, process)` is one subscription: `str()` gives
`<topic>.<target_id>`, such as `video-playback-by-id.123`, and calling it passes `(target_id, message)` to
`process`. It compares equal to another topic or a string with the same text and has the same hash as that
text, so a set or dict lookup by the text finds it. `WebsocketTopic.as_str` builds that text without an object.
[websocket.md](websocket.md) describes the pool.

## Invariants

- Importing `clients.py` has a side effect: it picks the user agent of each `ClientType` member that has a list
  of them, once per run.
- A new template variable that the caller must give is written as `...`, so a missing value raises before any
  request is sent.
- The package imports `JsonType` from `constants`, which imports no repo module except `version`, so the two
  form no import cycle.

**Dependencies.** `constants` (`JsonType`), `yarl` and the standard library.
