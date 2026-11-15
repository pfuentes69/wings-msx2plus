# Altitude and distant-view correction

The earlier prototype capped height at 255, so the distant aircraft only rose
32 screen pixels. It also used `plne`, a static map marker with a two-row shape,
rather than the original player-aircraft pose set. The distant sea rectangle
was missing, leaving cyan between the reduced hull/shore and dashboard.

The original player renderer uses a distant baseline of 1208 and a three-bit
projection shift (`wings` file 0x2a0 and 0x524). This gives a 151-pixel distant
baseline in its 162-line view. The MSX view retains its 161-pixel baseline and
now supports a 0–1200 height range, letting the aircraft reach the top portion
of the distant view. The 1200 ceiling is the prototype's chosen bound for this
projection span; original flight dynamics and their exact ceiling are not
claimed to be ported. Starting height remains 92. World Y is now unsigned
32-bit Q8 for this mission configuration, avoiding the former 16-bit limit.
Other prototypes retain their earlier vertical representation and bounds.

The source distant renderer fills a solid color-10 sea rectangle from row 151
to the bottom (file 0x3ea2). The MSX conversion fills rows 161–171 using the
corresponding mission ocean blue, preserving the original sand pixels at row
161. The carrier hull now meets the water surface.
This distant fill is deliberately flat; the close view keeps animated waves.

All 27 original `lpn…` records are retained with their own drawing origins and
heights. Original transparent pixels remain transparent, rather than becoming
green padding. The source reduced-pose table begins at file 0x13ed4; pitch and
bank selection code is at 0x490–0x516. The current normal-pose indices select
matching reduced pitch/bank art through an explicit adapter. This preserves
visible attitude changes while retaining the prototype's existing controls
and turn timing. It does not reproduce original flight dynamics.

The reduced frames are packed into three verified 48×24 atlas rectangles.
The manifest records every source hash, origin, atlas placement and normal-to-
reduced pose mapping. The emulator checks all 27 cached frames and captures
climbing plus three distant bank poses, alongside the full-height and reset
bounds. Host tests cover the expanded Q8 limits and NTSC/PAL simulation parity.

The workload currently needs eight VBlanks per presentation: 7.5 fps NTSC /
6.25 fps PAL, with 20/24 simulation steps maintaining nominal 150 Hz updates.
The former six-VBlank cadence missed an NTSC deadline at a shoreline crossing.
At PAL's 24 steps per presentation, the 12-step wave clock samples six of the
twelve phases; all twelve original frames remain loaded. View changes still
rebuild hidden pages and pause simulation. Faster rendering remains planned
work; the close-view pan is described below.

![Distant sea and carrier](mission/scenery-distant.png)

![Actual reduced pitch and bank captures, enlarged](mission/distant-aircraft-poses.png)

![Aircraft at the upper height bound](mission/altitude-top.png)

## Distant sand strip correction

The sea fill had overwritten the one-pixel sand strip already reconstructed
from the original reduced terrain. It now preserves source palette index 17
(MSX index 14) at viewport row 161; rows 162–171 remain ocean blue. The original
`8thscale.shp` beach records, `bchl` and `bchr`, supply the shoreline silhouettes.
Coarse ground outside their outer edges is removed so it cannot leave detached
sand fragments. The close-view artwork is unchanged.

The generated terrain uses 493 shared tiles. The release excludes the unused
legacy fixed-pose aircraft entry point to fit the resident ROM, now 32,728 of
32,768 bytes; debug profiles retain that entry point.

Validation: 117 host tests pass. Release gameplay checks pass 78 snapshots on
each NTSC and PAL profile. Renderer checks pass 59 NTSC and 65 PAL snapshots,
including full-VRAM comparison over the distant island. Results include ROM
hashes: [release NTSC](sand/release-ntsc.json), [release PAL](sand/release-pal.json),
[renderer NTSC](sand/renderer-ntsc.json), [renderer PAL](sand/renderer-pal.json).
The image below is a VRAM reconstruction, not a raster or hardware capture.

![Continuous sand beneath distant palms](sand/distant-island-vram.png)

## Close-view pan

The original's render loop (CODE 0x26e) places the close view's baseline
at 151 + max(0, altitude − 131). Above altitude 131 the whole scene moves
down with the plane, which stays at its pinned row. The distant view takes
over above altitude 186 (0xc966 sets the view to 1 above 0xba). Between the
two, the ground slides out of the bottom of the view and back as the plane
climbs and descends. The port used to pin the plane without moving the
scene, so in that band the plane seemed not to descend and bombs appeared
above it.

The port now pans by p = altitude − 131 (0..55) in two parts.

- **Whole tile rows, in software (`g_PanRows`, a multiple of 8).** The
  tile cache keeps map rows, independent of the pan, and terrain columns
  are drawn `g_PanRows` lower. The run loop (`Column_Runs`) still caches
  rows pushed below row 172 but draws nothing for them. The other layers
  add `g_PanRows` to their rows: the ship, signalmen, elevator and well
  edge (clipped at 172), bombs and smoke. Waves are skipped once the strip
  (rows 161..171) is a tile row or more below the view.
