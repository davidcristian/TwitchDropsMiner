# Docs index

Start here. The rules for working in this repo are in [AGENTS.md](../AGENTS.md).

## For users

- [building.md](building.md): running from source, previewing the GUI, building and packaging, and the release
  builds.
- [troubleshooting.md](troubleshooting.md): where the app keeps its files, the command line flags, and common
  problems with what to do about each.

## Map and procedures

- [ARCHITECTURE.md](ARCHITECTURE.md): the objects, the state machine in `Twitch._run`, the path from login to a
  claimed drop, the Twitch requests, the background tasks, the platform code and the repo map.
- [runbooks/gql-operations.md](runbooks/gql-operations.md): what to do when Twitch changes a GQL operation, and
  how to update its hash, the client ID or the user agent.
- [runbooks/upstream-fixes.md](runbooks/upstream-fixes.md): bringing a fix in from DevilXD/TwitchDropsMiner by
  cherry-pick.
- [runbooks/gui-preview-headless.md](runbooks/gui-preview-headless.md): running and screenshotting `gui.py` on
  Linux without a display.
- [refinements/](refinements/index.md): the deferred work, one file per task.

## Decisions

Each record states the decision that applies today and is edited in place when it changes. The format is in
[adr/README.md](adr/README.md). A new non-obvious decision becomes `adr/ADR-NNNN-<slug>.md` and is added here.

| Record | What it decides |
| --- | --- |
| [ADR-0001: An independent project](adr/ADR-0001-independent-project.md) | The fork is developed on its own under the AGPL v3, keeps the original MIT notice, sends nothing upstream and takes upstream fixes by cherry-pick or merge. |
| [ADR-0002: The Twitch traffic budget](adr/ADR-0002-twitch-traffic-budget.md) | Every GQL request goes through one rate limiter at 5 per second, batches of 20, the four events that run a full reload, and periodic work that re-enters the channel cleanup and fetch. |
| [ADR-0003: The stream refresh](adr/ADR-0003-stream-refresh.md) | A check for new streams every `refresh_interval` minutes that re-enters the channel cleanup and fetch instead of reloading, and what it costs. |
| [ADR-0004: Installed game detection](adr/ADR-0004-installed-game-detection.md) | Installed Steam and Epic games are added to what is mined, below the Priority list, found through the launchers' own indexes, matched with high confidence only, with the standard library. |
| [ADR-0005: Priority and Exclude list patterns](adr/ADR-0005-list-patterns.md) | Entries match names ignoring case, accents and punctuation, take `*` and `?`, rank by the first matching entry, and the Games Being Mined table names the entry that ranked each mined game. |
| [ADR-0006: Restart after a fatal error](adr/ADR-0006-restart-after-fatal-error.md) | A fatal error restarts the run after the `restart_delay` setting plus a jitter, instead of stopping the app. |
| [ADR-0007: Identifiers kept from the original project](adr/ADR-0007-kept-identifiers.md) | The AppImage id and the autostart names keep their original values, so the app still finds an autostart entry that an older build wrote, and a desktop entry made for an older AppImage still names the current id. |
| [ADR-0008: The docs layout](adr/ADR-0008-docs-layout.md) | Which Cortex docs practices this repo follows: AGENTS.md as the contract, this index, the map, ADRs edited in place, a doc per module, runbooks, one file per backlog task, the 250-line cap; and the four it leaves out. |
| [ADR-0009: Watching by playlist HEAD requests](adr/ADR-0009-watch-method.md) | Every 20 seconds the app reads the stream's playlist and sends one `HEAD` request per segment, outside the GQL limiter; the Spade and GQL methods stay with no caller. |
| [ADR-0010: Login by device code with the Android app client](adr/ADR-0010-device-code-login.md) | The device code flow is the only login, with the `ANDROID_APP` client; the token is kept in `cookies.jar` and checked at each run, `Invalidate` logs out, and there is no password login or CAPTCHA handling. |
| [ADR-0011: Secrets are hidden at the log call](adr/ADR-0011-secrets-in-logs.md) | A log call that prints a request, a response or a websocket message passes it through `redact()`, which hides secrets by key name and a URL's password. `Twitch.request` hides the proxy password in the text of a proxy error the same way. |
| [ADR-0012: One check command](adr/ADR-0012-check-command.md) | `just check` runs every check, from the pre-commit hook and in CI: the standard-library scans in `scripts/`, ruff's lint rules without its formatter, and the tests; two hooks check commit messages. |
| [ADR-0013: Tests assert behavior, with an 80% coverage floor](adr/ADR-0013-test-standard.md) | What a test must assert, fakes rather than mocks, strict `xfail` tests for known defects, and 80% branch coverage of the modules that need neither Twitch nor a display. |
| [ADR-0014: Code rules for new code](adr/ADR-0014-code-rules.md) | New logic receives its I/O as an argument, platform differences are one function per concern, and the typing and exception rules; inherited code follows them where a change rewrites it. |

