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
