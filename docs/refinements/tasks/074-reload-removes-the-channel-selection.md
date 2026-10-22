# A reload removes the selection in the channel list

**Status:** open
**Area:** twitch (state machine), gui
**Origin:** Found on 2026-10-22 while a `Switch` press during a reload was made to run,
[ADR-0017](../../adr/ADR-0017-state-requests.md)
**Verified:** 2026-10-22

`GAMES_UPDATE` in `Twitch._run` sets `full_cleanup`, so the `CHANNELS_CLEANUP` that follows removes every
tracked channel. `Channel.remove` calls `ChannelList.remove` in `gui.py`, which deletes the channel's row from
the `ttk.Treeview`. Deleting a row removes it from the selection, and a row inserted again with the same ID is
not selected. `CHANNELS_FETCH` reads the selection with `ChannelList.get_selection` only to restore it after it
rebuilds the list, and after a full cleanup the list is empty by then. So `CHANNEL_SWITCH` finds no selected
channel and watches the first channel by priority for which `should_switch` is true.

`CHANNEL_SWITCH` watches the selected channel first whenever `can_watch` accepts it. A stream refresh keeps
the selection while the channel stays in the list ([ADR-0003](../../adr/ADR-0003-stream-refresh.md)), so the
selected channel stays watched. Every reload ends that: the hourly one, one after a claim or a reward
notification, and a `Reload` press. A `Switch` press during a reload now runs as the reload's own
`CHANNEL_SWITCH`, but the channel it chose is not watched.

## What a fix involves

`CHANNELS_CLEANUP` stores the ID of the selected channel before a full cleanup, and `CHANNELS_FETCH` selects
the channel with that ID again when the new list has it. The selection then outlasts every reload, and a
selected channel stays watched after the hourly reload, which needs a decision of its own. Twitch requests:
none.

## History

- 2026-10-22: Opened. While a `Switch` press during a reload was made to run
  ([012](012-button-requests-lost-during-a-fetch.md)), its `CHANNEL_SWITCH` was found to read no selection
  after the full cleanup. A `ttk.Treeview` under Xvfb showed that `delete` removes the row from the selection
  and that inserting the row again leaves it unselected.
