"""`Translation` and the `TypedDict` classes in it, which name each string the app shows."""
from __future__ import annotations

from typing import TypedDict, TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import NotRequired


class StatusMessages(TypedDict):
    terminated: str
    fatal_error: str
    restarting: str
    restart_longer: str
    restart_now: str
    watching: str
    goes_online: str
    goes_offline: str
    claimed_drop: str
    no_channel: str
    no_campaign: str
    logging_level: str


class LoginMessages(TypedDict):
    unexpected_content: str


class ErrorMessages(TypedDict):
    no_connection: str
    site_down: str
    save_failed: str
    file_not_saved: str
    autostart_not_changed: str
    cannot_start: str
    folder_not_writable: str


class ArgumentMessages(TypedDict):
    title: str
    error_title: str


class GUIStatus(TypedDict):
    name: str
    idle: str
    exiting: str
    terminated: str
    restarting: str
    cleanup: str
    gathering: str
    switching: str
    fetching_inventory: str
    fetching_campaigns: str
    adding_campaigns: str


class GUITabs(TypedDict):
    main: str
    inventory: str
    settings: str
    help: str


class GUITray(TypedDict):
    notification_title: str
    minimize: str
    show: str
    quit: str


class GUILoginForm(TypedDict):
    name: str
    labels: str
    logging_in: str
    logged_in: str
    logged_out: str
    request: str
    enter_code: str
    required: str
    button: str


class GUIWebsocket(TypedDict):
    name: str
    websocket: str
    initializing: str
    connected: str
    disconnected: str
    connecting: str
    disconnecting: str
    reconnecting: str


class GUIProgress(TypedDict):
    name: str
    drop: str
    game: str
    campaign: str
    remaining: str
    drop_progress: str
    campaign_progress: str


class GUIChannelHeadings(TypedDict):
    channel: str
    status: str
    game: str
    viewers: str


class GUIChannels(TypedDict):
    name: str
    switch: str
    online: str
    pending: str
    offline: str
    headings: GUIChannelHeadings


class GUIInvFilter(TypedDict):
    name: str
    show: str
    not_linked: str
    upcoming: str
    expired: str
    excluded: str
    finished: str
    refresh: str


class GUIInvStatus(TypedDict):
    linked: str
    not_linked: str
    active: str
    expired: str
    upcoming: str
    claimed: str
    ready_to_claim: str


class GUIInventory(TypedDict):
    filter: GUIInvFilter
    status: GUIInvStatus
    starts: str
    ends: str
    allowed_channels: str
    all_channels: str
    and_more: str
    percent_progress: str
    minutes_progress: str


class GUISettingsGeneral(TypedDict):
    name: str
    language: str
    autostart: str
    tray: str
    tray_notifications: str
    dark_mode: str
    priority_mode: str
    refresh_interval: str
    restart_delay: str
    proxy: str


class GUISettingsAdvanced(TypedDict):
    name: str
    warning: str
    warning_text: str
    enable_badges_emotes: str
    available_drops_check: str


class GUIPriorityModes(TypedDict):
    priority_only: str
    ending_soonest: str
    low_availability: str


class GUIRefreshIntervals(TypedDict):
    disabled: str
    minutes: str


class GUIRestartDelays(TypedDict):
    disabled: str
    minutes: str


class GUISettingsWanted(TypedDict):
    name: str
    game: str
    source: str
    installed: str
    unlisted: str
    count: str
    empty: str


class GUISettingsDetect(TypedDict):
    name: str
    dirs: str
    add_dir: str
    remove_dir: str
    rescan: str
    scanning: str
    scan_error: str
    not_a_folder: str
    no_games: str
    failed: str
    detected: str
    restored: str
    empty: str
    no_dirs: str


class GUISettings(TypedDict):
    general: GUISettingsGeneral
    advanced: GUISettingsAdvanced
    priority_modes: GUIPriorityModes
    refresh_intervals: GUIRefreshIntervals
    restart_delays: GUIRestartDelays
    detect: GUISettingsDetect
    wanted: GUISettingsWanted
    game_name: str
    priority: str
    exclude: str
    pattern_matches: str
    pattern_empty: str
    reload: str
    reload_text: str


class GUIHelpAbout(TypedDict):
    name: str
    repository: str
    based_on: str
    based_on_text: str


class GUIHelpLinks(TypedDict):
    name: str
    inventory: str
    campaigns: str


class GUIHelpInvalidate(TypedDict):
    button: str
    text: str


class GUIHelp(TypedDict):
    about: GUIHelpAbout
    links: GUIHelpLinks
    how_it_works: str
    how_it_works_text: str
    getting_started: str
    getting_started_text: str
    invalidate: GUIHelpInvalidate


class GUIMessages(TypedDict):
    output: str
    status: GUIStatus
    tabs: GUITabs
    tray: GUITray
    login: GUILoginForm
    websocket: GUIWebsocket
    progress: GUIProgress
    channels: GUIChannels
    inventory: GUIInventory
    settings: GUISettings
    help: GUIHelp


class Translation(TypedDict):
    language_name: NotRequired[str]
    # No code reads it. It names the language of a file in English, for a reader who cannot read the file name.
    english_name: str
    status: StatusMessages
    login: LoginMessages
    error: ErrorMessages
    arguments: ArgumentMessages
    gui: GUIMessages
