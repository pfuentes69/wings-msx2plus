# Enemy ships

The ships work in steps (from [research/amiga-ships.md](research/amiga-ships.md)):

| Step | Contents | State |
| --- | --- | --- |
| 1 | Hulls drawn into the scenery, close and distant views | Done |
| 2 | Rockets; a rocket destroys a gun ([rockets.md](rockets.md)) | Done |
| 3 | Gun barrels, fire at the plane, shell splashes, the "under fire" sound | Done |
| 4 | The torpedo | |
| 5 | Hull hits, sinking, the bonus and "sunk" message, ships in mission complete | |
| 6 | Scripted verification on map j | |

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
  8thscale `spl1..spl3` exist. Splashes only threaten torpedoes (step 4).
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

Differences from the original: at most 4 splashes at once (the original
keeps 21), since the MSX cannot draw and erase more in a frame; the
render-loop rate is the open question of the research notes, so guns run
on the original tick, as the dugout guns do.

## Cost

A low pass over the destroyer's bow guns (map j, NTSC), not firing:
`Ships_Guns` 7.8 ms an update (about 2.5 a frame), the smoke path 23 ms
drawing and 30 ms erasing (barrels over the hull and splashes over the
waves are repainted from terrain tiles). Such a pass misses about 14
frame deadlines in 4 seconds: the game slows while the guns are on screen.
Done so far:

- muzzle flashes (gnf) were split into up to 8 one-row atlas pieces; they
  now go in the late atlas pass (one or two pieces), and every rocket
  frame is one piece (111 smoke-path pieces, from 167);
- `Terrain_TileY` in Z80; the modules' xorshift in Z80 (`xorshift.h`, 145
  T-states, the C sequence: `tests/test_xorshift_z80.py`);
- off-screen barrels skipped before clipping; the gun loop on statics.

Next: the smoke path's draw and erase in Z80, and one repaint for shapes
that overlap.
