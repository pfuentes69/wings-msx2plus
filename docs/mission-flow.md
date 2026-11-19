# Mission complete and the next mission (P4)

Done 2026-11-17. After the mission's last island falls, the player flies
back to the carrier, lands and goes down the lift. The hold then briefs the
next mission instead of servicing the plane, and the loadout starts it.

## What the original does

From the Amiga executable (CODE-hunk offsets, A4-relative variables;
[research/amiga-island-combat.md](research/amiga-island-combat.md)):

- **0x5694**, when the mission's last objective falls (the last island
  with targets, and no mission ships left):
  - the mission number within the rank (`-$5c3e`) goes up;
  - past the rank's last mission, it goes back to 1 and the rank (`-$5c40`)
    goes up, at most to the 7th. The promotion flag (`-$5ca1`) is set even
    at the top rank;
  - the ticker shows "Good work ! You are ordered to return to carrier to
    receive your next mission !", or, with a promotion, "Congratulations!
    You have completed your mission!! You are instructed to return to
    carrier for victory ceremony!!";
  - the mission-complete flag `-$5c42` is set.
- **0x0122**, in the main loop: when the plane is in the hold (`-$5c9a`,
  set by 0x3684 when a plane is put there) and the mission is complete:
  - it clears both flags;
  - a promotion gives one more plane (`-$5ca2`);
  - it goes through the mission set-up again (the briefing `-$7e42` →
    0x8590, the map load `-$7f74` → 0x2adc) to a new plane in the hold (0xd2).

| Table | Address | Values |
| --- | --- | --- |
| Missions per rank | `-$5ab6` | 3, 3, 2, 2, 1, 1, 3 |
| Map by rank × 4 + mission (1-based) | `-$7b9f` | rank 0: 0, 1, 2; rank 1: 3, 4, 5; rank 2: 6, 7; rank 3: 8, 9; rank 4: 10; rank 5: 11; rank 6: 12, 13, 14 |

The 15 maps are those 15 entries. Map 0 is rank 0's first mission, the
port's mission A. Rank selection starts the rank's first mission (0x84d0).

## The port

- **Game state** (`core/game.c`, now banked in segment 27):
  - `MissionProgress` holds the map and the mission number (bytes 18, 19 of
    the save, version 2).
  - `Game_AdvanceMission` is 0x5694's arithmetic. `Game_NextMission` is the
    hold: the promotion's plane (the HUD's one digit caps lives at 9), oil
    and fuel full, then `GAME_BRIEFING`.
- **The frame loop** (`world_flight.c`) advances the mission once, the frame
  the last island falls. With a promotion, the ticker gets
  `ISLAND_MESSAGE_PROMOTION` and the second string.
- **In the hold** with the island complete, `ReadActions` calls
  `Game_NextMission`, not the service.
- **A sortie started from the loadout** (game start or the next mission)
  restores the island (`Island_Reset`, which also rebuilds wrecked huts)
  and stops the ticker. Before this, a new game after game over kept the
  cleared island.
- **Ctrl-R** now wins over a fire button pressed with it on the elevator.
  Before, the lift took the press and swallowed the restart.

## The briefing (2026-11-19)

The original's briefing (0x8590) draws `rank.iff` (the frame with "Rank:",
"Mission:", "Mission objectives:", "Islands:", "Ships:") and prints into it:
- the rank's short name (table `-$56ee`: Midshipman, Ensign, Lt. Jr. Gr.,
  Lieutenant, Lt.Commd, Commander, Captain);
- the mission number within the rank (`-$5c3e`, `%d`);
- the mission's islands (`-$5c7c`) and ships (`-$5c8e`), totals kept beside
  the counters of those left (`-$5c7b`, `-$5c8d`).

It then waits 240 frames (4.8 s) or a button; Ctrl-R restarts. The port
shows the same values in the menu font (`msx/menu.c`; the artwork comes
later): the counts are the map's islands with targets and ships to sink,
taken at boot from the mission set-up (`g_BriefIslands`, `g_BriefShips`),
and `Game_Wait` (core/game.c) closes it after 240 PAL frames (288 NTSC
fields). Rank selection lists the names of the original's screen
(`selectrank`: Midshipman, Ensign, Lt. Junior Grade, Lieutenant,
Lt. Commander, Commander, Captain, Return from R&R).

## The end of a game and the high scores (2026-11-19)

From the original ([research/amiga-hiscores.md](research/amiga-hiscores.md)):
the last plane lost shows a plate reading "THE END" (0xaf7c) for 150
frames, or until a button after 30. Then (0x9856, also after Ctrl-R) a
score above the table's tenth takes a name, typed on the keyboard (16
characters at most), and the table of the ten best is shown every time,
for 1800 frames or until a fire button; then rank selection. A new entry
goes below the scores it does not beat. The table starts empty (the
original saves it as the file `highscore`).

**Set aside (2026-11-19):** the port can't save the table, so the name
entry and the table are built only with `WINGS_HIGH_SCORES` (off). Without
it "THE END" goes back to rank selection (after 150 frames, or a button
after 30) and Ctrl-R starts a new game at once; the typing code is not in
the ROM. `tests/test_game.py` builds the game both ways. With the switch:
- `GAME_OVER` is "THE END", then `GAME_NAME` (if the score qualifies) and
  `GAME_SCORES`; `Game_Wait` runs their timers (PAL frames, NTSC fields
  6/5 as many). Ctrl-R from play, pause, the menus or the service goes
  the same way; at rank selection and on these screens it does nothing.
- The table (`g_HighScores`, 10 × score, rank, 16-character name) is in
  RAM: it lasts until the machine is switched off.
- Typing (`Menu_Key`, the keyboard matrix scanned while the name is
  entered, every VBlank): A..Z, 0..9, space and `.` (the menu font's),
  Backspace or Del to delete. Return, a fire button, Up or Down end it; an
  empty name is accepted. Keys already down when it opens are not typed.
  The VBlank interrupt queues the keys in order while the name is typed
  (`Input_Keys`, msx/input_sampler.c), so a tap during a redraw is kept;
  the space bar types a space then, not fire (the joystick's button still
  ends the name).
  The original's cursor movement within the name is not done.
- The rows show position, score, rank and name; the rank is the short name,
  as the full ones don't fit 256 px in this font.
- The plate, the ACES banner, the slab and the font are for the artwork
  step.

Not yet:
- only maps a and j are built, so every mission flies the ROM's map again;
- no victory ceremony screen;
- the briefing's artwork (rank.iff) and the original font.

## Verification

- `tests/test_game.py` covers:
  - the whole rank and mission progression (maps, promotions, staying at
    the top rank);
  - the hold's next mission (lives, oil, fuel, briefing → loadout → sortie);
  - rank selection's first mission.
- `verify_p0` now flies back after `open_sea_right`, lands
  (`return_arrest`, `return_landed`) and goes down the lift. At the hold it
  requires the briefing with rank 0, mission 2, map 1 and the same lives
  (`mission_briefing`). It then goes through the loadout to a sortie with
  the island restored and no ticker (`mission_two`), before the Ctrl-R
  restart. NTSC and PAL pass (103 and 100 snapshots).
