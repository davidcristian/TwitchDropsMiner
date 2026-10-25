"""`default_translation`: the English strings, which every other language falls back to."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .translation import Translation


default_translation: Translation = {
    "english_name": "English",
    "status": {
        "terminated": "\nApplication Terminated.\nClose the window to exit the application.",
        "fatal_error": "Fatal error encountered:\n",
        "restarting": "Restarting automatically at {time}...",
        "restart_longer": (
            "The error came less than an hour after the last restart, "
            "so the wait is longer than the setting: {minutes} minutes."
        ),
        "restart_now": "Press Reload on the Settings tab to restart now.",
        "watching": "Watching: {channel}",
        "goes_online": "{channel} goes ONLINE, switching...",
        "goes_offline": "{channel} goes OFFLINE, switching...",
        "claimed_drop": "Claimed drop: {drop}",
        "no_channel": "No available channels to watch. Waiting for an ONLINE channel...",
        "no_campaign": "No active campaigns to mine drops for. Waiting for an active campaign...",
        "logging_level": "Logging level: {level}",
    },
    "login": {
        "unexpected_content": (
            "Unexpected content type returned, usually due to being redirected. "
            "Do you need to login for internet access?"
        ),
        "no_code": "The login could not get a code from Twitch: {message}",
        "token_rejected": "Twitch did not accept the token.",
        "unknown_client": "The token belongs to a Twitch client that the app does not know.",
    },
    "error": {
        "site_down": "Twitch is down, retrying in {seconds} seconds...",
        "no_connection": "Cannot connect to Twitch, retrying in {seconds} seconds... ({url})",
        "save_failed": "Saving failed, retrying at the next reload: {error}",
        "file_not_saved": "Could not save {file}: {error}",
        "autostart_not_changed": "Could not change the autostart entry: {error}",
        "cannot_start": "Cannot start",
        "folder_not_writable": (
            "The application cannot write to the folder it runs from, where it keeps its files:\n\n{error}\n\n"
            "Move the application to a folder you can write to."
        ),
    },
    "arguments": {
        "title": "Twitch Drops Miner",
        "error_title": "Argument Parser Error",
    },
    "gui": {
        "output": "Output",
        "status": {
            "name": "Status",
            "idle": "Idle",
            "exiting": "Exiting...",
            "terminated": "Terminated",
            "restarting": "Restarting at {time}",
            "cleanup": "Cleaning up channels...",
            "gathering": "Gathering channels...",
            "switching": "Switching the channel...",
            "fetching_inventory": "Fetching inventory...",
            "fetching_campaigns": "Fetching campaigns...",
            "adding_campaigns": "Adding campaigns to inventory... {counter}",
        },
        "tabs": {
            "main": "Main",
            "inventory": "Inventory",
            "settings": "Settings",
            "help": "Help",
        },
        "tray": {
            "notification_title": "Mined Drop",
            "minimize": "Minimize to Tray",
            "show": "Show",
            "quit": "Quit",
        },
        "login": {
            "name": "Login Form",
            "labels": "Status:\nUser ID:",
            "logged_in": "Logged in",
            "logged_out": "Logged out",
            "logging_in": "Logging in...",
            "required": "Login required",
            "request": "Please log in to continue.",
            "enter_code": "Enter this code on Twitch's device activation page: {code}",
            "button": "Login",
            "token": "Token:",
            "token_button": "Use token",
        },
        "websocket": {
            "name": "Websocket Status",
            "websocket": "Websocket #{id}:",
            "initializing": "Initializing...",
            "connected": "Connected",
            "disconnected": "Disconnected",
            "connecting": "Connecting...",
            "disconnecting": "Disconnecting...",
            "reconnecting": "Reconnecting...",
        },
        "progress": {
            "name": "Campaign Progress",
            "drop": "Drop:",
            "game": "Game:",
            "campaign": "Campaign:",
            "remaining": "{time} remaining",
            "drop_progress": "Progress:",
            "campaign_progress": "Progress:",
        },
        "channels": {
            "name": "Channels",
            "switch": "Switch",
            "online": "ONLINE  ✔",
            "pending": "OFFLINE ⏳",
            "offline": "OFFLINE ❌",
            "headings": {
                "channel": "Channel",
                "status": "Status",
                "game": "Game",
                "viewers": "Viewers",
            },
        },
        "inventory": {
            "filter": {
                "name": "Filter",
                "show": "Show:",
                "not_linked": "Not linked",
                "upcoming": "Upcoming",
                "expired": "Expired",
                "excluded": "Excluded",
                "finished": "Finished",
                "refresh": "Refresh",
            },
            "status": {
                "linked": "Linked ✔",
                "not_linked": "Not Linked ❌",
                "active": "Active ✔",
                "upcoming": "Upcoming ⏳",
                "expired": "Expired ❌",
                "claimed": "Claimed ✔",
                "ready_to_claim": "Ready to claim ⏳",
            },
            "starts": "Starts: {time}",
            "ends": "Ends: {time}",
            "allowed_channels": "Allowed Channels:",
            "all_channels": "All",
            "and_more": "and {amount} more...",
            "percent_progress": "{percent} of {minutes} minutes",
            "minutes_progress": "{minutes} minutes",
        },
        "settings": {
            "general": {
                "name": "General",
                "language": "Language 🌐 (requires restart): ",
                "autostart": "Autostart: ",
                "tray": "Autostart into tray: ",
                "tray_notifications": "Tray notifications: ",
                "dark_mode": "Dark mode: ",
                "priority_mode": "Priority mode: ",
                "refresh_interval": "Check for new streams every: ",
                "restart_delay": "Restart after a crash after: ",
                "proxy": "Proxy (requires restart):",
            },
            "advanced": {
                "name": "Advanced",
                "warning": "Warning!",
                "warning_text": (
                    "These options will cause the miner to misbehave.\n"
                    "If you're experiencing any issues, "
                    "make sure all of these options are disabled."
                ),
                "enable_badges_emotes": "Enable partial support for badges and emotes: ",
                "available_drops_check": "Enable extra available drops check: ",
            },
            "priority_modes": {
                "priority_only": "Priority list only",
                "ending_soonest": "Ending soonest",
                "low_availability": "Low availability first",
            },
            "refresh_intervals": {
                "disabled": "Never (hourly reload only)",
                "minutes": "{minutes} min",
            },
            "restart_delays": {
                "disabled": "Never (stay stopped)",
                "minutes": "{minutes} min",
            },
            "wanted": {
                "name": "Games Being Mined",
                "game": "Game",
                "source": "Matched by",
                "installed": "installed",
                "unlisted": "not on any list",
                "count": "Mining {count} game(s), highest priority first.",
                "empty": "Nothing worked out yet - press Reload below.",
            },
            "detect": {
                "name": "Detected Games",
                "dirs": "Game folders:",
                "add_dir": "Add a Steam or Epic games folder",
                "remove_dir": "Remove the selected folder",
                "rescan": "Rescan",
                "scanning": "Scanning game folders...",
                "scan_error": "Game scan: {error}",
                "not_a_folder": "Not a directory: {path}",
                "no_games": "No Steam or Epic games found in: {path}",
                "failed": "{path}: {reason}",
                "detected": "{count} of {total} installed games matched.",
                "restored": "{count} games from the last scan.",
                "empty": "Nothing detected yet - add a game folder below.",
                "no_dirs": "No folders added.",
            },
            "game_name": "Game name or pattern",
            "priority": "Priority",
            "exclude": "Exclude",
            "pattern_matches": "\"{pattern}\" matches {count} game(s): {games}",
            "pattern_empty": (
                "\"{pattern}\" doesn't match any game with a campaign right now."
            ),
            "reload": "Reload",
            "reload_text": "Most changes require a reload to take an immediate effect: ",
        },
        "help": {
            "about": {
                "name": "About",
                "repository": "Repository: ",
                "based_on": "Based on: ",
                "based_on_text": "TwitchDropsMiner by DevilXD",
            },
            "links": {
                "name": "Useful Links",
                "inventory": "See Twitch inventory",
                "campaigns": "See all campaigns and manage account links",
            },
            "how_it_works": "How It Works",
            "how_it_works_text": (
                "Every several seconds, the application pretends to watch a particular stream "
                "by fetching stream metadata - this is enough to advance the drops. "
                "Note that this completely bypasses the need to download "
                "any actual stream of video and sound. "
                "To keep the status (ONLINE or OFFLINE) of the channels up-to-date, "
                "there's a websocket connection established that receives events about streams "
                "going up or down, or updates regarding the current number of viewers."
            ),
            "getting_started": "Getting Started",
            "getting_started_text": (
                "1. Login to the application.\n"
                "2. Ensure your Twitch account is linked to all campaigns "
                "you're interested in mining.\n"
                "3. If you're interested in mining everything possible, "
                "change the Priority Mode to anything other than \"Priority list only\" "
                "and press on \"Reload\".\n"
                "4. If you want to mine specific games first, use the \"Priority\" list "
                "to set up an ordered list of games of your choice. "
                "Games from the top of the list will be attempted to be mined first, "
                "before the ones lower down the list.\n"
                "5. Keep the \"Priority mode\" selected as \"Priority list only\", "
                "to avoid mining games that are not on the priority list. "
                "Or not - it's up to you.\n"
                "6. Use the \"Exclude\" list to tell the application "
                "which games should never be mined.\n"
                "7. Changing the contents of either of the lists, or changing "
                "the \"Priority mode\", requires you to press on \"Reload\" "
                "for the changes to take an effect."
            ),
            "invalidate": {
                "button": "Invalidate",
                "text": "Invalidate the authentication token (log out):",
            },
        },
    },
}
