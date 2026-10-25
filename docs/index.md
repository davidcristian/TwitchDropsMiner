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
- [runbooks/dependency-versions.md](runbooks/dependency-versions.md): updating the package versions in
  `constraints.txt` and checking them for every build.
- [runbooks/linux-ci-with-act.md](runbooks/linux-ci-with-act.md): running the Ubuntu Validate entries and the
  Linux PyInstaller and AppImage builds of `ci.yml` with act before a push, and starting each build.
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
| [ADR-0006: Restart after a fatal error](adr/ADR-0006-restart-after-fatal-error.md) | A fatal error restarts the run after the `restart_delay` setting plus a jitter, instead of stopping the app. The wait doubles while the error comes back within an hour, up to 60 minutes, and a `Reload` press ends it. |
| [ADR-0007: Identifiers kept from the original project](adr/ADR-0007-kept-identifiers.md) | The AppImage id and the autostart names keep their original values, so the app still finds an autostart entry that an older build wrote, and a desktop entry made for an older AppImage still names the current id. |
| [ADR-0008: The docs layout](adr/ADR-0008-docs-layout.md) | Which Cortex docs practices this repo follows: AGENTS.md as the contract, this index, the map, ADRs edited in place, a doc per module, runbooks, one file per backlog task, the 300-line cap; and the four it leaves out. |
| [ADR-0009: Watching by playlist HEAD requests](adr/ADR-0009-watch-method.md) | Every 20 seconds the app reads the stream's playlist and sends one `HEAD` request per segment, outside the GQL limiter; the Spade and GQL methods stay with no caller. |
| [ADR-0010: Login by device code with the Android app client](adr/ADR-0010-device-code-login.md) | The device code flow is the only login, with the `ANDROID_APP` client; the token is kept in `cookies.jar` and checked at each run, `Invalidate` logs out, and there is no password login or CAPTCHA handling. |
| [ADR-0011: Secrets are hidden at the log call](adr/ADR-0011-secrets-in-logs.md) | A log call that prints a request, a response or a websocket message passes it through `redact()`, which hides secrets by key name, also in a URL's query, and a URL's password. `Twitch.request` hides the proxy password in the text of a proxy error the same way. |
| [ADR-0012: One check command](adr/ADR-0012-check-command.md) | `just check` runs every check, from the pre-commit hook and in CI on Ubuntu, Windows and macOS: the standard-library scans in `scripts/`, ruff's lint rules without its formatter, and the tests; two hooks check commit messages. |
| [ADR-0013: Tests assert behavior, with an 80% coverage floor](adr/ADR-0013-test-standard.md) | What a test must assert, fakes rather than mocks, suite tests also for the modules that need Twitch or a display, strict `xfail` tests for known defects, and 80% branch coverage of the modules that need neither. |
| [ADR-0014: Code rules for new code](adr/ADR-0014-code-rules.md) | New logic receives its I/O as an argument, platform differences are one function per concern, and the typing and exception rules; inherited code follows them where a change rewrites it. |
| [ADR-0015: The release builds use a newer Python than the checks](adr/ADR-0015-release-build-python.md) | The Validate job runs on Python 3.10, the oldest supported version, and also on 3.14; the PyInstaller builds use 3.14, a version for which python.org still publishes Windows and macOS builds with OpenSSL updates. |
| [ADR-0016: Exact versions of the packages the builds install](adr/ADR-0016-exact-dependency-versions.md) | `constraints.txt` sets the version of every package a build installs from PyPI, which each build passes to pip with `-c` and `--build-constraint` and the Validate job with `-c`; no hashes; Dependabot proposes releases at least two weeks old once a month, and each build job checks what pip installed. |
| [ADR-0017: Requests for the next state](adr/ADR-0017-state-requests.md) | Of the states requested while `Twitch._run` handles one, the first of `EXIT`, `RESTART` and the states of a reload in their order runs next, a reload requested while another fetches the inventory is merged into it, and a reload keeps the channel list's selection. |
| [ADR-0018: The channels kept at the channel limit](adr/ADR-0018-channel-slots.md) | At the limit of 199 tracked channels, the channels that the switch can watch next keep their slots first, and the others keep theirs by the priority of a game, an offline ACL channel by its campaign's. A stop of the watched channel starts a stream refresh at once when a channel left off the list is better. |
| [ADR-0019: Missing strings written without a native speaker](adr/ADR-0019-strings-without-a-native-speaker.md) | The maintainer's side writes the strings that a language file lacks, in the file's own terms and form of address, keeping the format fields; nothing else in the file changes, a speaker may correct any of them, and a new string is added in English only. |
| [ADR-0020: How a module over the line cap is split](adr/ADR-0020-module-splits.md) | A split module becomes a package of the same name whose `__init__.py` keeps the callers' imports, except `constants.py` and `gui.py`, which stay and move code to `twitchapi/` and `ui/`; big classes split into mixins; a split commit only moves code. |

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
| [gui.md](modules/gui.md) | `GUIManager` and the window it builds, the theme and the `python gui.py` preview |
| [ui.md](modules/ui.md) | The parts of the window that `gui.py` imports: the generic widgets, the Main tab panels, the tray icon, the Inventory, Settings and Help tabs, the two mixins of `GUIManager`, and the preview's mock data |
| [settings.md](modules/settings.md) | Every `settings.json` key with its type and default, loading and saving |
| [constants.md](modules/constants.md) | Paths, intervals and limits, `State`, `PriorityMode`, the logging values, and `version.py` |
| [twitchapi.md](modules/twitchapi.md) | The GQL operations, the client types and the PubSub topics that the app sends to Twitch |
| [translate.md](modules/translate.md) | The translation types, `default_translation`, loading `lang/*.json` and the English fallback |
| [utils.md](modules/utils.md) | JSON loading and saving, `ExponentialBackoff` and the task helpers |
| [cache.md](modules/cache.md) | `ImageCache`: where images are stored, their expiry and broken data |
| [registry.md](modules/registry.md) | The Windows registry wrapper |
| [autostart.md](modules/autostart.md) | The autostart entry on each OS, its command and the XDG autostart folder |
| [exceptions.md](modules/exceptions.md) | Each exception class, what raises it and what catches it |
| [redact.md](modules/redact.md) | `redact`: the secret key names it hides before a log call prints a value |
| [reconnect.md](modules/reconnect.md) | `ReconnectDelay`: the wait of a websocket before each reconnect |
| [restartdelay.md](modules/restartdelay.md) | `RestartDelay`: the wait before each restart after a fatal error, doubled while each run ends within an hour |
| [gqldata.md](modules/gqldata.md) | `get_field`, `merge_data` and the readers that leave out a field a server error set to null |
| [streamdata.md](modules/streamdata.md) | The readers of stream, channel and playback token data, which read a null field as no stream, no game or no campaign |
| [imagedata.md](modules/imagedata.md) | `decode_image`: the full decode of an image download, which returns None for broken data; `png_mode`: the mode to save it in as PNG |
| [savefiles.md](modules/savefiles.md) | `save_each`: the saves during a run, where a failed save is logged and the run goes on. `replace_file`: a write through a second file that keeps the old file when it fails. `UnsavedChanges`: whether a file has a change to write |
| [ratelimit.md](modules/ratelimit.md) | `RateLimiter`: at most 5 GQL requests start in any second and at most 5 are open |
| [instancelock.md](modules/instancelock.md) | `lock_file`: the lock on `lock.file`, and the result for a file it cannot open or write |
| [parentexit.md](modules/parentexit.md) | `end_with_runtime`: the SIGTERM at the end of the AppImage runtime without FUSE, and how the app finds that runtime |
| [mousewheel.md](modules/mousewheel.md) | `wheel_events` and `wheel_scroll`: the wheel events of each windowing system and their direction |
| [scrollarea.md](modules/scrollarea.md) | `ScrollArea`: the scrolling canvas of the Inventory and Settings tabs, its scroll bars and wheel, the window size at start and the minimum window size |
| [folderpicker.md](modules/folderpicker.md) | `FolderPicker` and `ChildDialog`: the folder dialog in a child process, which the app polls for the answer |
| [colorfonts.md](modules/colorfonts.md) | `skip_color_fonts`: the color fonts left out with a libXft older than 2.3.5, why, and the fontconfig rule that leaves them out |
| [traybackend.md](modules/traybackend.md) | `import_pystray`: the tray backends tried in turn on Linux, the errors that move on to the next, the check of the DBus session bus, and the warnings |
| [settingsdata.md](modules/settingsdata.md) | `drop_non_text_items`: the check that removes items that are not strings from the list and set settings |
| [gamelib.md](modules/gamelib.md) | The installed game scan, name matching and the list patterns |
