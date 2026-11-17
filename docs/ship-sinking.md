# Ships sinking

Added 2026-11-17. Step 5 of the enemy ships ([ships.md](ships.md)), after
the Amiga sinking clock (0x1cae, 0x1cd8), the "sunk" message (0x5640) and
the mission check (0x5694), read by static disassembly
([research/amiga-ships.md](research/amiga-ships.md)).

## What the player sees

- The torpedo hit that takes a ship's last hit point (destroyer 1, cruiser 1,
  battleship 2, Japanese carrier 3) starts it sinking. Its guns stop firing
  and its destroyed guns stop smoking at once.
- It goes down 1 px a step: the first steps 20, 19, 18 ... ticks apart (the
  battleship's first comes a tick after the hit), then one a tick.
- At step 10, about 13 s after the hit, the bonus is scored (destroyer 2500,
  cruiser 1000, battleship 4500, carrier 6000) and the ticker says
  ". . . Destroyer sunk . . . BONUS 2500 points . . .". The last ship, with no
  island left, completes the mission: "Good work ! ..." (or the promotion)
  is appended, as for the last island, and the plane returns to the carrier.
- At step 120 (26 s) the sea takes the ship: its columns are open sea for
  bombs, rockets and torpedoes.
- An island cleared while ships remain no longer completes the mission.

## The original

| Part | Address | What it does |
| --- | --- | --- |
| Start | 0x49c2..0x49d8 | A running torpedo's hit: +c −1; at 0, +18 = 20. +16 is left as the level builder set it: 20, or 0 for the battleship (never set). |
| Clock | 0x1cae, 0x1cd8 | Every tick, each ship with +4 ≠ 0 and +c = 0: +16 −1; at 0 or below a step: +14 +1, +16 = +18, +18 −1 unless 0. Steps 20, 20, 19, ... 1 tick apart, then every tick (the battleship's first at once). |
| Bonus | 0x1d04..0x1d56 | Step 10: score += +12; 0x5640 writes ". . . %s sunk . . . BONUS %ld points . . ." (name from -$7456 by the bonus); ships to sink −1. None left and no island left: 0x5694 (mission complete). Else the text is queued (0x555a, only if none pending). |
| Gone | 0x1db8 | Step 120: ships afloat −1, +c = −1, every map word of its columns cleared. Its record stays: 0x4a4e still finds it (a rocket there can still "destroy" a gun). |
| Deck | 0x5714 | The deck's height less +14: bursts over a sinking deck come lower. |
| Guns | 0x4c3e | Only ships with +c > 0 fire, show barrels and smoke. |

The research note read 0x1cf6 as "step 1 of the US carrier": the `move.w`
after `cmpi` sets the flags again, so the branch at 0x1d00 tests the bonus
(0 for the US carrier), at any step. The US carrier's own sinking (4 hits
from the player's torpedoes, or enemy torpedo planes) is not modelled: its
hits are counted but its clock does not start.

## The port

**Clock and score** (`src/core/ships.c`, segment 28): `g_Ships.step`,
`wait`, `interval` are +14, +16, +18; `Ships_Tick` runs the clocks on the
original tick, whether or not the plane flies, and scores the bonus.
`g_Ships.left` is -$5c8d; `g_Island.sunk` tells the ticker to use the ship
text (`src/msx/message.c`, `Compose` with %s and %ld). The texts and names
come from the executable (`tools/convert_font.py`).

**The sea takes it**: `g_ShipsGone` (a bit per ship) is tested by the
generated `Mission_Surface` on the ship's deck runs (resident).

**Drawing.** The hulls are baked into the terrain tiles
([tile-cache.md](tile-cache.md)), so sinking is shown in 15 stages of 8
steps (8 px close up, 1 px in the distant view), stage 15 being the sea:

- **Close view**: no new tiles or map data. A hull column's tiles come down
  a tile row per stage as the column is decoded (`Sink` in
  `src/msx/mission_streamer.c`, from `g_SinkHull`); the rows pushed down pass
  under the wave strip, which covers rows 161..171. The converter checks
  every stage against the true render of the hull lowered 8 px a stage.
  `Terrain_DrawColumn` keeps per ring slot the rows a column was drawn with
  and redraws a hull column when they change. One stage behind, it moves
  the column down 8 px on the page instead (`Lower`: one VDP copy, bottom
  up, from the hull's top row, and a fill; `Column_Lower` in Z80 scans and
  shifts the tile cache): the page's overlays are already erased then, so
  the column holds exactly its cached tiles.
- **Distant view**: per ship and stage, the converter renders its hull
  columns 1 px lower each stage, clipped at the sea line, as columns that
  live only in ROM; `TERRAIN_SINK_TABLE` holds their offsets, and
  `Terrain_RemapEntry` points the column table at them (as the wrecked huts
  do). Map j: 141 more tiles (1013), 1.7 KB more map.
- A new mission brings the ships back (`Ships_Reset`).

## Cost

Measured on map j (FS-A1WX, NTSC), 10 s of the fast phase (steps 16..120):

| Flight | Missed frames | Frames |
| --- | --- | --- |
| No ship sinking (baseline) | 0 | mean 140 ms |
| Ship sinking, out of view | 0–2 | mean 147 ms |
| Low over the sinking destroyer | 13 | mean 160 ms, worst 234 |

Over the ship a stage costs each page about 24 hull columns × 2.4 ms
(`Lower`) on the frame it shows, so the frames that follow a stage change
are often late in the fast phase (a stage every 0.64 s). First tries: a
redraw of every visible column on both pages cost 15 misses even with the
ship out of view; redrawing the hull columns tile by tile, 4.2 ms each;
`Lower` in C, 6.7 ms each (two 19-row loops through SDCC's IX frame).
Candidates for the optimisation pass: one VDP copy for a run of hull
columns with the same top row, instead of one per column.

## Verification

- `tests/test_sinking.py`: the clock tick for tick against a model of
  0x1cd8 (bonus at 164 ticks, 145 for the battleship; gone at 329 / 310), the
  bonus and messages, a pending message kept, the mission completed by the
  last ship, the stages handed to the terrain (rows and the ROM entries) and
  restored, guns silent, deck lowered, the sea at step 120.
- `tests/test_column_ops_z80.py`: `Column_Lower` against its definition on
  an emulated Z80 (at most 3,656 T-states).
- `tools/convert_mission.py` checks every close-view stage against the
  render.
- In the emulator (map j release ROM): torpedo the destroyer, patrol over it
  low and high. Step 10 came 13.6 s after the hit with +2500 and the ticker
  ". . . Destroyer sunk . . . BONUS 2500 points . . ."; the hull went down a
  row at a time close up and a pixel at a time far off, leaving the mast
  last; at step 120 it was gone (`g_ShipsGone` = 1, one ship left).
- The P0 smoke (map a) passes on NTSC and PAL.
