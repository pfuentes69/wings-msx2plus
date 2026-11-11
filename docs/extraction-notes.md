# Development log

## 2026-11-10 — Handoff and MSXgl layout

Read the handoff, port strategy, reference README, manifest and the three
original Python extraction scripts. The scripts remain exploratory and still
require the portable CLI and parser validation work described in the handoff.

Checked all 1,145 manifest entries: every file exists and matches its recorded
byte count and SHA-256. This verifies consistency with the supplied manifest,
not the correctness of the original extraction. The source ADF is absent, so
its recorded digest could not be independently checked.

The expanded `hellcat.shp.unpacked` starts with `PPkc` and a big-endian count
of 116. Representative raw record headers inspected:

| Record | Bytes | First 12 bytes (hex) |
| --- | ---: | --- |
| `040_hc01.bin` | 890 | `00 06 00 1d 00 19 00 10 00 40 00 8b` |
| `000_fa01.bin` | 80 | `00 02 00 06 ff f9 00 0a 00 60 00 91` |
| `020_fb01.bin` | 110 | `00 02 00 09 ff f9 00 0d 00 60 00 8e` |
| `096_wh01.bin` | 428 | `00 06 00 11 00 19 00 03 00 30 00 0d` |

These observations do not establish dimensions or pixel encoding. No new
aircraft PNGs have been generated. The next research increment remains the
portable extraction tools and three visually validated Hellcat frames.

Moved the strategy to `docs/PORT_ANALYSIS_AND_STRATEGY.md` to match the handoff.
Added the external MSXgl project layout with `src/main.c`, root build scripts
and configuration. The scaffold only switches to SCREEN 5 and waits.
The engine source and bundled binaries were left unchanged. MSXgl generates
its shared default configuration under `MSXgl/projects/` on first build.

Validation on macOS:

- `sh -n build.sh` and `node --check project_config.js` passed.
- `./build.sh` built `out/wings.rom` using native Node, SDCC and a native
  MSXhex compiled from the bundled source.
- `./build.sh clean` removed `out/`; invoking the absolute `build.sh` path
  from `/private/tmp` then built successfully.
- Checked ROM length (32,768 bytes), `AB` header and entry address in the ROM
  window, and confirmed `out/compile_commands.json` includes `src/main.c`.

The minimal configuration inherits library defaults and MSXgl prints warnings
for unspecified options. Builds succeed. Runtime behavior in openMSX and on
hardware, and the Windows/Linux launchers, have not been verified.

## 2026-11-10 — Hellcat decoding milestone

Recovered and visually inspected 52 aircraft frames, including at least three
clear, distinct pitched/level-flight views (`hc01`, `hc05`, `hc09`). Outputs:
`assets_src/hellcat/*.png`, `contact-sheet.png`, and `manifest.json`.
The manifest records source/record/palette hashes and exact decoder settings.
See `format-shp.md` for the established planar layout and provisional fields;
`research/hellcat-headers.csv` contains all 116 Hellcat archive headers.
`research/layout-comparison.png` preserves the rejected row-interleaving
hypothesis alongside successful plane-major images.

Established evidence:

- The 20-byte header/stride/height/nonzero-plane-count formula accounts for
  all 1,049 record lengths. Plane-major MSB-first decoding and plane color-bit
  maps render coherent aircraft, including records sharing color bitplanes.
- All 116 Hellcat archive records decode within bounds; the 52 `hc` records
  are exported as aircraft PNGs.
- `wingspalette` contains the blue/gray aircraft palette. Expanding its stored
  high-nibble RGB values to 8-bit values gives a close external screenshot
  match: `hc28` matches 291/306 nonzero pixels at native origin `(138,26)`.
  Fifteen pixels differ, so exact frame equivalence is not claimed.
- The current three example frames jointly need 11 opaque colors, leaving
  room in a 16-entry SCREEN 5 palette for transparent index 0.

Uncertain: origin/hotspot semantics, source-position fields, the meaning of
header bytes 12–13 outside Hellcat, exact animation groups, and whether index
0 alone is the game's complete transparency rule. No executable disassembly
was required to establish the pixel layout. No gameplay engine was added.

Refactored `unpack_shapes.py`, `extract_iff.py`, and `inspect_adf.py` into
portable CLIs; preserved byte-for-byte exploratory versions in `tools/legacy/`.
Parsers now validate bounds, declared lengths, malformed runs and path names,
and reject overwriting destination directories. Added `requirements.txt`.
The OFS extractor also checks block checksums, cycles and file sizes, but
only synthetic ADF fixtures were available to test it.

