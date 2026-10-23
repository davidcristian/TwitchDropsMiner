# Code that nothing calls

**Status:** open
**Area:** channel, inventory, websocket, utils, constants, gui, translate
**Origin:** Found on 2026-10-18 while the docs were written, [channel.md](../../modules/channel.md)
**Verified:** 2026-10-18

No code in the repo calls, reads or reaches the code below. The module docs name most of it:
[channel.md](../../modules/channel.md), [inventory.md](../../modules/inventory.md),
[websocket.md](../../modules/websocket.md), [utils.md](../../modules/utils.md),
[constants.md](../../modules/constants.md), [gui.md](../../modules/gui.md) and
[translate.md](../../modules/translate.md).

- **The Spade and GQL watch methods, `channel.py`.** `Channel._send_watch_spade` and `Channel._send_watch_gql`.
  `Twitch._watch_loop` calls only `Channel.send_watch`, the playlist HEAD method. Only these two use
  `Channel.get_spade_url`, `Channel.url`, the `_spade_url` slot and attribute, `Stream.spade_payload`,
  `Stream.gql_payload` and `Stream._watch_payload`. In `channel.py`, only they use the imports `gzip`,
  `b64encode`, `json_minify`, `isonow`, `RequestException` and `GQLQuery`.
- **`BaseDrop.generate_claim`**, `inventory.py`. It builds a claim ID as `<user ID>#<campaign ID>#<drop ID>`.
- **`DropsCampaign.get_drop`**, `inventory.py`. `Twitch.process_drops` finds a drop in `Twitch._drops` instead.
- **`websocket.py`:** the `Websocket.connected` property and `WebsocketPool.wait_until_connected`.
- **`utils.py`:** `first_to_complete`, `CHARS_HEX_UPPER`, `deduplicate`, `invalidate_cache` and
  `AwaitableValue.wait`.
- **Five `GQL_QUERIES` entries, `constants.py`:** `ClaimCommunityPoints`, `ChannelPointsContext`,
  `SlugRedirect`, `NotificationsView` and `NotificationsList`.
- **`SelectMenu`**, `gui.py`. The four drop-down lists of the General frame use `SelectCombobox`.
- **The four `login.chrome` strings** in `default_translation` and their `ChromeMessages` type,
  `translate.py`.
- **The `english_name` string**, `translate.py`. Every language file defines it, such as `"Polish"` in
  `Polski.json`. It still tells a person which language a file such as `العربية.json` holds, so removing it is
  optional.
- **The `language_name` check in `Translator.set_language`**, which raises `ValueError` when a language file
  defines `language_name`. `json_load` merges the file with `default_translation`, which has no `language_name`,
  so `merge_json` removes the key before the check runs.

## How it was confirmed

- A script parsed every tracked `.py` file with the `ast` module and listed each reference to each name: a
  definition, a name, an attribute, an import, or a string constant that contains the name. The string
  constants cover `getattr` and string keys. Each name above has its definition as its only reference, or
  references only from other names on the list. For example, `get_spade_url` has one other reference, in
  `_send_watch_spade`, and `_watch_payload` has two, in `spade_payload` and `gql_payload`. The other references
  to `connected` are the translation keys `connected` and `disconnected` and log text, and none of them reads
  the property.
- All 174 calls of the translator `_` pass literal keys, and none of them reads `login.chrome` or
  `english_name`. Every read of `GQL_QUERIES` uses a literal key, and no code loops over its entries.
- For the `language_name` check, a real call: a copy of `lang/Polski.json` with `"language_name": "Hacked"`
  added was loaded with `Translator.set_language`, from a copy of `lang/` in a temporary folder. It returned
  without `ValueError`, and `Translator.current` was the file's name.

## Effect

None for a user, because the app never runs this code. A reader of the code or the docs has to work out that
it does not run. The five GQL entries contain hashes that no request tests, so they can go out of date without
an error.

## How it came about

From `git log -S` on each name. All of it comes from the original project.

- The watch methods. Upstream changed the watch method five times: to playlist HEAD requests in "Implement
  channel watching using the new method" (2024-06-22), back to Spade in "Reimplement the old mining method"
  (2025-08-17), to a new GQL method in "Implement a way to send watch events through GQL" (2026-04-28), back
  to Spade in "Change the watching method back to using Spade" (2026-07-11), and to HEAD requests again in
  "Change the mining method to playlist HEAD requests" (2026-10-09). The first change deleted the Spade code,
  and the second wrote it again. Since then, each change has kept the method it replaced, with a comment that
  says it is unused. No commit says why the old methods stay, so a fix decides whether to delete them or to
  keep them as alternatives ([ADR-0009](../../adr/ADR-0009-watch-method.md)).
- `generate_claim` was added in "Add claim ID generator for future reference" (2024-06-23) and has never had a
  caller.
- "Remove selenium, chrome and integrity handling" (2024-06-20) removed the Chrome login, which was the last
  caller of `first_to_complete` and the only reader of the `login.chrome` strings.
- `deduplicate` (2022-01-22) and `CHARS_HEX_UPPER` (2022-09-14) have never had a caller.
- "Remove Game Selector; Implement multi-game mining based on the priority list" (2022-03-30) removed the last
  calls of `DropsCampaign.get_drop`.
- "Simplify some of the websocket start and stop logic" (2022-09-17) removed the last reads of
  `Websocket.connected`. `WebsocketPool.wait_until_connected` has had no caller since "Huge websocket redesign,
  to support more than a single connection" (2021-12-15) added it.
- "Implement drop progression tracking across all drops in a campaign" (2025-09-10) removed the last calls of
  `invalidate_cache`.
- "Use SelectCombobox for language selection" (2024-09-11) replaced the last use of `SelectMenu`.
- "Remove channel points handling" (2025-05-01) removed the requests for `ClaimCommunityPoints` and
  `ChannelPointsContext` and kept the entries. `SlugRedirect` was added "for potential later usage"
  (2024-06-22). `NotificationsView` and `NotificationsList` were added with a comment that says they are unused
  (2023-11-04).
- The `language_name` check dates from the first translation code (2022-08-18). `english_name` was added to
  every file in "Add English translation name keys" (2023-10-29), and no code has read it.

## What a fix involves

Remove each item, or keep it with a one line comment that says why it stays. The watch methods are the one
real choice. Removing them also removes the imports and the `_spade_url` slot that only they use, and then
`utils.isonow` and `constants.GQLQuery` have no caller. Keeping them saves work if Twitch stops counting the
HEAD method. Removing them makes an upstream fix to one of them conflict when it is brought in
([upstream-fixes.md](../../runbooks/upstream-fixes.md)). The fix chooses, and says why.

When the `login.chrome` keys leave `default_translation`, the language files still contain them. The merge
drops them on load, and [023](023-language-file-keys-dropped.md) covers keys like these. The module docs listed
above change in the same commit.

Removing code sends no request. Switching back to a Spade or GQL method changes the requests of each watch
cycle, so that change states its count, as [AGENTS.md](../../../AGENTS.md#the-one-hard-rule) asks.

## History

- 2026-10-18: Opened. The module docs named most of this code as unused while they were written, and an
  `ast` scan of the tracked `.py` files confirmed that nothing references any of it.
- 2026-10-20: `WebsocketPool.start` no longer waits for a connection, so `Websocket.start` and
  `Websocket.wait_until_connected` were removed. `AwaitableValue.wait` lost its one caller and is now listed here.
- 2026-10-23: Removed the five items in `utils.py`, `generate_claim`, `get_drop`, `Websocket.connected`,
  `WebsocketPool.wait_until_connected` and `SelectMenu`.
