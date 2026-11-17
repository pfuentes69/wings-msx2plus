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

Not yet:
- only map 0 is decoded, so every mission flies mission A's island again;
- no victory ceremony screen;
- the briefing doesn't name the mission. The campaign (rank names, mission
  texts, the other maps) is P6.

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