Two format quirks are reported explicitly rather than silently truncated:
`ff00` trailers in two Rpck archives, and one final zero byte inside the
`selectrank` ByteRun1 BODY after all declared image bytes have been produced.
IFF scanning now includes the Rpck-wrapped `palette` and `ocean.palette`
images (12 images total instead of the original 10). All ten supplied IFF
previews reproduce identically in RGB.

Commands run from the project root (outputs must be new directories):

```sh
python3 -m venv tools/.build/venv
tools/.build/venv/bin/python -m pip install --no-cache-dir Pillow
tools/.build/venv/bin/python tools/unpack_shapes.py \
  reference_assets/original_files/Wings_of_Fury/shapes tools/.build/reextracted
tools/.build/venv/bin/python tools/decode_shapes.py \
  reference_assets/original_files/Wings_of_Fury/shapes/hellcat.shp \
  assets_src/hellcat \
  --palette reference_assets/original_files/Wings_of_Fury/shapes/wingspalette
tools/.build/venv/bin/python tools/extract_iff.py \
  reference_assets/original_files/Wings_of_Fury/shapes tools/.build/iff-redecoded
tools/.build/venv/bin/python -m unittest discover -s tests -v
```

Result: 18 tests passed. These cover malformed Rpck/PPkc/ByteRun1/IFF records,
bit order and combined plane maps, synthetic OFS extraction/checksums/bounds,
all 1,145 manifest hashes, archive/record byte reproduction, all 116 Hellcat
records, and the ten existing PNGs. A separate byte comparison found all
1,061 regenerated archive blobs and records identical to the preserved copies.

No blocker remains for exporting the first aircraft frames. Next: convert
three to SCREEN 5 bitmap/palette data and display them in openMSX, measuring
and validating actual VRAM rendering before choosing a flight/scrolling design.

## 2026-11-10 — Three-frame MSX graphics prototype

Converted `hc01`, `hc05`, `hc09` to shared-palette SCREEN 5 data and committed
reproducible generated C arrays under `src/generated/`. The game source now
shows the three views, selected by keys 1/2/3, over a sky background. Hidden
page redraws are published during VBlank. All work remains under `src/` for
game code; the copied MSXgl engine is unchanged.

Added `tools/convert_hellcat.py`, `tools/verify_screen5.py` and its openMSX Tcl
script. Source transparency is flattened to sky; origins/hotspots remain
unapplied. See `screen5-prototype.md` for captures, provenance, exact commands,
VRAM layout, measured limits and remaining platform-validation gaps.

Validation: native ROM build succeeded; generated-asset check and all 23 tests
passed. Both NTSC and PAL openMSX checks passed five snapshots each, including
keyboard input, held-key behavior, palette/VRAM comparisons, stale-pixel checks
and VBlank publication. Interactive redraws measured 10.55 ms; observed input
latencies were 21.42–22.19 ms NTSC and 27.93–30.35 ms PAL. The ROM occupies
4,496 bytes before padding to 32 KiB, with 48 bytes static RAM plus stack and
BIOS state, and reserves two 32 KiB VRAM pages. No flight engine was added.

## 2026-11-10 — Reference emulator configuration

The user identified `Panasonic_FS-A1WX-512K` as their usual reference machine.
Made it the default in the emulator checker and manual launch commands.
The check isolates generated writes while retaining read access to the user's
machine definitions/firmware; no personal machine files were copied here.

Ran `python tools/verify_screen5.py --output tools/.build/screen5-panasonic`
with the project's Python environment. All five snapshots, VRAM/palette
checks, keyboard/held-key behavior and VBlank publications passed. Interactive
redraws measured 11.07 ms and observed selection latency was 23.55–24.32 ms.
The ROM binary is unchanged. Captured the verification report and level-flight
screenshot under `docs/prototype/`. Physical hardware checks remain pending.

## 2026-11-10 — Audio extraction assessment before flight work

Inspected all eight raw effects, `wofsongs`, `songplay` and limited relevant
sound setup/interrupt logic in the original executable. The source ADF is
absent, but these files are already recovered from it and remain unchanged.

