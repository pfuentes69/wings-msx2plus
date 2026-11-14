# Island combat (P3)

The port's island targets follow the original executable, as recovered in
[research/amiga-island-combat.md](research/amiga-island-combat.md). This page
describes what the MSX does and how. P3 is being built in steps:

| Step | Contents | State |
| --- | --- | --- |
| 1 | Huts and dugouts: map data, wrecked huts, bomb hits, scoring, hut smoke | Done |
| 2 | The original's bomb physics (gravity, drag, detonation at altitude 12) | Next |
| 3 | Dugout guns: barrel art, hit-scan ground fire, engine damage | |
| 4 | Soldiers: release, walking, re-manning dugouts, deaths (+25) | |
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

## Verification

- `tests/test_island.py` builds `island.c` with a stub `Terrain_Remap` and
  checks the layout, the 32-px hit boxes, single wrecking, the near/far
  column swaps and their restoration, dugout scoring, that only fresh bomb
  detonations count, and the 49-puff smoke cadence.
- `tests/test_mission.py` round-trips the variant columns through the tile
  map.
- The emulator scenario (`tools/p0_smoke.tcl`, `island_run`) flies to island A
  after the cannon tests and carpet-bombs it from y 1100 until the hut at 2392
  is wrecked. The `island_bombed` snapshot checks the whole screen against
  `verify_world_flight.island_background`, which pastes the variant columns
  over the scene for wrecked huts. It also checks the score (150 per wrecked
  hut, 200 per emptied dugout) and at least one smoke puff on screen. This
  runs on NTSC and PAL with no missed frame deadline.
