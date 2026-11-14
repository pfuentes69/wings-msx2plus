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
4. Hand-written Z80 for the remaining `Terrain_DrawColumn` C path
   (mismatch runs and cache update).
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