Added a bounded HUNK/8SVX extractor and an optional libuade WAV front end.
Exports in `assets_src/audio/`: eight byte-preserving raw-effect WAV previews,
six exact embedded 8SVX instruments and six instrument WAVs, the unmodified
music/player pair, four ten-second music WAVs and hash/provenance manifests.
The music is the supported Kris Hatlelid two-file format. UADE independently
reports five subsongs; the recovered symbol/pointer table identifies four
unique definitions, with slots 1 and 3 shared.

Effect audition rates remain assumed (8,363 Hz); actual gameplay uses varying
Paula periods and dynamic engine pitch. Instrument rate/loop metadata is
recovered from VHDR. Music WAVs are bounded, not asserted complete or
listening-validated against a game recording. Event transcription and MSX
arrangement remain separate future work. No game code or ROM was changed.

UADE 3.05, libzakalwe and bencodetools were built under ignored tools/.build
with source hashes verified; no system-wide packages were installed. Capstone
was installed only in the ignored project environment for limited analysis.
All 29 tests passed, including new audio container, signed PCM round-trip,
exact instrument, song-table and rendered-preview checks. See
`docs/audio-extraction.md` for commands, primary references and limitations.

## 2026-11-10 — Controllable movement over static sky

Completed the first motion increment: portable fixed-point C core under
`src/core/`, cursor-key/port-1 joystick input, acceleration/coasting, screen
bounds and Space/fire reset. The three poses follow vertical velocity;
horizontal facing uses generated reflected artwork. This is an arcade
movement baseline, not established Amiga flight physics. No audio integration
or scrolling was added.

The renderer now clears each hidden page's previous aircraft rectangle with
HMMV, redraws at the new position and publishes at VBlank. A dedicated MSXgl
IM2 VBlank clock drives 30 Hz NTSC / 25 Hz PAL presentation, with equivalent
150 Hz simulation tick grouping. Globals start at C1C4 after the SDK's ISR
reservation. The initial BIOS-clock experiment showed an isolated long
publication interval; the dedicated clock passes the cadence checks on both
configurations. See `docs/flight-prototype.md` for implementation details,
controls, exact commands and known limits.

Validation: native ROM build and generated-asset check succeeded; all 36
tests pass. Panasonic flight verification passes ten snapshots and 406
publication intervals, with maximum redraw 13.68 ms and zero missed deadlines.
PAL passes ten snapshots and 340 intervals, maximum redraw 13.18 ms, zero
missed deadlines. Full displayed-page comparisons show no trails; reset,
coasting, facing, all four bounds, palettes and VBlank publication pass.
The retained manual-pose regression passes five snapshots. Selected captures
and hash-linked reports are under `docs/flight/`.

ROM occupancy is 7,942 bytes before padding to 32 KiB. Static globals use
89 bytes plus a 452-byte IM2 reservation, stack and BIOS workspace. VRAM
reservation remains two 32 KiB pages. Physical Panasonic/joystick checks and
Windows/Linux execution remain pending. Next: authentic orientation-frame
mapping and stable pivots before scrolling work.

## 2026-11-10 — Source-backed orientation and turn playback

Recovered executable frame-name tables at 15d00, 15d68 and 15dd0, and established
that header offsets 4/6 are signed drawing origins subtracted from object
coordinates. Twenty stored fa/fb pairs validate the horizontal reflection and
origin transform. Added `tools/map_aircraft.py` with bounded table checks and
instruction-evidence guards. Data facts and source hashes are retained in the
converted asset manifest; no original executable code was ported.

The ROM now uses 49 cropped shapes (40 original, nine reflected pitch views),
ten pitch choices per facing, original drawing origins and two MSX-authored
22-step banked transitions. Reversal requests finish the current turn before
servicing a queued direction. T requests a stationary review turn; held T does
not repeat. Timing is authored (110 core ticks), not claimed original-game
behavior. Safe viewport clipping preserves source offsets even at screen edges.
Movement physics and audio integration remain unchanged.

Validation: native ROM build and generated-asset check pass; all 45 tests pass.
Panasonic movement verification passes 11 snapshots and 430 intervals at the
30 fps target, maximum redraw 13.77 ms, zero missed deadlines. PAL passes 11
snapshots and 360 intervals at 25 fps, maximum redraw 13.35 ms, zero missed
deadlines. Stationary turns validate 31 distinct original shapes on Panasonic
and 28 on PAL, including full-page pixels and a fixed logical pivot. Idle
1/2/3 regression passes five snapshots. Reports/captures are under
`docs/orientation/`; `docs/aircraft-orientation.md` documents reproduction,
source facts versus authored behavior, clipping limits and remaining work.

