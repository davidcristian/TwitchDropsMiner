# The README platform notes break the prose rules

**Status:** open
**Area:** README
**Origin:** found on 2026-10-18 while the docs were written
**Verified:** 2026-10-18

The README rewrite of 2026-10-18 left three sections in the original project's wording: "Notes about the
Windows build", "Notes about the Linux build" and "Notes about the macOS build". They contain no banned word
and no dash, but they break the [Prose](../../../AGENTS.md#prose) rules against hedging, idioms, subjective
claims and long sentences that hold several ideas. The lines below are quoted from README.md.

## Hedging and subjective claims

- "Some antivirus engines (including Windows Defender) might report the packaged executable as a trojan,
  because PyInstaller has been used by others to package malicious Python code in the past."
- "These reports can be safely ignored."
- "If you absolutely do not trust the executable, you'll have to install Python yourself and run everything
  from source."
- "There are no major differences between the two formats, but if you're looking for a recommendation, use the
  AppImage."
- "The Linux app should work out of the box on any modern distribution, as long as it has `glibc>=2.35`, plus
  a working display server." This line also uses an idiom, "out of the box".
- "Every feature of the app is expected to work on Linux just as well as it does on Windows."
- "The size of the Linux app is significantly larger than the Windows app due to the inclusion of the `gtk3`
  library (and its dependencies), which is required for proper system tray/notifications support."
- "As an alternative to the native Linux app, you can run the Windows app via [Wine](https://www.winehq.org/)
  instead. It works really well!"

## Long sentences and other defects

- The macOS fix is one sentence of 59 words that describes two procedures and has no final period: "**To fix
  this**: Either open the Terminal in the folder the app is in (or navigating with `cd path/to/folder`) and
  enter `xattr -cr Twitch Drops Miner.app` or just type `xattr -cr ` (make sure to put a space at the end),
  drag and drop the `Twitch Drops Miner.app` file into the terminal window (this will auto-fill the path) and
  enter". Its first command is also wrong: without quotes, the shell passes `Twitch`, `Drops` and `Miner.app`
  to `xattr` as three paths. The correct form is `xattr -cr "Twitch Drops Miner.app"`.
- "Since this application is not signed with a paid Apple Developer Certificate, **macOS Gatekeeper will block
  it** on the first run (saying it "The application is damaged and can't be opened")." The phrase "saying it"
  before the quoted message is not grammatical.
- "The executable uses the `%TEMP%` directory for temporary runtime storage of files, that don't need to be
  exposed to the user (like compiled code and translation files)." The comma before "that" separates the
  clause from the noun it describes.
- Three sentences have no final period: the autostart note ("...until you toggle the option off and back on
  again"), the macOS fix above, and the note on persistent files ("...select `Show Package Contents`)").

## What closes it

Rewrite the three sections in the style of the rest of README.md: one fact per sentence, the literal verb, no
hedging. Keep every fact: the PyInstaller `EXE` and the antivirus reports, the `%TEMP%` use, the `HKCU`
autostart key, the AppImage and PyInstaller formats, `glibc>=2.35`, the `gtk3` library, Wine, the Gatekeeper
message, the `xattr` command and the `Contents/MacOS` folder. A claim that cannot be stated as a fact, such as
"These reports can be safely ignored" or "It works really well!", is removed. A fact that also belongs to
[troubleshooting.md](../../troubleshooting.md) is linked there instead of repeated.

Cost: no Twitch requests.

## History

- 2026-10-18: Opened. Found while the docs were written. `git log -p` shows that the README rewrite of the
  same day removed only an issue link from these lines, and the byline removal only renamed the app bundle in
  the macOS notes. Both versions of the `xattr` command leave the bundle name unquoted.