- **A pan step** (the tile rows change by up to 3) moves the page instead of
  rebuilding it (`PanStep`); a rebuild took 250–300 ms. A VDP block move
  (YMMM) shifts the rows below the scenery's top, which comes from
  `g_TerrainBlockTop`: the converter's first scenery row per 256 px. It is
  40 at the carrier's tower, 120–160 over the islands, and none over open
  sea. Then:
  - **Step down:** the rows uncovered above are filled with sky.
  - **Step up:** the rows uncovered at the bottom are painted from the cache
    (`Terrain_RepaintBand`). That needs no map decode: solid runs merge,
    and a row of one tile is painted once and doubled.
  - **Order:** all this happens after the restores and before the
    scrolled-in columns are drawn, so the cache matches VRAM when they are
    compared.
- **The fine part, in hardware (`s_RenderFine`, −1..7 px).** R23 already
  scrolls the scene by the carrier's heave. Wrapped top rows would show the
  cached wave frames in VRAM rows 243..253. So the top lines keep the
  heave-only offset (they show sky), and a line interrupt at line s = heave
  + fine (R19 = fine) switches to the full offset (`pan_split$`). The tile
  rows change only when the fine part leaves −1..7. A plane holding height
  on a row boundary therefore doesn't step every frame. At −1 the last
  play line shows terrain row 171.

**The top split, made timing-proof (2026-11-15).** The top lines show VRAM
rows −heave .. fine − 1 of the page. While smoke and the plane could be drawn
there, they appeared in the top band, displaced up by `fine`. A late split
interrupt did the same for the rows just below. Measured over the P0 run,
the split ISR runs 0–2 lines late on most fields, and rarely 3–4. Players saw
it as fragments of smoke or of the plane at the top while descending through
the pan band. Now:
- **No overlays above `g_TopClip`.** The plane, its wheels and gun flash, the
  weapons and smoke stay at VRAM rows from `g_TopClip` (`fine` in the pan,
  else 0). In the tallest dive and climb poses (dy −2), at fine 6–7, that
  costs the top 1–2 rows of the plane.
- **The split is requested `min(fine, 2)` lines early.** Under the play
  scroll those lines show VRAM rows 254..255, which hold no data (the wave
  cache keeps them empty). A split up to 2 lines late shows rows
  fine − 2 .. fine − 1 instead, which are sky. Either way nothing changes
  on screen. A split 3–4 lines late can still show a 1–2-line sliver.
- **Checked every frame.** The P0 run checks, on every published frame,
  that the rows the top band can show are plain sky. The pixel oracle
  clips overlays the same way and models the earlier split line.

The bottom split must not depend on the line interrupt's exact timing.
Interrupts can arrive a line or more late (other interrupt work, short
sections with interrupts off), and two earlier attempts showed it:
- **A +2 scroll onto the dashboard's top rows:** a late second interrupt left
  the dashboard shifted, with hidden VRAM below it.
- **A switch exactly in the horizontal retrace:** a late first interrupt
  switched on the wrong line, so the dashboard flickered and jumped a pixel.

Now the split is requested at line 170, and the scroll returns straight to
the dashboard's 0. A dark guard line is drawn at VRAM 170 − scroll .. 171,
and the dashboard's top rows 172..175 are solid colour 1. Lines 170..175
therefore read dark pixels under either scroll, and the switch may land
anywhere in them. When the scroll shrinks, `RepairGuard` repaints the rows
the guard leaves, from the tile cache. With no tile-row pan, waves are drawn,
and most of those rows are handled every frame anyway: rows 166..171 are
redrawn opaque and 161..162 are restored from the wave backup. So only rows
163..165 need repainting, and only where the island's beach is in view.

**Timing.** Steps over open sea and the islands fit the 8-VBlank frame. Over
the carrier the block move spans the tower, about 130 rows. There a step can
run 1–3 VBlanks long: up to about 185 ms against the 133 ms NTSC frame, about
10 frames on a descent through the band. Those frames are counted in
`g_PanOverruns`, apart from missed frames, as view changes are. The emulator
run reports them and allows at most 16 (8 NTSC, 4 PAL now).

Verification: `tools/p0_smoke.tcl` climbs into the distant view after the
island run. It comes down through the band over the carrier with a bomb
falling, and captures `pan_high` (pan 45..55) and `pan_mid` (17..29). The
cannon tests also fly in the band. Each snapshot dumps the published fine
scroll (`g_DisplayFine`). `verify_world_flight.pan_of` and `vram_row` model
the pan and the two scroll regions in the oracle, which expects the guard line on screen rows 170..171. `tests/test_column_runs_z80.py` covers the run loop with
pans of 0..6 rows.