Occupied ROM size is 26,813 bytes before 32 KiB padding. Static globals use
101 bytes plus the existing 452-byte IM2 reservation and stack/BIOS workspace.
The next rendering increment should benchmark scenery restoration/scrolling
and consider mapper/storage capacity. Additional native corner-turn checks
pass 22 clipped-frame cases on Panasonic and 19 on PAL, including two/one
fully off-screen cases respectively, with no stale pixels.

## 2026-11-11 — Full-height V9958 ring streaming

Added an independent `hardware-scroll` MSXgl subproject, preserving the normal
aircraft prototype. It streams a synthetic 4,096-pixel landscape through pages
0/1 using R#25/26/27, with an eight-pixel left mask and 212-row incoming columns.
P pauses and R reverses; the camera and VRAM ring have separate coordinates.

Both standard-speed openMSX configurations pass full visible VRAM and completed
raster comparisons, all fine-scroll phases, page/ring/world seams, keyboard
pause/reversal, upper-VRAM preservation and VBlank cadence. All 575 streamed
columns per run are checked to be outside the currently displayed window.
Panasonic passes 36 snapshots and 1,656 publication intervals, maximum column
update 4.683 ms; PAL passes 33 snapshots and 1,386 intervals, maximum 4.378 ms.
Neither misses deadlines. All 46 host tests, the generated-aircraft check and
normal ROM build also pass. See `docs/hardware-scrolling.md` and hash-linked
reports under `docs/hardware-scrolling/`.

This establishes the standalone ring/column baseline, not combined gameplay
throughput. Next: aircraft restoration/composition across the ring seam and
world coordinates with a following camera, then measure terrain-cache and
mapper needs. Original maps and real-hardware verification remain separate.

## 2026-11-11 — World-space flight and following camera

Added `world-flight`, combining the aircraft atlas with bounded 4,096-pixel
world flight, a clamped following camera, seam-split transparent composition
and saved-footprint restoration. Two alternating 256-pixel scrolling pages
use the left mask for incoming columns and keep the upper 64 KiB aircraft
atlas. Terrain updates track cached heights and markers. Space/fire resets
altitude and motion while retaining horizontal world position.

Panasonic passes 64 pixel/raster snapshots and 2,496 publication intervals;
PAL passes 60 snapshots and 2,090 intervals. Maximum redraws are 20.538 and
22.152 ms with zero missed deadlines at 30/25 Hz. All 2,050/1,709 redraws leave
the visible bitmap unchanged, and every snapshot verifies all cached shapes.
The 49 host tests, generated-aircraft check, normal ROM build and NTSC flight
regression pass. The integrated ROM occupies 29,331 bytes. Run
`./launch.sh world-flight`; see `docs/world-flight.md` and its hash-linked
reports. Next: representative original terrain decoding, streamed storage
format and mapper/capacity measurements; real hardware remains unverified.

## 2026-11-11 — Original-art terrain tiles and ASCII8 storage

Decoded and inspected nine world-art records: two shorelines, three palms,
hut/ruin/dugout candidates and one wave candidate. All 140 world records satisfy
the bounded planar decoder. The base-14 shoreline pair reconstructs recognizable
coast pieces and is an exact pixel reflection; base OR and masking remain
provisional outside the aircraft evidence. Source files remain unchanged.

Composed a 4,096-pixel authored scene, retaining source hashes/origins and an
explicit reduced shared palette. Compared lossless 8×8 and 16×16 tilings:
8,640 versus 7,168 bytes including map IDs. The 16×16 form has 44 cached tiles,
four changing vertical rows and eight-pixel half-column streaming. A separate
`tile-flight` 64 KiB ASCII8 project loads terrain from segment 4 at startup,
restores all resident banks, and runs without mapper switches during flight.
Resident content is 29,847 bytes, terrain bundle 7,168 bytes, static RAM 1,912
bytes plus IM2/stack/BIOS. Run `./launch.sh tile-flight`.

Pitch selection is deferred to the last simulation tick of each displayed
frame, preserving every bank-animation tick and tested published state. All
56 host tests pass, as do original-aircraft and procedural-world NTSC emulator
regressions. The tile prototype passes 78/71 complete pixel/raster snapshots,
2,811/2,353 publication intervals and 2,081/1,734 immutable-visible-page redraw
checks on Panasonic/PAL. Maximum redraws are 21.819/24.341 ms with no missed
30/25 Hz deadlines. Every snapshot also verifies all aircraft/tile caches and
actual restored ROM banks. See `docs/tile-terrain.md` and retained reports.
Original mission maps and collision remain next; physical hardware is untested.

