# Frame budget

Measured 2026-11-14 on the release ROM with `tools/profile_p0.py`. That tool
samples the P0/P1 smoke run in openMSX: takeoff, flight, turns, cannon, bombs,
carrier, elevator, distant view. These figures are the baseline that enemy
work (P3–P5: infantry, guns, ships, aircraft) has to fit into.

## Budget per presented frame

Gameplay presents every 8 VBlanks: 133.3 ms on NTSC and 160 ms on PAL.
Simulation runs at 150 Hz, which is 20 steps per frame on NTSC and 24 on PAL.
Sound has a fixed 3,000 T-states per field ([sound-budget.md](sound-budget.md)),
included in all figures below.

| Per rendered gameplay frame | NTSC (FS-A1WX) | PAL (C-BIOS EU) |
| --- | --- | --- |
| Simulation, mean / max | 19.6 / 50 ms | 23.0 / 57 ms |
| Render, mean | 47.9 ms | 46.0 ms |
| Simulation + render, mean | 67.5 ms | 69.0 ms |
| Simulation + render, p99 | 119 ms | 110 ms |
| Worst gameplay frame | ~127 ms (31 + 96, low over the carrier, one dial redraw) | ~114 ms |
| **Spare time, worst frame** | **~6 ms** | **~46 ms** |
| Spare time, mean frame | ~66 ms | ~91 ms |

Updated 2026-11-14 for the P2 engine work. The P0 run now also takes off
twice more and flies low over the carrier: about 34 ms of simulation plus an
84 ms redraw before any dial redraw (118 ms). The first measurement (worst
~107 ms) did not sample those frames. A dial redraw costs about 5 ms per page
when a needle moves; at most one is drawn per page.

View rebuilds (altitude scale switch, full-page redraw, 300+ ms) and
restart/menu transition frames are excluded. They are exempt from the
deadline by design (`g_ViewChange`, phase not `GAME_PLAY`).

**NTSC worst case is the binding limit: only about 6 ms per frame is left
in the heaviest scene (low over the carrier) for enemy simulation and
drawing.** Recovering render time (candidates below) is a precondition for
enemies there. Before adding
entities, set per-entity budgets against this, and remeasure with the
profiler after each phase. The plan's rule applies: optimise transitions and
rendering before increasing active combat load, and never miss a deadline
silently. The verifiers fail on any missed frame.

## Flight speed and the carrier (2026-11-14)

The [rebuilt flight model](flight-model.md) flies at the original's speed:
10–14 px per tick, about 23 px per NTSC frame at full speed. The P1 tuning
model managed about 16. Each page now draws about six new terrain columns per
redraw instead of four, and a low pass over the carrier first measured
137–148 ms against the 133 ms deadline. A temporary 2-VBlank reservation for
those frames has since been removed by two changes:

- **Terrain columns in Z80.** `Column_Runs` (`src/msx/column_ops.c`) replaces
  SDCC's version of the per-run loop in `Terrain_DrawColumn` (about 900
  T-states per run before the VDP setup). `tests/test_column_runs_z80.py`
  checks every VDP command and the tile cache against a model of the C loop.
  Resident code also shrank by about 600 bytes.
- **Dial redraws wait out fast frames over the carrier.** Needles move one
  step per tick, so a short delay is not visible; the published gauge state
  still matches the page.

Result in the P0 run (NTSC):
- the worst frame over the carrier is 117 ms (33 ms simulation, 84 ms render),
  down from 127 ms at the old speed: 16 ms spare;
- all gameplay frames: p99 113 ms, render mean 43 ms.

The profiler now also breaks down renders over 85 ms on their own
(`render heavy`). The remaining heavy frames stream art from ROM (deck-turn
poses, crash art), not carrier passes.

Flight costs under the rebuilt model: the tick takes about 0.35 ms (12.5 Hz);
the Z80 step takes 0.21 ms (150 Hz), down from 0.475 ms.

## Where render time goes

Render is mostly CPU-bound: the VDP command engine is busy for only about 46%
of render time. About 21 VDP commands per frame. Mean per frame (NTSC):

| Item | ms/frame | Notes |
| --- | --- | --- |
| Waiting for the VDP before the next command | ~7 | Mostly the wave restore queued behind the aircraft/weapon background restores |
| Dashboard wave restore + draw | ~8 | Two 256-pixel strip copies plus LMMM bands; much of it is waiting |
| Terrain columns | ~4.5 | ~2.2 columns per frame at 2.2 ms each (was 4.5 ms before `column_ops`) |
| Ship, elevator and deck crew overlays | ~4.4 | Only while the carrier is visible |
| Overlay dirty marking | ~1.7 | 6 calls per frame near the carrier |

