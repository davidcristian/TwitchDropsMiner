# The no campaign message repeats on every stream refresh

**Status:** open
**Area:** twitch (state machine)
**Origin:** Found on 2026-10-18 while the docs were written, [twitch.md](../../modules/twitch.md#maintenance-task)
**Verified:** 2026-10-18

When no game is wanted, the `State.CHANNELS_CLEANUP` branch of `Twitch._run` in `twitch.py` (line 867) removes
every channel, prints `_("status", "no_campaign")` and enters `State.IDLE`. The text is "No active campaigns to
mine drops for. Waiting for an active campaign...". Nothing records that it was already printed.

`_maintenance_task` enters `CHANNELS_CLEANUP` on each stream refresh, every `refresh_interval` minutes plus a
random 0 to 60 seconds (`REFRESH_JITTER`), and at each time trigger in `_mnt_triggers`. `fetch_inventory`
starts that task whether or not a game is wanted, and it fills `_mnt_triggers` from every campaign that
`can_earn_within` the next hour, wanted or not. Each reload also passes through `CHANNELS_CLEANUP`. So with no
wanted game the message is printed:

- on each stream refresh: about 10 times an hour at the default of 5 minutes, and about 40 times an hour at 1
  minute;
- once per reload, which is once an hour, and once per time trigger.

The similar message for a wanted game with no live channel, `_("status", "no_channel")`, is printed once.
`State.CHANNEL_SWITCH` prints it only while `_no_channel_printed` is False and then sets that flag. `watch`
sets it back to False when a channel is watched again, and `shutdown` does the same for the next run. The
comment at the flag in `Twitch.__init__` gives the reason: "with periodic refreshes enabled, we end up in
CHANNEL_SWITCH every few minutes".

## How it was confirmed

A script ran the real `Twitch._run` with stubs for the GUI, the websocket pool, the login and the requests.
After `_run` reached `IDLE`, the script called `change_state(State.CHANNELS_CLEANUP)` four times, as the
maintenance task does on a refresh, and counted the lines given to `gui.print`:

```
no wanted game               : startup + 4 refreshes -> no_campaign printed 5x, no_channel printed 0x
wanted game, no live channel : startup + 4 refreshes -> no_campaign printed 0x, no_channel printed 1x
```

## Effect

The Output box gains one line per refresh for as long as no game is wanted, for example while the Priority
list is empty under "Priority list only", or while no campaign can progress within the next hour. At the
default interval that is about 90 lines in 8 hours. The Output box keeps every line, so earlier messages scroll
out of view. `Twitch.print` writes to the Output box only, so `log.txt` does not get these lines. The refresh
sends no Twitch request when no game is wanted.

## How it came about

The no campaign message is from the original project; its last change was "Fix no_campaign keyerror"
(2022-08-19). There, `CHANNELS_CLEANUP` ran at each reload and each time trigger, so the message was printed
about once an hour. This project added the stream refresh in "Implement auto fetch" (2026-08-03, found with
`git log -S'_no_channel_printed'`). That commit added `_no_channel_printed` for the no channel message, and
not a flag for the no campaign message, which the refresh also repeats.

## What a fix involves

Add a flag like `_no_channel_printed`: `CHANNELS_CLEANUP` prints the message only while the flag is False and
then sets it. `GAMES_UPDATE` sets it back to False when it finds a wanted game, and `shutdown` does the same,
next to `_no_channel_printed`. The message then appears once each time the app goes from a wanted game to
none. The fix sends no Twitch request.

With no wanted game, a stream refresh cannot find anything, because only a reload adds a campaign. The fix may
also skip the refresh in that case; it costs no request either way.

## History

- 2026-10-18: Opened. While the maintenance task in twitch.md was written, the no campaign print was found to
  have no flag. A run of the real `_run` with stubs counted the messages.