## 2026-11-11 — Source-backed a.map strip and carrier

The user reports that tile-flight seems OK so far; record this as a preliminary
run report without assuming machine/input/timing coverage. Decoded all fifteen
original map files as bounded big-endian 16-bit strips following eight-byte
headers. Recovered executable-backed drawing flag, nine-bit shape ID, surface
class, three-bit depth offset and reset-X encoding; preserved every word.
The 184-entry name table at 0x13ed4 maps the first world's graphics IDs.

Reconstructed a.map's 7,608-pixel file-backed strip, reset X=7,032, island class
8–3,976 and carrier class 6,600–7,360. Seventy-five draw entries have available
normal-scale world shapes; 13 `bumb` entries and special marker 275 remain
explicitly unrendered. Original X/depth/origins place the hull sections, tower,
palms and huts; baseline translation and solid soil/ocean fills are authored.
Full game collision, dynamic carrier parts and mission rules remain unported.

Added mission-flight: a separate 64 KiB ASCII8 prototype with 434 8×8 tiles and
6,191-byte deduplicated/RLE column map. The 20,079-byte bundle occupies data
segments 4–6. Static RAM is 8,909 bytes plus IM2/stack/BIOS. Vertical atlas runs
and solid fills merge VDP commands; resident content occupies 31,093 bytes.
Two-/three-VBlank budgets overrun in carrier traversal; four VBlanks retain a
stable 15/12.5 fps presentation with nominal 150 Hz simulation.

All 63 host tests pass. Headless Panasonic/PAL checks pass 68/64 complete VRAM
snapshots, 2,232/1,868 publication intervals and 1,845/1,538 live-page immutability
checks with zero misses. Maximum redraws are 41.989/51.990 ms. Both caches,
source-map landmarks and actual restored cartridge banks are verified. Graphics
startup was unavailable, so these reports do not claim raster screenshots.
Existing tile-flight/world-flight NTSC headless regressions retain 30 fps.
See `docs/mission-map.md`, source exports and hash-linked reports. Next:
full-map streaming optimization, display validation and collision surfaces.

## 2026-11-11 — Mission raster verification completed

After the user granted permission, graphics-enabled mission-flight verification
passes on both configurations: 68 Panasonic and 64 PAL completed-raster/VRAM
snapshots with zero missed deadlines. Publication counts and maximum redraws
match the preceding headless runs. Both reports identify the same ROM SHA-256
and record `raster_checked: true`. The actual carrier screenshot and reports
replace the earlier pending-raster status in `docs/mission-map.md`; the prior
headless reports remain separately retained. Physical mission-flight testing
and collision/landing behavior are still pending.

## 2026-11-11 — Overlap CPU work with VDP commands

Mission rendering no longer waits immediately after every VDP command: the SDK
waits before submitting the next command, and the renderer waits once at the end
before publishing its hidden page. Cache bookkeeping and transfer preparation
now overlap VDP execution. The same full-map trajectory passes at three VBlanks:
20 fps NTSC / 16.7 fps PAL, retaining nominal 150 Hz simulation.

Graphics-enabled verification passes 80/71 raster and VRAM snapshots,
2,976/2,491 publication intervals and 2,460/2,049 hidden-page checks with zero
missed deadlines. Worst redraws fall to 33.454/33.998 ms. Both reports identify
ROM SHA-256 `7ec8e5035b2a0a42d07a0e18d9b39f01c1083f38b58e3cd7ed34fb11bac49ffe`.
The previous four-VBlank reports remain retained for comparison. All 63 host
tests pass; mission timing parity now exercises alternating seven/eight NTSC
steps and nine PAL steps. Static RAM and assets are unchanged.

## 2026-11-11 — Runtime original strip queries

Added executable byte guards for the bounded class/object query at file
0x50f0–0x5128 and its relocated jump-table entry at 0x130e6. The MSX
`Mission_Query` API preserves all eleven returned bits using 91 exclusive-end
runs (364 ROM bytes), including cells without drawing flags. Out-of-strip X
returns zero; navigation remains bounded to actual payload words.