## Modules

[modules/](modules/) holds one short document per module, each giving its purpose, its public contract, its
invariants and what it depends on. Every module in the [module map](../AGENTS.md#module-map) has one:

| Document | What it covers |
| --- | --- |
| [main.md](modules/main.md) | The entry point: flags, logging, the argument, settings and lock file error dialogs, the exit codes |
| [twitch.md](modules/twitch.md) | `Twitch`: requests and the GQL limiter, login, the state machine, the maintenance task, the wanted games |
| [inventory.md](modules/inventory.md) | `DropsCampaign` and `TimedDrop`: what can be mined, progress, claiming |
| [channel.md](modules/channel.md) | `Channel` and `Stream`: online checks, the batched bulk check, the watch requests |
| [websocket.md](modules/websocket.md) | The PubSub websocket pool, its topics and the 199 channel limit |
| [gui.md](modules/gui.md) | `GUIManager`, its tabs and panels, the tray icon, the theme and the `python gui.py` preview |
| [settings.md](modules/settings.md) | Every `settings.json` key with its type and default, loading and saving |
| [constants.md](modules/constants.md) | Paths, intervals and limits, `State`, `PriorityMode`, the GQL operations, the client types, and `version.py` |
| [translate.md](modules/translate.md) | The translation types, `default_translation`, loading `lang/*.json` and the English fallback |
| [utils.md](modules/utils.md) | JSON loading and saving, `ExponentialBackoff` and the task helpers |
| [cache.md](modules/cache.md) | `ImageCache`: where images are stored, their expiry and broken data |
| [registry.md](modules/registry.md) | The Windows registry wrapper and autostart on each OS |
| [exceptions.md](modules/exceptions.md) | Each exception class, what raises it and what catches it |
| [redact.md](modules/redact.md) | `redact`: the secret key names it hides before a log call prints a value |
| [reconnect.md](modules/reconnect.md) | `ReconnectDelay`: the wait of a websocket before each reconnect |
| [gqldata.md](modules/gqldata.md) | `get_field`, `merge_data` and the readers that leave out a field a server error set to null |
| [imagedata.md](modules/imagedata.md) | `decode_image`: the full decode of an image download, which returns None for broken data |
| [savefiles.md](modules/savefiles.md) | `save_each`: the saves after an inventory fetch, where a failed save is logged and the run goes on. `UnsavedChanges`: whether a file has a change to write |
| [ratelimit.md](modules/ratelimit.md) | `RateLimiter`: at most 5 GQL requests start in any second and at most 5 are open |
| [instancelock.md](modules/instancelock.md) | `lock_file`: the lock on `lock.file`, and the result for a file it cannot open or write |
| [mousewheel.md](modules/mousewheel.md) | `wheel_events` and `wheel_scroll`: the wheel events of each windowing system and their direction |
| [gamelib.md](modules/gamelib.md) | The installed game scan, name matching and the list patterns |