## Over the carrier (2026-11-14)

`tools/profile_p0.py` tags samples taken while the camera is over the ship.
Those frames average 57 ms of render (1,293 frames in the P0 run):

| Item | ms/frame |
| --- | --- |
| Waiting for the VDP before the next command (`VDP_CommandWait`) | 8.5 |
| Wave strip restore (`Dashboard_RestoreWaves`, mostly waiting) | 6.8 |
| Terrain columns (+ decode/compare helpers) | 6.3 (+1.7) |
| Wave bands (`Dashboard_Waves`) | 4.2 |
| Sound budget (line interrupt) | 3.0 |
| Command setup (`VDP_CommandSetupR32`) | 2.9 |
| Ship, crew, elevator overlays | 5.6 |
| Overlay dirty marking | 1.9 |
| Surface queries (`Mission_Query`) | 0.9 |

Done: `Dashboard_Status` skips the digit divisions when nothing changed, and
the crew re-marks overlay rows only when the camera moved or the page was
rebuilt (mean render 50.2 → 49.0 ms, worst frame 128 → 127 ms). Tried and
reverted: a binary-searched `Mission_Surface` and a one-entry query cache
(SDCC's search costs ~2,500 T-states and the alternating queries never hit),
and an early-out in dirty marking (no measurable gain).

The remaining time is structural: about 15 ms per frame is the CPU waiting on
the VDP, and the wave strip issues about 12 commands per frame (2-row backup
and restore, 96-pixel wave segments, transparent top rows via LMMM).

## NTSC heavy-scene allowance (2026-11-15)

Measured with `set cmdtiming broken` (VDP commands instant), the approach
over the carrier still takes ~95 ms of render CPU. The render is CPU-bound,
not VDP-bound. The simulation takes 55–65 ms more. Most render paths are
SDCC C at ~2,000–3,000 T-states per VDP command:

| Stage over the carrier, CPU | Time |
| --- | --- |
| Terrain columns (`Column_Runs`, asm) | ~2.8 ms per column, 4–6 a frame |
| Waves, after the open-sea fast path | ~8 ms (was 15.5) |
| Signalmen / elevator / ship | ~8 / 8 / 7 ms |
| Smoke, 5 puffs | ~8 ms |
| Aircraft and its backup | ~10 ms |

Until those paths are rewritten (planned as its own step before P4), NTSC
frames get 2 more VBlanks (10 instead of 8, on top of the weapons allowance)
in two cases:
- while the near view shows the carrier in normal play (not the lift);
- when the previous frame drew 4 or more smoke, gun or soldier shapes;
- when the previous frame came within one VBlank of the base deadline
  (`s_Tight`, added 2026-11-15). Shape counts miss scenes with a few large
  puffs: each costs several atlas pieces. Example: the plane's own engine
  smoke over the hut smoke near the right dugout took 42 ms of smoke
  restore and draw with only 3 shapes.

The simulation keeps its 150 Hz, so an extra VBlank adds ~10 ms of slack,
not 16.7. PAL is unchanged.

Found and fixed along the way: the wave strip moved to segment 21
(`src/msx/waves.c`; segment 3 had 25 bytes left). `RepairGuard` repaints
only the pixel rows the guard leaves. `Mission_Query` keeps its last run.
The island's per-update work is skipped when nothing is due.

## The render pass (2026-11-17)

Measured with `tools/profile_p0.py` (NTSC, the P0 run). The profiler now
charges time spent waiting for the VDP to the function that issued the
command. It also reports frames low over the carrier (y >= 1069, below the
pan), the ones the NTSC carrier allowance was for.

| Step | Render over the carrier, ms a frame |
| --- | --- |
| Before | 54.8 |
| Wave band loop in Z80 (`src/msx/wave_band.c`): 6.8 → 2.2 ms of CPU | 53.3 |
| `Vdp_RingCopy` (resident Z80) for the ship, signalmen, elevator, aircraft and background restore | 50.8 |
| `Terrain_DirtyOverlay` in Z80 (one call per overlay); smoke through `Vdp_RingCopy` | 47.6 |

The wave strip's copies are VDP-bound. Most of the CPU time saved there
turned into waiting for the VDP: 6.3 ms a frame over the carrier is spent
waiting inside the band loop itself.

Low over the carrier, sim + render now has a median of 68 ms, p90 96 and
p99 116, against 133 on NTSC. The only frames above 122 ms are the deck
transitions after the lift, which are exempt. **The NTSC carrier allowance
is removed.** The adaptive one stays: 4+ shapes on screen, or a frame within
a VBlank of the deadline. Both NTSC runs and the PAL run pass. The weapons
regression (`verify_world_flight --debug-profile --weapons`) still has its
known miss away from the carrier, now at world 1481.

Next candidates:
- `Ship_Draw` (1.8 ms) and the signalmen (1.4) in Z80;
- `DrawAircraft` (1.9);
- `Smoke_Draw` (1.8);
- the simulation: ~31 ms a frame over the carrier, `main`'s step loop
  ~6.8 ms of it.

## PAL heavy scenes (2026-11-16)

The PAL smoke run measured island frames with soldiers, 6 puffs and 10
shapes at 160.6–163 ms of work without MSX-MUSIC, against PAL's 160 ms.
They passed only when bombs in flight had already added 2 VBlanks. The FM
sound adds 0.4–1.6 ms to those frames, and the frame after `island_soldiers`
then missed (165 ms). PAL now also gets the 2 extra VBlanks with 4+ shapes
or after a tight frame. The carrier condition stays NTSC-only: PAL frames
there have room.

## Island cleared (2026-11-15)

The island-clear frames on NTSC were within a few ms of the deadline:
4 soldiers, the flag, hut smoke, and the score redraw for the bonus.

- **Score redraw.** It took ~21 ms on each page: digit extraction with u32
  arithmetic, SDCC multiplications for the glyph rows, then 147 table
  lookups. It now walks row pointers (no multiplications), and the second
  page reuses the first page's composed field. This applies to every kill
  and every bombed hut, not only the clear.
- **Message ticker.** Its first C version cost 10–24 ms a frame. The render
  now does only a VDP block move from the other page (~1 ms). The CPU writes
  the new text pixels in the time the frame loop would spend waiting for
  its VBlank, and only with a whole frame to spare. A page shows only the
  text it holds, so with no time to spare the ticker slows down instead
  of missing a frame. It starts two updates after the clear, after both
  pages have redrawn the score.

## Candidates, in order of expected value

1. **Schedule render work to overlap CPU with VDP** (the largest item over
   the carrier, ~15 ms per frame). Prepare terrain columns
   (decode and compare) while the background restores run, and emit their
   commands afterwards. VDP command order must stay as it is: the wave
   restore must precede the new columns.
2. **Wave strip.** Avoid the full 256-pixel backup and restore when nothing
   crossed the strip, and merge LMMM bands further.
3. **Carrier overlays.** Skip unchanged crew and elevator redraws, and mark
   overlay columns dirty once per column reuse instead of every frame.
4. ~~Hand-written Z80 for the remaining `Terrain_DrawColumn` C path~~:
   done (`Column_Runs`, 2026-11-14).
5. **Dial redraws.** The generic `VDP_WriteVRAM` costs about 5 ms per dial
   patch: 20 rows of 13–14 bytes, with an address set per row. Options:
   per-frame minimal rectangles, or a row blit tuned to V9938 timing.

## History

| Change | Effect |
| --- | --- |
| SDCC loop workaround in `Combat_Advance` ([sdcc-pitfalls.md](sdcc-pitfalls.md)) | firing simulation 51 → 41 ms per frame |
| Z80 flight step ([flight-step-z80.md](flight-step-z80.md)) | 1.16 → 0.475 ms per step, ~12 ms per NTSC frame |
| Gun reservation removed | firing at 8 VBlanks (7.5 fps NTSC) |
| `column_ops` decode/compare helpers | 4.5 → 2.2 ms per terrain column; worst weapons redraw 101–107 → ~81 ms |
| Flight model rebuilt from the original | step 0.475 → 0.21 ms; faster flight adds terrain columns; 2-VBlank reservation for fast carrier frames |
| `Column_Runs` in Z80; dial redraws held in fast carrier frames | worst carrier frame 148 → 117 ms at the original's speed; reservation removed |
| `Scenery_Read` copies with LDIR (was a C byte loop, ~80 T-states a byte) | a dial patch or streamed shape: ~8 ms → ~2 ms of ROM reads |