All 64 host tests pass, including compiled lookup equality at every one of the
7,608 source pixel positions and signed coordinate extremes. Graphics-enabled
NTSC/PAL traversal passes 80/71 frame comparisons and verifies published class
and object queries against original strip words across all three classes.
20/16.7 fps timing remains stable with zero missed deadlines. Resident content
is 31,761 bytes; static RAM is 8,911 bytes plus IM2, stack and BIOS.

This supplies collision input without inventing collision heights from object
depth or artwork. Collision response and landing behavior remain pending.

## 2026-11-11 — Fixed original-art dashboard

Replaced the first authored SPD/ALT/AREA layout at the user's request with
`shapes/iff-dash`, preserving its equipment, OIL, central display, FUEL and
counter layout. Exported the original 640×37 ILBM and metadata for all 223
`dash.shp` records. The SCREEN 5 panel uses 248×36 nearest-neighbor pixels and
the shared mission palette, after a four-line separator and eight-pixel mask.
Gauge and inventory behavior remain unported; the current panel is static art.

Mission flight now occupies 172 lines, with the world translated up 40 pixels.
The line ISR resets horizontal offsets for the fixed panel; VBlank restores the
world offsets. Terrain and aircraft are clipped above the panel. The first
8,192 aircraft bitmap bytes move to previously unused ROM bank 7, with resident
banks restored before uploads. The cartridge remains 64 KiB. Resident content
is 26,973 bytes; static RAM is 9,041 bytes plus IM2, stack and BIOS workspace.

All 65 host tests pass. Graphics-enabled NTSC/PAL traversal verifies 79/71
completed frames, all aircraft/terrain cache bytes, source strip queries and
actual mapper restoration. No frame deadlines are missed at 20/16.7 fps.
Worst redraws are 32.403/34.328 ms. Full reports and screenshot are retained
under `docs/mission/`; original artwork and record hashes under
`assets_src/dashboard/`. See `docs/dashboard.md` for conversion and scope.

## 2026-11-11 — Live dashboard miniature

The user's original-game capture confirms the miniature scene and target
reticle in the central dashboard window. Added a 48×24 live local view of the
current mission reconstruction, at horizontal scale 1:8 with vertical fitting.
It follows world position, shows island/carrier details, and places the original
`dash.shp` `targ` sprite according to altitude. This is an MSX adaptation, not
a recovered port of the original miniature renderer or its dynamic entities.
The equipment counters and OIL/FUEL behavior remain unimplemented.

A six-chunk lower-band panorama cache and original reticle use unused VRAM below
the display, disjoint from aircraft footprint backups. Updates render only on
the hidden page; sky restoration touches only the old marker's footprint.
Camera projection and derived pitch are deferred to the final simulation tick,
while physics and persistent facing advance every tick. Host parity checks
include fractional boundary positions and reversals. The source strip query
overlaps the final reticle transfer.

All 67 host tests pass. Final graphics-enabled NTSC/PAL runs compare 79/71
complete raster and VRAM snapshots, including the miniature and reticle, with
zero missed deadlines at 20/16.7 fps. Resident content is 29,044 bytes and static
RAM 9,053 bytes, plus IM2, stack and BIOS workspace. Reports and carrier/island
screenshots are retained under `docs/mission/`.

## 2026-11-11 — Scenery fidelity before collision

At the user's request, prioritized scenery height, waves, the pilot-perspective
dashboard and altitude-dependent distance views. Corrected the MSX baseline
from 144 to 161 after viewport cropping, reducing the ground strip from 28 to
eleven lines. Aircraft now remove the logical-frame 25×16 offset before using
source drawing anchors. Source-color-17 island fill replaces the prior authored
color 14.

Added original `wava`–`wavl` animation, including beneath the carrier, with a
blue/foam palette adaptation. The central side overview was incorrect for this
role: it is replaced by source `3dl`/`3dc` perspective sprites, altitude profiles
and a fixed `targ` reticle. The original continuous pilot projection remains
unported. The recovered altitude test (>186) selects original `8thscale.shp`
scenery and reduced aircraft, returning at height 186 or below.

Close/far scenes share 516 tiles and a 6,485-byte compressed map; their bundle
is 22,997 bytes. The cartridge grows to 128 KiB; aircraft data use banks 8–10
and waves bank 11. Resident content is 20,714 bytes; static RAM is 9,352 bytes
plus IM2/stack/BIOS. The bounded bank reader restores resident mappings before
returning. Source-derived water intervals and class-only queries avoid full
object lookup work in the pilot renderer.

