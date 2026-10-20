# Twitch Drops Miner

Twitch Drops Miner is a desktop app that collects timed Twitch drops on your account while you do something else. It watches streams without downloading their video or sound, claims each drop when it is ready, and switches channels when a stream goes offline. This README calls that work *mining*.

The project started as a fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) and is developed on its own.

### How It Works:

Every 20 seconds, the app asks Twitch for the list of the newest video segments of the stream it watches, then sends a `HEAD` request for each segment. A `HEAD` request returns only headers, so no video or sound is downloaded, but Twitch counts it as watching and the drop progresses. A websocket connection receives an event when a tracked channel goes online or offline and when its viewer count changes, so the channel list stays current without extra requests.

### Features:

- Mining without the stream: no video or sound is downloaded, which saves bandwidth.
- Priority and Exclude lists: mine the games you want, in the order you want, and skip the games you don't. Entries ignore case, accents and punctuation, in any alphabet, and accept `*` and `?` wildcards, so one `Pokemon*` entry matches every Pokémon game. An entry without a wildcard matches one game only.
- Installed game detection: add your Steam or Epic game folders on the Settings tab, and the app mines every installed game that has a drop campaign. One Steam folder is enough, because the app also reads the Steam libraries it lists on other drives. Epic games installed through the Legendary or Heroic launchers, the usual way on Linux, are found too. Detected games rank below the games on your Priority list, and the Exclude list still applies to them.
- A Games Being Mined table on the Settings tab. It lists the games in the order the app picks them, and shows for each game the Priority entry that matched it or that it is installed. When a Priority entry never appears in the table, no game is mined because of it.
- A check for new streams every 5 minutes by default (1 to 30 minutes, or Never), so a channel that goes live between the hourly reloads is found within minutes. Each check costs a few requests to Twitch.
- Automatic restart after a fatal error, 10 minutes later by default (1 to 60 minutes, or Never), so a temporary problem on Twitch's side does not stop mining for the rest of the day.
- Up to `199` channels tracked at the same time, spread over several websocket connections.
- Campaigns are found through the game accounts you have linked on the [campaigns page](https://www.twitch.tv/drops/campaigns). You link them yourself.
- Stream tag and campaign checks, so the app does not mine a stream that cannot give you the drop.
- Automatic channel switching when the watched stream goes offline, or when a channel streaming a game with a higher priority goes online.
- The login session is saved in a cookies file, so you log in only once.
- Mining starts when new campaigns appear and stops when the last available drop is mined.

### Usage:

- Download and unzip [the latest release](https://github.com/davidcristian/TwitchDropsMiner/releases). Keep the app in the folder it comes in.
- Run it and press `Login` in the app. The app shows a code and opens the Twitch activation page in your browser. Enter the code there while logged in to the Twitch account you want to mine on. The app never asks for your password ([Logging in](docs/troubleshooting.md#logging-in)).
- After you log in, the app fetches every campaign and game you can mine drops for. On the Settings tab, add the games you want to the Priority list, or add your Steam or Epic game folders, then press `Reload`. The app finds the streams it can watch and starts mining. You can also switch to another channel by hand.
- The Priority Mode setting decides what happens to the other games. "Priority list only" mines only the games on your Priority list and the installed games. "Ending soonest" also mines every other game that is not excluded, starting with the campaign that ends first. "Low availability first" does the same, starting with the campaign that has the least time to spare: the least time left before it ends, compared with the watch time its drops still need.
- Link your Twitch account to your game accounts on the [campaigns page](https://www.twitch.tv/drops/campaigns), so the app can mine more games.

### Pictures:

![Main](https://user-images.githubusercontent.com/4180725/164298155-c0880ad7-6423-4419-8d73-f3c053730a1b.png)
![Inventory](https://user-images.githubusercontent.com/4180725/164298315-81cae0d2-24a4-4822-a056-154fd763c284.png)
![Settings](https://user-images.githubusercontent.com/4180725/164298391-b13ad40d-3881-436c-8d4c-34e2bbe33a78.png)

### Notes:

> [!WARNING]
> Because of how Twitch tracks drop progress, watching a stream on the account the app uses, in a browser or anywhere else, usually breaks mining. The app then shows false progress and can get stuck on the current drop. Avoid watching streams on that account while the app runs.

> [!CAUTION]
> The app stores your login session in the `cookies.jar` file and restores it on every run. Keep this file private: anyone who has it can use your Twitch account without knowing your password.

> [!IMPORTANT]
> Twitch may email you a "New Login" notice after you log in through the app. This is normal, and you can check that the notice shows your own IP address. The notice can name a browser you did not use, such as "Chrome".

> [!NOTE]
> The remaining time counts down one minute and then stops. It starts again when Twitch next reports the drop's progress, which happens at most 20 seconds after the timer reaches zero. The seconds are an estimate and do not change how fast the drop progresses. Twitch sometimes skips a progress report or reports progress for the wrong drop, and the app handles both cases.

> [!NOTE]
> Running from source needs Python 3.10 or newer.

### Notes about the Windows build:

- To achieve a portable-executable format, the application is packaged with PyInstaller into an `EXE`. Some antivirus engines (including Windows Defender) might report the packaged executable as a trojan, because PyInstaller has been used by others to package malicious Python code in the past. These reports can be safely ignored. If you absolutely do not trust the executable, you'll have to install Python yourself and run everything from source.
- The executable uses the `%TEMP%` directory for temporary runtime storage of files, that don't need to be exposed to the user (like compiled code and translation files). For persistent storage, the directory the executable resides in is used instead.
- The autostart feature is implemented as a registry entry to the current user's (`HKCU`) autostart key. It is only altered when toggling the respective option. If you relocate the app to a different directory, the autostart feature will stop working, until you toggle the option off and back on again

### Notes about the Linux build:

- The Linux app is built and distributed using two distinct portable-executable formats: [AppImage](https://appimage.org/) and [PyInstaller](https://pyinstaller.org/).
- There are no major differences between the two formats, but if you're looking for a recommendation, use the AppImage.
- The Linux app should work out of the box on any modern distribution, as long as it has `glibc>=2.35`, plus a working display server.
- Every feature of the app is expected to work on Linux just as well as it does on Windows.
- The size of the Linux app is significantly larger than the Windows app due to the inclusion of the `gtk3` library (and its dependencies), which is required for proper system tray/notifications support.
- As an alternative to the native Linux app, you can run the Windows app via [Wine](https://www.winehq.org/) instead. It works really well!

### Notes about the macOS build:

- The macOS version is packaged using PyInstaller into a standalone `.app` bundle, distributed as a ZIP archive.
- Since this application is not signed with a paid Apple Developer Certificate, **macOS Gatekeeper will block it** on the first run (saying it "The application is damaged and can't be opened").
  - **To fix this**: Either open the Terminal in the folder the app is in (or navigating with `cd path/to/folder`) and enter `xattr -cr Twitch Drops Miner.app` or just type `xattr -cr ` (make sure to put a space at the end), drag and drop the `Twitch Drops Miner.app` file into the terminal window (this will auto-fill the path) and enter
- Persistent files (like `cookies.jar`, `settings.json`, `lock.file` and the `cache` folder) are stored inside the application bundle in `Twitch Drops Miner.app/Contents/MacOS` (to access them Right-click the application and select `Show Package Contents`)

### Advanced Usage:

To run the latest `master` from source or build your own executable, see [docs/building.md](docs/building.md).

### Support:

- [docs/troubleshooting.md](docs/troubleshooting.md) explains common problems, the command line flags and how to get a log.
- This project's code differs from the original, so do not report its problems on DevilXD/TwitchDropsMiner.

### Project goals:

Twitch Drops Miner is built for these goals:

- Twitch drops only. The app collects drops and nothing else.
- Easy to use. It has a GUI and comes as a ready-to-run executable that needs no Python installation.
- A helper that runs in the background. It starts with your PC, runs through the day and closes when the PC shuts down. It should run for at least 24 hours without help.
- Little attention. The app finds new streams, mines your installed games and restarts after a fatal error by itself, so checking it once or twice a day is enough.
- Low Twitch traffic. Twitch sees no more traffic than a diligent person would cause, because the app runs on your own account and a burst of requests puts that account at risk. Requests to GQL, the GraphQL API that the Twitch website uses, are limited to 5 per second. A full reload, which can send thousands of GQL operations in batches of 20, runs at startup, once an hour, after a restart that follows a fatal error, after a drop is claimed or Twitch sends a reward notification, and when you press `Invalidate` or `Reload`. The checks for new streams between reloads cost a few requests each.
- One account. The app mines on a single Twitch account.

The app is not built for:

- Channel points.
- Other sites that depend on watching Twitch streams.
- Running without a GUI, or with only a console.
- Running as a 24/7 miner on a remote server, in Docker or in any other remote deployment.
- Unattended use with 100% uptime. A restart after a fatal error waits 10 minutes by default.
- More than one account.
- Campaigns that your account is not linked to.
- Anything that raises Twitch traffic above what a diligent person would cause.
- Notifications beyond the current tray notifications, such as email or webhooks.

Features from this list will not be added.

### License:

This project is licensed under the [GNU Affero General Public License v3](LICENSE). Code from the original project stays under the [MIT License](LICENSE.MIT).

### Credits:

This project started as a fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) by DevilXD, released under the MIT License (see [LICENSE.MIT](LICENSE.MIT)). The people below contributed to that project.

<!---
Note: The translations credits are sorted alphabetically, based on their English language name.
When adding a new entry, please ensure to insert it in the correct place in the second section.
Non-translations related credits should be added to the first section instead.

Note: When adding a new credits line below, please add two trailing spaces at the end
of the previous line, if they aren't already there. Doing so ensures proper markdown
rendering on Github. In short: Each credits line should end with two trailing spaces,
placed past the period character at the end.

• Last line can have the two trailing spaces omitted.
• Please ensure your editor won't trim the trailing spaces upon saving the file.
• Please ensure to leave a single empty new line at the end of the file.
-->

@guihkx: for the CI script, CI maintenance, and everything related to Linux builds.  
@kWAYTV: for the implementation of the dark mode theme.  
@crocchetto: for the macOS port.  

@Bamboozul: for the entirety of the Arabic (العربية) translation.  
@Suz1e: for the entirety of the Chinese (简体中文) translation and revisions.  
@wwj010, @zhangminghao1989, @Self4215: for the Chinese (简体中文) translation corrections and revisions.  
@Ricky103403: for the entirety of the Traditional Chinese (繁體中文) translation.  
@LusTerCsI: for the Traditional Chinese (繁體中文) translation corrections and revisions.  
@nwvh: for the entirety of the Czech (Čeština) translation.  
@Kjerne: for the entirety of the Danish (Dansk) translation.  
@lmdpocus: for the entirety of the Dutch (Nederlandse) translation.  
@Rensoraa: for the Traditional Dutch (Nederlandse) translation corrections and revisions.  
@roobini-gamer: for the entirety of the French (Français) translation.  
@Calvineries: for the French (Français) translation revisions.  
@ThisIsCyreX: for the entirety of the German (Deutsch) translation.  
@Nagyhoho1234: for the entirety of the Hungarian (Magyar) translation.  
@Eriza-Z: for the entirety of the Indonesian translation.  
@casungo: for the entirety of the Italian (Italiano) translation.  
@ShimadaNanaki: for the entirety of the Japanese (日本語) translation.  
@biroman: for the entirety of the Norwegian (Norsk) translation.  
@Patriot99: for the Polish (Polski) translation and revisions (co-authored with @DevilXD).  
@zarigata: for the entirety of the Portuguese (Português) translation.  
@Sergo1217: for the entirety of the Russian (Русский) translation.  
@kilroy98, @flamesv: for the Russian (Русский) translation corrections and revisions.  
@Shofuu: for the entirety of the Spanish (Español) translation and revisions.  
@Forero-0: for the Spanish (Español) translation revisions.  
@alikdb: for the entirety of the Turkish (Türkçe) translation.  
@DogancanYr, @Elderly-Emre, @Hweord: for the Turkish (Türkçe) translation corrections and revisions.  
@Nollasko: for the entirety of the Ukrainian (Українська) translation and revisions.  
@kilroy98: for the Ukrainian (Українська) translation corrections and revisions.  
