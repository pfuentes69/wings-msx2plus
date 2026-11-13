# Aircraft orientation and drawing-origin milestone

This records the animation milestone. The current renderer adds VRAM caching
and transparent scenery composition; see the [scrolling benchmark](scrolling-benchmark.md).
Measurements below are retained for their recorded ROM hash.

Implemented and validated 2026-11-10. The current ROM uses ten pitch choices
per facing and plays banking transitions when horizontal velocity reverses.
The fixed-point movement model remains unchanged. Press **T while stationary**
to inspect a turn without moving the logical aircraft position; holding T
starts one transition. Another request during a turn is queued, not used to
restart the animation. Cursor/joystick movement, Space/fire reset and idle
1/2/3 manual poses remain available.

[Turn preview](orientation/turn-preview.gif) assembles actual scanned-out
Panasonic emulator captures at a slightly slowed 40 ms per frame for review.
It is illustrative playback, not a frame-timing measurement.

## Recovered evidence and authored choices

The supplied `wings` executable contains these four-character frame-name arrays:

| File offset | Entries | Observed contents |
| --- | ---: | --- |
| `0x15d00` | 26 | Left-side banking data, starting `hc0f hc28 hc29 hc2a` |
| `0x15d68` | 26 | Right-side banking data, starting `hc05 hc22 hc23 hc24` |
| `0x15dd0` | 20 | Repeated right-side pitch frames, starting `hc0a hc0a hc09 hc09` |

The side labels are descriptive, not recovered symbol names. `tools/map_aircraft.py`
locates unique table anchors, validates their complete name runs and records
the source SHA-256. The raw recovered tables and the prototype's joins are
retained in `assets_msx/hellcat/animation/mapping.json`.

Two 22-step transitions join available halves of the banking data through
shared narrow/front views. They run from level right to level left and back.
This is a new MSX animation controller using original artwork and table order;
it is **not** a reconstruction of the original game's complete state machine.
Each sequence entry lasts five 150 Hz simulation ticks, about 0.73 seconds
for a complete turn. That timing is authored for this prototype. NTSC normally
presents each step; PAL sometimes advances two steps between presentations.

The original executable repeatedly subtracts signed shape-header words at
byte offsets 4 and 6 from object X/Y before drawing. Examples at file offsets
`0x392/0x396` and `0x56a/0x56e` establish this interpretation; the mapping tool
checks the corresponding instruction bytes. Thus these fields are drawing
origins, rather than values to replace with a crop's geometric center.

Twenty stored `fa`/`fb` frame pairs independently confirm that horizontal
reflection reverses each pixel row and uses `new_origin_x = width - old_origin_x`.
The paired origin sums equal the padded width. This is tested against raw
records, not just inferred from the appearance of the aircraft.

Forty included shapes are original recovered pitch/bank artwork. Nine
left-facing pitch shapes remain explicit reflections because their matching
names are absent from the preserved archive. The level-left view uses the
original `hc28`, including its source propeller details. No missing record is
claimed to have been recovered, and the derived views are marked in the
manifest. The later [P1 carrier corrections](p1-flight.md) add original gear-down
`hc40`/`hc41`, plus tail-down `hc21`/`hcoc`, bringing the resident atlas to 53 shapes. The later taxi increment adds nine
streamed ground-turn poses, for 62 shape records total. Damage artwork remains
outside this increment.

## Alignment and cropped data

The runtime now uses 49 variable-size packed shapes, rather than uploading
six fixed 48×32 canvases. Each record stores a data pointer, signed X/Y drawing
offsets, width and height. There are 21,370 packed pixel bytes; the largest
crop is 42 pixels wide, and the tallest is 36 pixels.

For the existing logical position `(x,y)`, the common drawing pivot is
`(x+25,y+16)`. An original source pixel `(sx,sy)` with origin `(ox,oy)` appears at:

```text
screen_x = x + 25 + sx - ox
screen_y = y + 16 + sy - oy
```

Zero-only source padding is cropped away. A zero column is retained where
needed to align the packed rectangle to a two-pixel SCREEN 5 byte boundary.
This preserves each original opaque pixel's placement exactly; it does not
recenter each frame or invent intermediate artwork.