The complete fidelity workload needs five VBlanks: 12 fps NTSC / 10 fps PAL.
Scale changes rebuild both hidden pages, taking about 0.4 seconds per page;
these measured pauses are separate from regular deadline checks. Original
flight/collision/instrument rules and continuous vertical panning are still
pending. All 67 host tests pass; full raster reports and comparison captures
are retained under `docs/mission/`. The emulator harness now blocks live host
input, preventing physical Space/fire events from resetting scripted runs.
See `docs/scenery-fidelity.md` for source evidence, behavior and limitations.


### Verified shape-plane masks and final scenery measurements

Tracing the original blitter establishes header bytes 12/13 as clear/set
plane masks, with transparency derived from raw stored planes. The game
allocates a 1,040-byte transparency buffer; larger hulls fall back to opaque
rectangles. Applying this to mission art corrects distant foliage and hull
shades. Legacy prototype conversions remain unchanged.

The corrected close/far dictionary has 501 tiles (16,032 bytes), a 6,371-byte
map and a 22,403-byte bundle. Resident code/data use 20,624 bytes and static RAM
uses 9,238 bytes, excluding IM2/stack/BIOS. The final conservative cadence is
six VBlanks: 10 fps NTSC / 8.3 fps PAL, with nominal 150 Hz simulation between
view rebuilds. This supersedes the five-VBlank measurements above.

All 68 host tests pass. Final graphics checks cover 53 NTSC and 52 PAL snapshots,
with zero regular deadline misses and maximum regular redraws of 58.66/71.83 ms.
Page rebuilds take 419–435 ms each, two per view transition, and pause simulation.
Current reports and captures under `docs/mission/` use ROM hash
`6b33ab609915205989a9d872232c59b11adfa772beb3a389c068486fbe31adba`.


### Shoreline and wave backdrop correction

The wave adaptation now maps empty pixels and source sea color 19 to cyan,
matching the surrounding backdrop. Static ocean fill uses the same color.
The source beach silhouettes replace rectangular island endpoints, and sand
is composited after scenery so depth-offset palm roots are occluded. Wave
copy intervals come from the sand silhouette and round away from land to even
pixel pairs required by SCREEN 5 HMMM.

The scene now uses 478 tiles (15,296 bytes) and a 6,377-byte map, totaling
21,673 bytes. Added regression checks cover beach slopes, sand occlusion and
all twelve wave backgrounds; all 70 host tests pass.

Final verification: 53 NTSC raster/VRAM snapshots and 52 PAL VRAM snapshots,
zero regular deadline misses. Maximum regular redraws: 57.92 ms NTSC,
70.91 ms PAL. ROM SHA-256: `d5caba842d3080e0a6e1f1db497e7aab2bf71488b6a281172aaee01d8a379f86`.


### Original ocean palette and transparent carrier compositing

The user's original-game captures exposed the incorrect authored wave palette.
Re-extracted all twelve wave records with source plane masks and paired them
with the separate `ocean.palette` CMAP. Raw frame indices and palette bytes now
remain under `assets_src/dashboard/`, with source hashes and a display preview.
Original source 10 is blue, not white foam; source 19 is dark sea, not cyan.
The mission palette uses ocean RGB3 tones in slots 3/4 and fits wave pixels to
five shared blue entries. The source/MSX comparison documents color reduction.

Wave zeros now preserve scenery. Two clean 256×2 backups restore each hidden
page's crest background before streaming and transparent compositing. Explicit
startup initialization and scale invalidation prevent stale backups. The
remaining nine wave rows are opaque. Host atlas checks include the new backup
rows; the pixel/raster oracle now composites transparent wave pixels over the
actual terrain. See `docs/water-artwork.md` for the extraction and rendering.

Final validation: all 70 host tests pass; 53 NTSC raster/VRAM and 52 PAL VRAM
snapshots pass with zero regular deadline misses. Maximum redraws are
63.36/76.74 ms. Resident code/data total 20,798 bytes;
static RAM is 9,246 bytes plus IM2/stack/BIOS. The cadence remains six VBlanks.
Reports share ROM SHA-256 `5c91b26d6a02d956f21fbb2f92dc6e673921758d685da83321a295c685e98031`.


### Thin beach strip and water below land

The supplied original shoreline capture shows the five-row foreground sand
strip tapering into the wave crests, with animated sea below the island.
The beach records confirm six source rows and origin Y=1; the earlier bottom
row extension to the viewport bottom was an incorrect adaptation. Removed
that extension. The distant beach uses its source one-row height.

