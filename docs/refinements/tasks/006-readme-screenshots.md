# The README pictures show the original app

**Status:** done 2026-10-23
**Area:** README
**Origin:** found on 2026-10-18 while the docs were written
**Verified:** 2026-10-23

The [Pictures](../../../README.md#pictures) section of README.md shows three images, Main, Inventory and
Settings, hosted under `user-images.githubusercontent.com/4180725/`. The original project added them on
2022-04-20. At that date the code had three tabs, the window title `Twitch Drops Miner v12 (by DevilXD)`, and
a Settings tab with a General frame (Autostart, Autostart into tray, Priority only, Proxy), the Priority and
Exclude lists and the Reload button.

The Settings tab today has these parts that the images cannot show. The labels are the English strings in
`default_translation` in `translate.py`, placed by `SettingsPanel` in `gui.py`:

- The Games Being Mined table, with its `#`, Game and Matched by columns.
- The Detected Games frame, with the Game folders list and the Rescan button.
- "Check for new streams every:" and "Restart after a crash after:" in General.
- "Priority mode:" with Priority list only, Ending soonest and Low availability first, in place of the
  Priority only checkbox.
- "Tray notifications:", "Dark mode:" and the language selector in General.
- The Advanced frame and its two checkboxes.
- The "Game name or pattern" placeholder of the Priority and Exclude entries, which accept `*` and `?`.

The Help tab has no picture at all. Its parts are About, Useful Links, How It Works, Getting Started and the
Invalidate button.

## What closes it

New pictures of all four tabs, stored in the repo, for example in `docs/assets/`, and linked from README.md
with relative paths. Neither `build.spec` nor `appimage/AppImageBuilder.yml` packages `docs/`, so the images
add to the repo but not to the builds.

`python gui.py` opens the GUI with mock data and no login, so its pictures show no real account. On every run
it downloads the mock's campaign and reward images with two GET requests to `static-cdn.jtvnw.net`, Twitch's
image server, because the mock never saves `cache/mapping.json`, the record of the cached images.
[gui-preview-headless.md](../../runbooks/gui-preview-headless.md) covers taking them without a display; they
can also be taken on Windows. The mock sets `game_dirs` and `detected_games` to empty lists and does not call
`SettingsPanel.set_wanted_games`. A picture from it therefore shows the empty texts
`Nothing detected yet - add a game folder below.` and `Nothing worked out yet - press Reload below.` To show
the two new frames filled in, the mock needs sample folders, detected games and a call to `set_wanted_games`.
A picture of the full app shows the account's user ID and channels, so it is checked before it is committed.

Cost: no GQL requests, and the two image requests of each preview run.

## History

- 2026-10-18: Opened. Found while the docs were written, after comparing the Settings tab in `gui.py` with the code
  of the date the pictures were added.
- 2026-10-23: Closed. `docs/assets/` holds `main.png`, `inventory.png`, `settings.png` and `help.png`, linked
  from README.md and taken with the steps in
  [gui-preview-headless.md](../../runbooks/gui-preview-headless.md#take-the-readme-pictures), with the network
  blocked. Each is 1600 by 900 pixels with 256 colors, 18 to 35 KB. The mock's settings now name two Priority
  entries, two game folders and two detected games, and it calls `set_wanted_games`. Its campaign is active and
  linked, and its game is detected, so the Inventory tab shows it. Its `request` returns `icons/pickaxe.ico`
  for each image, so the preview sends no request. The alternative, blank artwork, shows the white squares of a
  failed download.
