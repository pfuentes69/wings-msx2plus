# Island combat (P3)

The port's island targets follow the original executable, as recovered in
[research/amiga-island-combat.md](research/amiga-island-combat.md). This page
describes what the MSX does and how. P3 is being built in steps:

| Step | Contents | State |
| --- | --- | --- |
| 1 | Huts and dugouts: map data, wrecked huts, bomb hits, scoring, hut smoke | Done |
| 2 | The original's bomb physics (gravity, drag, detonation at altitude 12) | Done |
| 3 | Dugout guns: barrel art, hit-scan ground fire, engine damage | Done |
| 4 | Soldiers: release, walking, re-manning dugouts, deaths (+25) | Next |
| 5 | Island cleared: bonus, flag, message, mission complete | |
| later | Rockets, AA guns (rockets only) | |

## Map data

`tools/convert_mission.py` reads the island objects from the map's anchor
words (bit 15) and writes `src/generated/mission_island.h`. Each object
anchored at x A covers [A − 16, A + 16), as in the original's lists
(0x2de8/0x310c). Mission A has:

| Object | Anchors | Island |
| --- | --- | --- |
| Huts (id 4) | 2392, 2712 | 0 |
| Dugouts (id 3) | 1736 (leftmost), 3224 (rightmost) | 0 |
| Flag (id 275) | 2408 | 0 |
| Island span (bchl..bchr) | 32..3952, bonus 450 | |

The bonus table is the original's (`-$7b82`, 15 maps); map A is map 0.

## Wrecked huts

The original writes id 5 (hutb) into a bombed hut's four map columns
(0x46dc). The port's terrain is pre-rendered into 8-px tile columns, so the
converter renders the scene again for each hut with its anchor swapped to
hutb, in both the near and the distant view. It keeps only the columns that
change (5 near, 1 distant per hut in mission A) and appends them to the tile
image as variant columns, after the near and far maps. The tile dictionary
grows from 493 to 503 tiles; `hut-variants.indices` holds the variant pixels
for the tests.

At run time the map's column table (u16 offsets into the run data, in RAM)
is what changes. `Terrain_Remap` (`src/msx/terrain_patch.c`) points a hut's
columns at its variants' runs; restoring a column reads its offset back from
ROM. It also sets `g_TerrainDirty`. `Render` then calls `DrawView` for each
page once. `DrawView` visits the 33 visible columns, and the renderer's
per-slot offset check redraws only those whose runs changed.

To make room in the atlas, the hellcat frames hc40/hc41 (the original's
wheels-down side views) no longer get an atlas slot. The wheel overlays
replaced them, and nothing draws them. Their shape-table entries have no size
in both the C table and the ROM copy that the mission build loads from the
dashboard bank (`convert_dashboard.py`). `LoadShape` therefore skips them.

## Targets and scoring

`src/core/island.c` (banked, segment 23) keeps the original's hut and dugout
records (fields +8..+e) in `g_Island`:

- **A bomb that detonates on the ground** (a fresh `COMBAT_IMPACT` in a bomb
  slot; `Island_Impacts` runs after each weapon tick) inside a hut's 32 px
  wrecks it once: the terrain swap, +150, smoke, and the garrison comes out
  (0x4b40: waiting += 5, release timer 60). Cannon strikes do not damage
  buildings.
- **Inside a manned dugout's 32 px:** +200, reinforcement timer 200, and the
  garrison comes out. Dugouts are never destroyed. An emptied dugout scores
  nothing until soldiers re-man it (step 4).
- **Smoke** (0x4e18): a wrecked hut puts out up to 49 puffs at x + 16,
  altitude 17. The gap grows by one 12.5 Hz tick after each puff (1, 2, ...
  48 ticks), about 98 seconds in all. The puffs come from the engine smoke's
  8-puff pool through `Smoke_Emit` and are drawn the same way.
- Points go straight into `g_Game.progress.score`; the dashboard redraws it.
- Island soldiers are counted (5 per hut and per dugout, 20 on island A),
  ready for the island-clear check of step 5.

State resets at boot and on Ctrl-R (a new game), not when a plane is lost.
That matches the original, where island damage persists through the mission.

## Bomb physics

The original's bomb update (0x0b58), once per 12.5 Hz tick in 16.16 fixed
point:

- **Drag:** vx −= trunc(whole pixels of vx / 10). The quotient of the integer
  part by 10 is subtracted in whole pixels, so a bomb slows by 1 px a tick
  from 10 px a tick and by 2 from 20. Below 10 px a tick it keeps its speed.
- **Gravity:** vy grows by 0.375 px a tick (`-$5cae` = 0x6000), downward;
  y += vy.
- **Launch:** at the plane's velocity (vx negated facing left, 0x07f2).
- **Detonation** (0x0bf0): when the altitude reaches 12 over the sea or the
  island, or the height table + 11 over the carrier (surface class 1). There
  is no height test against objects. A bomb falls through huts, trees and
  dugouts and bursts 12 px above the sea. Only its x picks the target.

The port keeps its Q2 positions and its 25 Hz weapon tick (`Fall` in
`src/core/combat.c`). Its velocity unit, a quarter pixel per 25 Hz tick, is
half a pixel per original tick. Gravity is therefore 3/8 of a unit a tick,
added as 0/0/1/0/0/1/0/1 by age, and drag applies every second tick. Sampling
at 25 Hz trails the original's step (velocity first, then position) by 3/32 px
per original tick: about 2 px after a 100 px fall and 7 px after a fall from
the ceiling. Bursts happen at y 1188 (sea and island) or 1156 (deck: 33 + 11)
and are drawn on the surface, as before.

From 100 px up at full speed (14 px a tick) a bomb falls for about 1.7 s and
bursts some 190 px ahead of its release point. The earlier prototype's
gravity was about ten times the original's.

Combat (`combat.c`) moved into banked segment 23 with the island code, which
freed about 2.2 KB of resident space (3,044 bytes free).

## Dugout guns

A manned dugout aims at the plane and fires hit-scan rounds at it (0x3d78,
0x4d50, 0x4f5c). `Island_Guns` (`src/core/island.c`) runs once per original
tick, after `Island_Tick`. For each dugout:

- **Who fires:** only a manned dugout (garrison > 0) whose fire delay (+c,
  360 updates after re-manning, step 4) has run out, and only while the
  plane flies (the original's mode 0: not on deck, not crashing, not with a
  dead engine).
- **Barrel:** up to altitude 186 (the close view) and within |dx| ≤ 512, the
  shape is gun0 + the original's table (DATA `-$63e2`) at
  ((altitude >> 5) − 1) × 8 + dx / 40 + 3, dx = plane x − gun x, truncated
  toward 0. The index runs from −17 to 47 and reads the neighbouring
  constant bytes at both ends, so the port copies those 65 bytes as they
  are. On 6 updates in 16 the muzzle flash gnf0..gnf6 replaces the barrel.
- **The distant view:** above altitude 186 the original draws `8thscale`
  `expl` (shape 0x5a) on half the updates and fires only on those.
- **Hit:** none beyond |dx| > 448. With d = max(|dx|, altitude) +
  min(|dx|, altitude) / 4, a round hits when (rand & 511) ≥ d and
  (rand & 2047) ≤ 409: about 20% × (1 − d / 512) per gun and update. The
  original's `-$408c` check is a debug toggle (key handler 0xd184) and is
  left out.
- **Damage:** a hit puts out a spark at the nose (0x54e0 with effect type 6:
  `smk5`, the fiery frame, for 7 updates, then the smoke stages `smk4` down
  to `smk0`) and runs `Engine_Hit` (0x4f9e). The engine's hit counter (+$10)
  counts down; at 0 the engine loses 1 oil and 0..3 fuel and the counter
  restarts at 6 + rand(0..7). A new plane starts the counter at
  6 + rand(0..3) (0xb82c). Lost oil then leaks on and smokes as before.

The guns are drawn through the smoke path (`src/msx/smoke_draw.c`), behind
the puffs. The converter adds `smk5`, gun0..gun6, gnf0..gnf6 and the far
`expl` to the smoke frames (23 in all), cut into atlas pieces where they do
not fit whole; the aircraft data bank grew by 1.1 KB. The barrel's origin is
at the dugout's anchor x and altitude 20, placed with the same formula the
original's world-shape draw uses (0x5174): y = 11 − altitude + base, the
same as the puffs. Up to 3 guns and 8 puffs are drawn and published.

Two changes to the shared smoke drawing came with it:

