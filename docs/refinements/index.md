# Deferred refinements

Every known gap or improvement that was left for later, one file per task in [tasks/](tasks/). A deferral
without a written record is a lost decision, so writing one down is part of finishing the change that defers it
([AGENTS.md](../../AGENTS.md#working-agreement)). A task keeps its file after it closes, as the record of what
the deferral became.

## How to work this backlog

1. **Pick** a task from the list below and open its file. Its `**Status:**` line is the only place its state
   is written.
2. **Check the task's claim against the code before you start.** The `**Verified:**` line gives the day
   somebody last did. An old date, or a file the task names that has changed since, makes the check yours
   again. Write today's date on that line when you take it.
3. **Work it** under the rules in [AGENTS.md](../../AGENTS.md), through a pull request.
4. **Close it in its own file.** Set `**Status:**` to `done` (fixed), `declined` (not to be done, with the
   reason) or `satisfied` (other work met the need) with today's date, and add a `## History` line saying what
   it became. Edit the origin ADR only when the close changed the decision it states.
5. **File what the close opened** as a new task with the next free number, and name it in the History of both.

A new task is added to the list below in the same commit as its file. The list gives no status, so it needs no
edit when a task changes state.

## Task format

```
# <Title that names the problem>

**Status:** open
**Area:** <module or area>
**Origin:** <the ADR or doc that deferred it, or how it was found>
**Verified:** <the day its claim was last checked against the code>

<What is wrong or missing, with file and function references and numbers from the code. What fixing it
involves and costs, in Twitch requests where that applies. Why it was deferred, when known.>

## History

- <date>: Opened. <how it was found>
```

## Tasks

| Task | Area |
| --- | --- |
| [001: Offline ACL channels are trimmed first](tasks/001-offline-acl-channels-trimmed-first.md) | twitch |
| [002: A stream-up check makes a single try](tasks/002-online-delay-single-try.md) | channel |
| [003: There is no test suite](tasks/003-test-suite.md) | repo checks |
| [004: No single command runs the repo checks](tasks/004-single-check-command.md) | repo checks, ci |
| [005: Eight modules are over the line cap](tasks/005-modules-over-the-line-cap.md) | module layout |
| [006: The README pictures show the original app](tasks/006-readme-screenshots.md) | README |
| [007: The README platform notes break the prose rules](tasks/007-readme-platform-notes-prose.md) | README |
| [008: The translations lack the strings of new features](tasks/008-translations-for-new-strings.md) | lang |
| [009: The ™ sign becomes the letters TM in normalized game names](tasks/009-trademark-symbols-in-game-names.md) | gamelib |
| [010: The password login and its CAPTCHA handling cannot run](tasks/010-unreachable-password-login.md) | twitch, main, gui, constants, translate |
| [011: Debug logs contain the login token](tasks/011-login-token-in-debug-log.md) | twitch, websocket, logging |
| [012: A button press during a fetch is replaced by the next state](tasks/012-button-requests-lost-during-a-fetch.md) | twitch, gui |
| [013: A crashed background task ends the app instead of restarting it](tasks/013-crashed-task-ends-the-app.md) | utils, twitch, websocket, main |
| [014: Some text the app shows is written in the code and is not translated](tasks/014-hard-coded-strings.md) | gui, gamelib, translate |
| [015: Autostart fails on Linux without an autostart folder, and from source outside Windows](tasks/015-autostart-on-linux-and-macos.md) | gui |
| [016: A lower progress value sets other drops of the campaign below zero minutes](tasks/016-negative-minutes-for-other-drops.md) | inventory |
| [017: A failed image download stays blank while the image is in use](tasks/017-failed-image-downloads-cached.md) | cache |
| [018: The Inventory tab hides campaigns that are mined because the game is installed](tasks/018-inventory-tab-hides-detected-games.md) | gui |
| [019: Each restart after a fatal error runs a full reload](tasks/019-restart-runs-a-full-reload.md) | twitch, Twitch traffic |
| [020: The no campaign message repeats on every stream refresh](tasks/020-no-campaign-message-repeats.md) | twitch |
| [021: At `-vvvv`, a log record from the game scan thread makes the scan fail](tasks/021-scan-thread-logs-into-tk.md) | gui, gamelib, twitch |
| [022: Code that nothing calls](tasks/022-unused-code.md) | channel, inventory, websocket, utils, constants, gui, translate |
| [023: Some language files have strings at paths the app does not read](tasks/023-language-file-keys-dropped.md) | lang |
| [024: After a restart, the PubSub pool connects websockets that have no topics](tasks/024-websocket-pool-keeps-empty-connections.md) | websocket |
| [025: `--version` and `--help` show their output as an error](tasks/025-version-and-help-shown-as-error.md) | main |
| [026: The Settings tab repeats three setting defaults](tasks/026-settings-defaults-written-twice.md) | settings, gui |
| [027: The campaign map keeps every campaign since the app started](tasks/027-campaigns-never-cleared.md) | twitch, channel |
| [028: A watch restart in the first 15 seconds of a cycle has no effect](tasks/028-watch-restart-dropped.md) | twitch |
| [029: Each stream refresh stops the drop countdown](tasks/029-refresh-stops-the-countdown.md) | twitch, gui |
| [030: A device code can expire before the Login press](tasks/030-device-code-expires-before-login-press.md) | twitch, gui |
| [031: The logic in utils and settings has no tests](tasks/031-tests-for-utils-and-settings.md) | utils, settings, tests |
| [032: Letters outside a to z are removed from normalized game names](tasks/032-names-outside-a-to-z-dropped.md) | gamelib |
| [033: A fuzzy game match ignores the numerals I, V and X](tasks/033-fuzzy-match-ignores-i-v-x.md) | gamelib |
| [034: A game folder scanned after another one is reported as holding no games](tasks/034-shared-epic-folder-reported-empty.md) | gamelib |
| [035: A game folder that names an unknown user ends the scan of every folder](tasks/035-unknown-user-ends-the-game-scan.md) | gamelib |
| [036: A name that holds a native title and an English one does not match the English Twitch name](tasks/036-mixed-script-names-unmatched.md) | gamelib |
| [037: Some GQL reads still raise on a null field](tasks/037-null-fields-in-other-gql-reads.md) | twitch, inventory |
| [038: A downloaded CMYK image ends the run](tasks/038-cmyk-image-download-ends-the-run.md) | cache |
| [039: On a full disk, the cookie and image writes still end the run](tasks/039-full-disk-other-writes.md) | twitch, cache |
| [040: No test can import `translate` or a module that imports it](tasks/040-tests-cannot-import-translate.md) | translate, tests |
| [041: A `WebsocketTopic` equals its text but has a different hash](tasks/041-topic-hash-differs-from-its-text.md) | constants, websocket |
| [042: The game folder dialog stops the miner while it is open](tasks/042-folder-dialog-stops-the-miner.md) | gui |
| [043: A `drop-claim` event for a claimed drop runs the claim handling again](tasks/043-repeated-drop-claim-event.md) | twitch |
| [044: The window is wider than a screen of 1366 pixels](tasks/044-window-wider-than-small-screens.md) | gui |
| [045: A run from source started from another AppImage keeps its files in that AppImage's folder](tasks/045-run-from-source-inside-another-appimage.md) | constants |
| [046: The Windows and macOS checks in CI have never run and are not required](tasks/046-checks-run-only-on-linux-and-python-3-10.md) | ci, repo checks |
| [047: The hash checks of the Linux build downloads have not run in CI](tasks/047-unchecked-build-downloads.md) | ci, appimage |
| [048: The builds install the newest release of every dependency](tasks/048-builds-install-the-newest-dependencies.md) | build, ci, requirements |
| [049: The `just` binary and a commit message hook are not checked against a hash](tasks/049-check-tools-from-third-party-sources.md) | repo checks, ci |
| [050: The image hash calls `getdata`, which Pillow 14 removes](tasks/050-image-hash-uses-removed-getdata.md) | cache |
| [051: The redact tests use a stand-in for aiohttp's `RequestInfo`](tasks/051-redact-test-uses-a-stand-in-request-info.md) | redact, tests |
| [052: On Tk 9, the back and forward mouse buttons scroll the Inventory tab](tasks/052-tk-9-back-button-scrolls-inventory.md) | mousewheel, gui |
| [053: No test checks that `log.txt` is written in UTF-8](tasks/053-log-file-encoding-untested.md) | main, tests |
| [054: The window is taller than a screen of 720 pixels](tasks/054-window-taller-than-small-screens.md) | gui |
| [055: The minimum window size does not follow the Main tab when it grows](tasks/055-minimum-window-size-misses-main-tab-growth.md) | gui |
| [056: The AppImage job installs the newest release of appimage-builder's dependencies](tasks/056-appimage-builder-dependencies-newest.md) | ci, appimage |
| [057: Nothing proposes a new version for `constraints.txt` or checks that it lists every indirect package](tasks/057-constraints-updates-by-hand.md) | build, ci |
| [058: `build.sh --nopause` exits with status 1 after a successful build](tasks/058-build-script-nopause-exit-status.md) | build |
| [059: A null field in stream data still raises](tasks/059-null-fields-in-stream-data.md) | channel, twitch |
| [060: A null item in `AvailableDrops` data still raises](tasks/060-null-fields-in-available-drops.md) | channel, twitch |
| [061: The Linux builds stop at start without the Wayland client libraries](tasks/061-linux-build-needs-wayland-libraries.md) | build, appimage, gui |
| [062: A SIGTERM to an AppImage that runs without FUSE leaves the app running](tasks/062-appimage-without-fuse-ignores-sigterm.md) | appimage |
| [063: The X11 tray icon does not respond to a click](tasks/063-x11-tray-icon-ignores-clicks.md) | gui, traybackend |
| [064: A SIGTERM leaves the app running while its AppIndicator tray icon is shown without a session bus](tasks/064-sigterm-ignored-with-appindicator-tray.md) | gui, main |