[The source-pivot sheet](orientation/source-pivots.png) shows both joined
paths with a common orange pivot guide. The artwork's lateral movement during
banking is preserved. A stable logical pivot does not mean that the visible
fuselage center stays at the guide throughout a turn.

At viewport edges, these larger arcs can extend partially or wholly outside
the display. The renderer clips source rows/columns safely and clears the
previous hidden page's visible rectangle, including when the new frame is
entirely outside. Logical screen bounds remain the original movement bounds;
a future camera/scrolling pass should handle visibility during edge turns.
There is still a solid sky background and no general scenery compositor.

## Validation

All **45 host tests pass**. New checks cover source-table locations/counts,
velocity-to-pitch selection, turn order and duration, queued reversals, reset,
facing deadband, all 49 crops against original pixels/origins, all 49 shapes
at all four screen corners, and the 20 stored reflection/origin pairs.
Generated-asset checks pass; native builds still produce a 32 KiB ROM.

| Emulator configuration | Movement snapshots | Publication intervals | Maximum redraw | Missed deadlines |
| --- | ---: | ---: | ---: | ---: |
| Panasonic_FS-A1WX-512K | 11 | 430 | 13.77 ms | 0 |
| C-BIOS_MSX2+_EU | 11 | 360 | 13.35 ms | 0 |

The measured median publication intervals are 33.376 ms and 39.873 ms,
respectively, meeting the nominal 30/25 fps targets. These are emulated-machine
timings; future scenery/combat budgets still need measurement.

The movement verifier independently reconstructs each complete displayed
32 KiB page pixel by pixel from the converted shape metadata, including
clipping. It checks coasting, turn initiation/completion, both facings, reset,
all four logical bounds, palette/mode, VBlank publication, and absence of trails.

A separate stationary-turn test exercises both joins, verifies held-T edge
detection, confirms the logical pivot stays `(104,88)`, and checks full-page
pixels for 31 distinct original shapes on Panasonic and 28 on PAL. PAL's
sampled order is checked as a forward subsequence with no more than one
intermediate step skipped. Native captures are saved after scan-out so they
show the newly published page. The idle manual-pose regression also passes
five snapshots.

The stationary-turn test also moves to the lower-right screen limit and
repeats a turn: 22 native clipped-frame cases on Panasonic and 19 on PAL.
These include two completely off-screen frames on Panasonic and one on PAL;
their displayed pages correctly contain only sky, without stale artwork.

Retained reports all identify the tested ROM hash:

- [Panasonic movement](orientation/panasonic-flight.json)
- [PAL movement](orientation/pal-flight.json)
- [Panasonic turns](orientation/panasonic-turns.json)
- [PAL turns](orientation/pal-turns.json)
- [Idle pose regression](orientation/pose-verification.json)

The occupied ROM size is 26,813 bytes, leaving 5,955 bytes before the current
32 KiB limit. Static globals occupy 101 bytes plus the existing 452-byte IM2
reservation, stack and BIOS workspace. VRAM reservation remains two 32 KiB
pages. No audio or original executable code was added to the game; the
executable is inspected only for data facts and drawing-origin evidence.
Physical Panasonic/joystick validation remains pending.

## Reproduce

From the project root with the existing Python/Pillow environment, C compiler,
SDCC and openMSX 21:

```sh
python tools/map_aircraft.py
python tools/convert_hellcat.py --check
python -m unittest discover -s tests -v
./build.sh
python tools/verify_flight.py --output tools/.build/turn-flight
python tools/verify_flight.py --machine C-BIOS_MSX2+_EU --output tools/.build/turn-flight-pal
python tools/verify_turns.py
python tools/verify_turns.py --machine C-BIOS_MSX2+_EU --output tools/.build/turn-smoke-pal
python tools/verify_screen5.py --output tools/.build/turn-frame-selection
```

Movement and pose automation may run unthrottled; timing samples are still
emulated time. Turn capture runs throttled and waits for scan-out to preserve
reviewable images. Test writes/settings are isolated under `tools/.build/`,
with read access to the user's machine definitions and firmware.

Next: benchmark scene restoration, VRAM layout and terrain scrolling before
adding scenery. The animation data now consumes most of the 32 KiB ROM, so
mapper/storage choice needs to be considered before adding a larger world.
Original flight dynamics and musical arrangements remain separate work.
