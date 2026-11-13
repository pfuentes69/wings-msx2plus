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
rebuild hidden pages and pause simulation. Continuous close-view vertical
scenery panning and faster rendering remain planned work.

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
