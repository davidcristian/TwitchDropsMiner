# The Inventory tab hides campaigns that are mined because the game is installed

**Status:** done 2026-10-23
**Area:** gui (Inventory tab)
**Origin:** Found on 2026-10-18 while the docs were written, [gui.md](../../modules/gui.md#the-window)
**Verified:** 2026-10-23

`InventoryOverview._update_visibility(campaign)` in `gui.py` shows a campaign's frame only when all of these
hold:

1. `campaign.required_minutes > 0`;
2. the "Not linked" filter is on, or `campaign.eligible`;
3. the campaign is active, or it is upcoming with the "Upcoming" filter on, or expired with the "Expired" filter
   on;
4. the "Excluded" filter is on, or `not listed_excluded and not priority_only or listed_priority`;
5. the "Finished" filter is on, or the campaign is not finished.

`listed_excluded` and `listed_priority` come from `any_match` over the Exclude and the Priority patterns, and
`priority_only` is true under "Priority list only". Python evaluates condition 4 as
`(not listed_excluded and not priority_only) or listed_priority`. The method never reads
`settings.detected_games`.

Under "Priority list only", the default mode, `State.GAMES_UPDATE` in `Twitch._run` mines every game whose rank
is below `MAX_INT`, and a detected game gets such a rank
([ADR-0004](../../adr/ADR-0004-installed-game-detection.md)). So a campaign for a detected game that no Priority
entry matches is mined, and the Inventory tab hides it. Only the "Excluded" filter shows it, and that filter
also shows the campaigns of every other game. The other four filters do not change condition 4.

## How it was confirmed

`_update_visibility` was called on a stand-in object with a stub campaign for the game `Warframe` (active,
eligible, 60 minutes, not finished) and `detected_games` set to `["Warframe"]`:

| Priority mode | Priority list | Filters on | Shown |
| --- | --- | --- | --- |
| Priority list only | empty | Upcoming (the default) | no |
| Priority list only | empty | only one of Not linked, Upcoming, Expired or Finished | no |
| Priority list only | empty | only Excluded | yes |
| Priority list only | `Warframe` | Upcoming | yes |
| Ending soonest | empty | Upcoming | yes |

## A second effect of the same condition

Because of the `or`, condition 4 holds whenever `listed_priority` is true, even when `listed_excluded` is true
too. So a game that matches both lists is shown with the "Excluded" filter off, in every Priority mode.
`State.GAMES_UPDATE` checks the Exclude patterns as a separate condition, so it never mines that game. The same
stand-in with `Warframe` on both lists returned shown for "Ending soonest" and for "Priority list only". A
detected game on the Exclude list is hidden, which matches what is mined.

## Effect on a user

A user who mines through game detection alone, with an empty Priority list and the default mode, opens the
Inventory tab and sees none of the campaigns the app mines, while the Main tab shows the drop being mined and
the Games Being Mined table on the Settings tab lists the game. A game on both lists appears in the Inventory
tab although it is not mined.

## What a fix involves

Make condition 4 follow the rule of `State.GAMES_UPDATE`: the "Excluded" filter is on, or the game matches no
Exclude entry and, under "Priority list only", it matches a Priority entry or is in `detected_games`. That is
`excluded or (not listed_excluded and (not priority_only or listed_priority or detected))`, with
`detected = game_name in self._settings.detected_games`. `SettingsPanel.set_wanted_games` already reads
`detected_games` the same way. A game on both lists is then hidden unless the "Excluded" filter is on.

The preview's settings mock under `if __name__ == "__main__":` already has `detected_games=[]`. Cost: no Twitch
requests. The change is a GUI change, so it is run in `python gui.py`.

How it came about: condition 4 has had this form since 2022 in the original project ("Inventory tab exclude option
takes priority_only into account"). Installed game detection, on 2026-08-24, let "Priority list only" mine games
that no Priority entry matches, and it did not change this method. The pattern matching of the lists replaced
the name lookups in the condition on the same day.

## History

- 2026-10-18: Opened while the docs were written. `_update_visibility` was called with a stub campaign under
  each filter setting, and `git log -S` showed the commits that formed the condition.
- 2026-10-23: Done. The claim held: a suite test under Xvfb found the campaign of a detected game hidden under
  "Priority list only", and the campaign of a game on both lists shown in every Priority mode. Condition 4 is now
  `excluded or (not listed_excluded and (not priority_only or listed_priority or detected))`.
  `tests/test_gui_inventory.py` checks each list and Priority mode, with the "Excluded" filter on and off.
