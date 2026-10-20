# ADR-0002: The Twitch traffic budget

**Status:** Accepted (2026-10-20)

## Context

The app runs on the user's own Twitch account, and a burst of requests puts that account at risk. So Twitch
must see no more traffic than a diligent person would cause. AGENTS.md states this as
[the one hard rule](../../AGENTS.md#the-one-hard-rule), and the README states it for users under
[Project goals](../../README.md#project-goals). This record states the mechanism behind the rule.

Apart from the video requests sent while a stream is watched, most of the app's requests go to GQL, the GraphQL
API that the Twitch website uses. One GQL request is an HTTP
`POST` to `https://gql.twitch.tv/gql`. Its body holds one operation (one query or mutation) or a list of them.
The limit below counts requests. Nothing in this repo records how Twitch counts its own limit, so the costs
below give both numbers.

The most expensive work is a full reload, `State.INVENTORY_FETCH`. Its cost grows with the ACL of each wanted
campaign. An ACL (access control list) is the list of channels whose streams count toward a campaign's drops.
The original project's maintainer declined to shorten the hourly reload or to make it a setting, in
[a feature request for a shorter wait time](https://github.com/DevilXD/TwitchDropsMiner/issues/175). His count
was 2 requests per ACL channel. Some campaigns list about 1200 ACL channels or more, so a reload came to about
2500 requests and took over 500 seconds at 5 per second. He wrote: "I cannot set a shorter time for everyone,
nor allow setting it such".

## Decision

1. **Every GQL request goes through `Twitch.gql_request`.** It is the only code that posts to the GQL endpoint.
   Each pass of its retry loop enters `Twitch._qgl_limiter`, which `Twitch.__init__` builds as
   `RateLimiter(capacity=5, window=1)` (`ratelimit.py`). At most 5 entries start in any span of 1 second, and
   at most 5 are in flight at once. `Twitch.request` retries a status of 500 or more, or a connection error,
   inside the same entry, so the limiter does not count those retries. One entry point means no caller can
   send GQL outside the limit. The comment at the constructor says that GQL "breaks everything if one runs
   into their rate limit".

2. **Operations for many channels or campaigns are sent in batches of 20.** `bulk_check_online` passes its
   `GetStreamInfo` and `AvailableDrops` operations through `chunk(..., 20)`, and `fetch_inventory` does the same
   with `CampaignDetails`. The limiter counts a batch as one request, so a check of 1200 channels costs 60
   requests instead of 1200.

3. **A full reload runs only on these events, and no timer runs it more often:**
   - at startup, because `_run` begins in `State.INVENTORY_FETCH`. `Twitch.run` starts `_run` again after the
     `Invalidate` button on the Help tab, whose `State.RESTART` raises `ReloadRequest`, and after a fatal error
     ([ADR-0006](ADR-0006-restart-after-fatal-error.md)). Each new run reloads, so a fatal error that repeats
     causes one reload per restart ([019](../refinements/tasks/019-restart-runs-a-full-reload.md)).
   - once an hour, from `_maintenance_task`. Every reload ends by starting a new `_maintenance_task`, so the
     hour counts from the last reload of any cause.
   - after a drop is claimed. `process_drops` reloads when the drop's campaign cannot progress further on the
     watched channel, and `process_notifications` reloads on Twitch's drop reward notification.
   - on Twitch's emote reward notification (`quests_viewer_reward_campaign_earned_emote`), from
     `process_notifications`.
   - from the `Reload` button in the Settings tab.

   The reason is the cost of a reload ([below](#the-cost-of-a-full-reload)), which grows with the size of the
   ACLs.

4. **Periodic work re-enters the channel fetch, not the reload.** New periodic work changes the state to
   `State.CHANNELS_CLEANUP`, which moves on to `State.CHANNELS_FETCH`, or to `State.IDLE` when no game is
   wanted. These states check channels again for the campaigns already loaded, which costs a few requests.
   The stream refresh ([ADR-0003](ADR-0003-stream-refresh.md)) and the start and end times of campaigns and
   drops (`_mnt_triggers`) both take this path.

5. **A change that adds requests states how many per cycle in its commit body.** A reviewer can then check the
   change against this budget from the commit alone.

## Consequences

### The cost of a full reload

The GQL requests of one full reload, by step:

- `fetch_inventory`: 1 `Inventory`, 1 `Campaigns`, and 1 `CampaignDetails` per 20 active or upcoming
  campaigns.
- `State.GAMES_UPDATE`: 1 `ClaimDrop` per drop that can be claimed.
- `State.CHANNELS_CLEANUP`: none. A full cleanup removes every tracked channel.
- `State.CHANNELS_FETCH`: 1 `GetStreamInfo` per 20 ACL channels of the wanted campaigns that can progress
  within the next hour. 1 `AvailableDrops` per 20 of those channels that are online, only when
  `available_drops_check` is on, which it is not by default. 1 `GameDirectory` per wanted game with a campaign
  that has no ACL.
- `_watch_loop`, while a channel is watched: 1 `PlaybackAccessToken` for the new `Stream` object that the
  channel fetch gives the watched channel. The channel fetch also shows the drop again with `subone=True`,
  which stops the countdown that `minute_almost_done` reads, so 1 `CurrentDrop` follows unless a PubSub
  progress update restarts the countdown first.

For the sizes in the maintainer's count (about 100 campaigns and 1200 ACL channels), a reload today sends 67
requests, plus one per wanted game without an ACL, one per claim and up to two from the watch loop. With
`available_drops_check` on and every channel online, it sends up to 127. At 5 per second that takes at least
13 seconds, or 25 with the check. The same reload sends 1302 operations, or up to 2502 with the check, which
matches the maintainer's figure of 2500.

### What else follows

- A reload stays the most expensive work the app does, and its cost grows with every ACL channel. A new timer
  that runs it breaks the rule. A new periodic check uses decision 4 instead.
- A retry in `gql_request` enters the limiter again, after a wait from `ExponentialBackoff(maximum=60)`.
- Watching a stream sends requests to Twitch's video servers every `WATCH_INTERVAL` (20 seconds), as the
  README's [How It Works](../../README.md#how-it-works) describes. They are not GQL requests, so the limit does
  not apply to them. The stream's playback token and the `CurrentDrop` check in `_watch_loop` are GQL, and go
  through `gql_request`.
- Campaign and drop images come from Twitch's image servers. `ImageCache` in `cache.py` keeps each image on disk
  for 7 days after its last use (`LIFETIME`), so a reload downloads only the images it does not have. A failed
  download is stored as a blank placeholder and is not tried again while it is in use
  ([017](../refinements/tasks/017-failed-image-downloads-cached.md)).

## Alternatives rejected

- **A shorter hourly reload, or a setting for it.** Each reload costs what the list above gives, so a shorter
  interval multiplies the largest cost the app has. The stream refresh in ADR-0003 finds new streams for a few
  requests.
- **A higher limit than 5 requests per second.** The code comment at the limiter asks to keep the safe default,
  and nothing measures how close 5 per second is to Twitch's own limit.
- **Fixed windows of 1 second, each opened by the first request after the last one closed.** Requests at the end
  of one window and the start of the next add up to 9 starts within one second. The limiter keeps the start
  times of the last 5 requests instead, which gives the same average of 5 per second.

## Related

- [ADR-0003](ADR-0003-stream-refresh.md): the stream refresh that re-enters the channel fetch.
- [ADR-0006](ADR-0006-restart-after-fatal-error.md): the restart that runs `_run` again.
- [twitch.md](../modules/twitch.md), [ratelimit.md](../modules/ratelimit.md), [utils.md](../modules/utils.md),
  [channel.md](../modules/channel.md), [constants.md](../modules/constants.md), [cache.md](../modules/cache.md).
- [The one hard rule](../../AGENTS.md#the-one-hard-rule) in AGENTS.md and
  [Project goals](../../README.md#project-goals) in the README.