- **Erasing a tile at a time.** A puff or barrel over terrain was erased by
  rerunning `Column_Runs` on each 8-px column it touched. Now
  `RepaintTiles` copies back only the 8×8 tiles under the shape, cut to its
  rows, from the page's tile cache: one HMMM (or HMMV for a solid tile)
  each. A barrel over the dugout costs a few commands instead of 3–4
  column redraws.
- **The top split.** In the close-view pan the top lines (above line
  heave + fine) show VRAM rows −heave .. fine − 1 at the heave-only scroll.
  A puff that rose into those rows showed in the wrong place there. Shapes
  are now clipped at VRAM row fine, and the pixel oracle does the same.
  Damage from the island run left the engine smoking for the rest of the
  run, which exposed this.
- **Smoke over the carrier.** The signalmen and the elevator mark their
  columns for repaint in the tile cache. The eraser skipped such columns
  completely, so a puff passing over them left 8-px blocks of smoke in the
  sky. It now repaints every tile the cache knows and takes the overlay rows
  from the map (`Terrain_DecodeColumn`). The P0 run checks it: on the deck it
  puts 8 puffs over those columns, and the `deck_smoke_live` and
  `deck_smoke_cleared` snapshots must match the pixel oracle. The old build
  fails the first one.

There are no dugout-gun sounds yet (P5 audio).

**Frame budget.** The first build missed NTSC deadlines: over the right
dugout (render 60 → 90 ms) and, later, over the carrier, where a few ms of
extra simulation tipped a frame that was already at the limit. Profiling
the island stretch (with `tools/profile_p0.py` now naming the static
functions of banked modules; it used to credit them to the global before
them) showed three costs:

- **Erasing shapes by column.** `RepaintTiles` (above) replaced it.
- **`Shape` through struct pointers.** It now works out the box in statics.
- **`Smoke_Tick` with a full pool.** Once ground fire has damaged the
  engine, it keeps about 8 puffs alive. SDCC's loop cost ~1,200 T-states a
  puff, about 5 ms a frame at 2 ticks a frame. The advance is now Z80
  (`Smoke_Advance`, at most 3,521 T-states for 8 puffs), checked against
  the C reference in `tests/test_smoke_z80.py`.

`Island_Guns` itself works in statics, with no division (dx / 40 by
subtraction).

After these changes the run's heaviest island frame (NTSC, three shapes
over the right dugout) takes 41 ms of simulation and 84 ms of render: 125 of
133 ms. That is still about 20 ms more render than without the guns. Frames
over the carrier are back at the baseline.

## Verification

- `tests/test_island.py` builds `island.c` with a stub `Terrain_Remap` and
  checks the layout, the 32-px hit boxes, single wrecking, the near/far
  column swaps and their restoration, dugout scoring, that only fresh bomb
  detonations count, and the 49-puff smoke cadence.
- `tests/test_island.py` also checks the barrel table against the plane's
  position, the 6/16 flash rate, the quiet cases (out of range, not flying,
  emptied dugout), the re-manned fire delay, the distant view's 50% flash,
  the hit rate against 20% × (1 − d / 512) at three distances, none beyond
  448, and that hits spark at the nose and wear oil and fuel at the
  counter's rate.
- `tests/test_mission.py` round-trips the variant columns through the tile
  map.
- `tests/test_combat.py` follows released bombs against a 16.16 model of
  the original update and checks the burst heights over sea, island and deck.
- The emulator scenario (`tools/p0_smoke.tcl`, `island_run`) flies to island A
  after the cannon tests and coasts to speed 1000 at y 1100. It aims one bomb
  at the hut at 2392, predicting the burst point with a copy of `Fall`, then
  turns back over the hut. The plane's x moves a frame's worth at a time
  (28 px on PAL at full speed), and carpet bombing at 14 px a tick spaces the
  bursts 44 px apart, wider than a hut, so the run coasts and aims instead. The `island_bombed` snapshot checks the whole screen against
  `verify_world_flight.island_background`, which pastes the variant columns
  over the scene for wrecked huts. It also checks the score (150 per wrecked
  hut, 200 per emptied dugout) and at least one smoke puff on screen. This
  runs on NTSC and PAL with no missed frame deadline. On its way in, the
  run passes the right dugout at altitude 100. The snapshot also requires
  at least one ground-fire hit (`g_Island.hits`), and the pixel checks
  cover the drawn barrels, flashes and sparks (95 snapshots NTSC, 92 PAL).
