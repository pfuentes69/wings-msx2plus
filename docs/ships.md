# Enemy ships

The ships work in steps (from [research/amiga-ships.md](research/amiga-ships.md)):

| Step | Contents | State |
| --- | --- | --- |
| 1 | Hulls drawn into the scenery, close and distant views | Done |
| 2 | Rockets; a rocket destroys a gun ([rockets.md](rockets.md)) | Done |
| 3 | Gun barrels, fire at the plane, shell splashes, the "under fire" sound | Done |
| 4 | The torpedo: fall, run, wake, hull hits, destroyed by shell splashes ([torpedo.md](torpedo.md)) | Done |
| 5 | Sinking, the bonus and "sunk" message, ships in mission complete ([ship-sinking.md](ship-sinking.md)) | Done |
| 6 | Scripted verification on map j: the P4 gate ([below](#verification-step-6)) | Done |

Map j has a destroyer at its left end (x 8..655) and a battleship at its
right end (x 7160..7935); `WINGS_MAP=j ./launch.sh` runs it. The ship
tables (hull range, deck, hits, bonus, gun x) come from the converter,
`src/generated/map_<x>/mission_ships.h`.

## The guns (step 3)

`Ships_Guns` (`src/core/ships.c`, segment 28) runs each original tick next
to the island's dugout guns, while the plane flies. For each live gun of a
ship afloat it follows 0x4c3e:

- **Shell splash** (0x4efc): if `rand & 511` exceeds the gun's distance
  from the plane and the plane is at altitude 200 or below, with chance
  6/16 a splash at the plane's x ± 32 (0x52b0): `spl6` down to `spl1`
  over 6 frames, or `ric0` for 4 on land. In the distant view only
  8thscale `spl1..spl3` exist. Each destroys a torpedo within 10 px
  ([torpedo.md](torpedo.md)).
- **Barrel**: close up, within 512 px, the island's barrel table (0x4db8,
  `src/core/barrel.h`) by altitude and dx / 40, with the muzzle flash
  (gnf) on half the updates. In the distant view every gun shows `expl`
  on half the updates, whatever its distance. Barrels stand at the deck
  (+e) + the gun's rise + 13; the hull is drawn without its bob, so the
  barrels are too.
- **Fire** (0x4f5c): the dugout guns' hit-scan, within 448 px: a hit
  sparks at the nose and damages the engine (oil, fuel).
- **Sound**: the nearest gun firing drives the gun channel (0x38ea), louder
  nearer, as the dugout guns do.

Destroyed guns stop and smoke (step 2). Drawing goes through the smoke
path (`src/msx/smoke_draw.c`): barrels before the puffs, splashes after.

Differences from the original: at most 4 shell splashes at once (the original
keeps 21), since the MSX cannot draw and erase more in a frame; the
render-loop rate is the open question of the research notes, so guns run
on the original tick, as the dugout guns do.

## Cost

Measured on map j (NTSC), a low pass over the destroyer's bow guns. Frame
deadlines missed in about 4 seconds:

| | Not firing | Firing rockets |
| --- | --- | --- |
| Step 3 as first built | 18 | 14 |
| After the performance pass | 7 | 8 |

The pass (2026-11-17):

- the guns run once a presented frame, as in the original's render loop
  (0x38d2), not on every original tick: 7.4 ms a frame, from about 19;
- muzzle flashes (gnf) and rockets drawn whole: they were split into up
  to 8 one-row atlas pieces (smoke-path pieces 167 -> 111; the tile cache
  gave up 4 of its 56 slots for the room);
- `Terrain_TileY`, the xorshift generators (`xorshift.h`) and the shapes'
  `Box` (`smoke_box.h`) in Z80, each tested against its C on an emulated
  Z80; the barrel frame by table; the gun loop, `Piece` and `RepaintTiles`
  on statics;
- off-screen barrels skipped before clipping; at most 4 splashes at once;
- with a ship's guns in view and 8+ smoke-path shapes, 2 more VBlanks a
  frame (an even 5 frames a second instead of late ones).

What a not-firing frame there still costs: erasing the shapes 27 ms
(terrain repaints under barrels and splashes), drawing them 20 ms, the wave
strip 11.5 ms, the guns 7.4 ms, tile strips loaded mid-frame about 5 ms
(4.5 ms a strip). Firing adds the rockets and their bursts. Next
candidates: the repaint loop in Z80, fewer strip uploads in heavy frames
(prefetch further ahead), cheaper bursts, the wave strip.

## Verification (step 6)

`tools/verify_ships.py` flies the P4 gate of
[PORT_ANALYSIS_AND_STRATEGY.md](PORT_ANALYSIS_AND_STRATEGY.md) on map j's
release ROM (build it first: `WINGS_MAP=j ./build.sh projname=mission-flight`)
with `tools/ships_smoke.tcl`, closed loop from the real flight state:

1. **Rockets.** Up to three dive passes from the left at the battleship's
   first live gun (guns 8..13, x 7203..7276): Down taps to pose 7, a
   one-second salvo from 350 px short of the gun, pull-up at altitude 130.
   Each pass moves its firing point by where the last salvo burst, and dives
   later if it reached the pull-up before the firing point. At least two
   guns must fall (4 on NTSC, 5 on PAL): +200 each. The ship stays afloat:
   a gun kill does not neutralise it (OBJ-02).
2. **Landing.** Straight in from the east (the landing direction), high,
   then down in steps, then the lib's final approach, flare, arrest and
   taxi onto the lift. A gun hit starts an oil leak, and the engine seizes
   below oil 96: the full circuit was too long. Down the lift, the service
   arms the torpedo (stock 1).
3. **The battleship.** Released at wave height (altitude 37..39) at x 6,420,
   more than 512 px from any live gun: the first hit, the ship still
   afloat. F1 (the refill cheat) gives another torpedo: the second hit, the
   sinking clock, the plane low over it in the close view, the bonus
   (+4,500) and the ticker ". . . Battleship sunk . . .". It goes under
   while the plane flies home.
4. **A second landing**: the service offers the torpedo again.
5. **A distant release.** Heading left at x 2,400, where its 199 moves end in
   open sea. The plane turns back over it (the wake in view); it runs out,
   with no hull hit.
6. **The destroyer.** F1 again: released at x 1,320, 700 px from its live stern
   guns, then a climb and a turn away from them. The hit, +2,500,
   ". . . Destroyer sunk . . .", gone: no ship left, the mission complete.
7. **A third landing** (east past the carrier first), down the lift to the
   next mission's briefing. Its sortie starts with both ships restored.

Each snapshot checks:
- the ships' state: guns, hits left, the sinking clock, ships left, gone;
- the score and bonuses;
- the ticker's pixels against the font;
- the dashboard's pixels;
- every tile-cache slot against the ROM.

All through the run, the visible page is never written while drawing, and
the overlay rows above the pan split stay clear. A VRAM preview of each
snapshot is saved (`*-vram.png`).

Missed frame deadlines are counted (`WINGS_ALLOW_MISSED`), not failed.
Frames over a ship with its gun smoke, barrels and splashes still run late
(render 100..185 ms over the battleship). On 2026-11-18 the run had 21
misses on NTSC and 9 on PAL; the limit of 50 catches a regression. Pan-step
overruns over the ships are reported only (54 NTSC, 22 PAL). The run takes
about 10 minutes headless:

```
.venv/bin/python tools/verify_ships.py --headless
.venv/bin/python tools/verify_ships.py --headless --machine C-BIOS_MSX2+_EU --output tools/.build/ships-pal
```

The harness is shared with the P0 smoke. `tools/smoke_lib.tcl` holds:
- the boot and the symbol lookup (`WINGS_ROM`);
- snapshot capture and the per-frame checks;
- the autopilot and the carrier circuit, relative to `::cx`, the carrier's x.