Generated water spans now follow every row of the foreground sand silhouette,
including odd X coordinates. Logical copies retain exact edges; opaque even
spans use HMMM. Runtime merges identical clipped intervals before drawing to
avoid extra commands away from the shoreline. The lower six water rows now
animate under the entire normal-scale island. Existing source surface queries
remain unchanged. All 70 host tests pass, including shoreline and water-below-
sand regression checks. Scenery now uses 493 tiles and a 6,386-byte map.

Final emulator validation: 53 NTSC raster/VRAM and 52 PAL VRAM snapshots pass,
with zero regular frame deadline misses. Maximum redraws: 76.11 ms NTSC /
87.15 ms PAL. Resident code/data total 21,353 bytes; static RAM
is 9,255 bytes plus IM2/stack/BIOS. The six-VBlank cadence is unchanged.
Reports share ROM SHA-256 `38246ef6f4ea7f753d982df52fb510b10cdb36281af2b57aebd6233dbe537aa3`.


### Full-height distant view and original reduced aircraft poses

The user's captures identified three linked errors: a 255-height prototype
limit, missing distant sea fill, and use of the static `plne` marker for the
player. The original player renderer instead selects `lpn…` pitch/bank records
and uses a 1208 baseline with a three-bit shift. Its distant sea rectangle is
color 10 from row 151 downward. Executable byte guards now cover these paths.

The mission prototype now supports height 0–1200 using 32-bit unsigned Q8 Y,
starts at height 92, and fills the distant ocean below its translated horizon.
All 27 `lpn…` poses retain their origins, transparency and source hashes in the
manifest. The existing pitch and turn state selects matching source poses.
The chosen 1200 bound covers the original projection span; exact source flight
physics and ceiling remain unported. Close-view continuous vertical panning
also remains pending.

Host tests cover expanded bounds, sea fill, source pitch/bank poses and cadence
parity. The harness now climbs to the full height and captures distant turns;
all reduced sprite caches are checked at every snapshot. The workload needs
eight VBlanks (7.5 fps NTSC / 6.25 fps PAL) to meet regular deadlines. Nominal
150 Hz simulation continues between view rebuilds. PAL's 24 simulation steps
sample six phases of the unchanged twelve-frame, twelve-step wave clock.

Final validation: 71 host tests pass; 50 NTSC raster/VRAM and
58 PAL VRAM snapshots pass with zero regular deadline misses.
Maximum redraws are 94.67/106.33 ms. Resident code/data:
22,871 bytes. Static RAM: 9,228 bytes plus IM2/stack/BIOS. Reports share ROM
SHA-256 `ebda00853d383c7db3c1851c5a6a110eacc8db552732bf3cbfb1deccc53ed737`.


### Carrier flag/radar artwork and two-pixel hardware heave

Extracted original `flg3`–`flg6` as four combined flag/radar overlays, retaining
their source indices, origins and record hashes. Opaque sky pixels replace the
previous cloth and radar positions. Playback is an explicit 30-tick MSX timing
adaptation. The heave cycle uses 0,1,2,1 offsets at 45-tick intervals; the total
excursion and one-pixel steps match the supplied captures.

Hardware vertical scrolling provides close-carrier heave without repeatedly
copying the hull. Aircraft and wave positions compensate; the dashboard's
scroll reset and interrupt line compensate together. Four-row clean waterline
backups prevent stale crests from showing through the hull between offsets.
Wrapped source rows 254–255 remain blank; wave frames 3,7,11 retain their last
two rows in upper-atlas 96×2 rectangles. Original wave artwork is unchanged.

Added source-art and atlas-overlap tests. Emulator checks now cover all four
carrier frames, all three heave heights, every wave/ship cached pixel and the
blank scroll-wrap rows, in addition to complete visible VRAM and raster checks.
See `docs/ship-effects.md` for the layout and remaining adaptations.

Final validation: all 73 host tests pass; 54 NTSC and 61 PAL full
raster/VRAM snapshots pass with zero regular deadline misses. Maximum redraws
are 95.59/107.90 ms. The eight-VBlank cadence is unchanged.
A one-pixel uniform separator at row 171 protects the dashboard reset from
VDP prefetch/interrupt latency. Resident code/data: 26,549 bytes; static RAM:
9,240 bytes plus IM2/stack/BIOS. Reports share ROM SHA-256
`bb847b271968e155e63b687f505682097fabcaaf75067400920d5d61995c361c`.
