# Prompt to paste into the VS Code Codex extension

You are taking over an Amiga-to-MSX2+ reverse-engineering and game development project, **Wings of Fury (Broderbund) to Panasonic FS-A1WX MSX2+**.

## Read the handoff first

- Read `docs/PORT_ANALYSIS_AND_STRATEGY.md` in full.
- Inspect `reference_assets/README.md`, `reference_assets/MANIFEST.json`, all `tools/` scripts, and representative original shape files.
- Do not assume the `.bin` records are already decoded sprites: they are individual resource payloads extracted from proprietary `.shp` archives.

## Verified starting point

The user-supplied 880 KiB Amiga ADF was traversed to recover 73 files. Ten IFF/ILBM images were decoded to PNG, and 12 `.shp` archives were unpacked using `Rpck` and split using the `PPkc` index into 1,049 binary records. Fifteen `.map` mission files are present but undocumented. The PNGs recovered so far are primarily UI/title art, **not the complete gameplay sprites**. Existing scripts are research prototypes and may have assumptions/edge cases.

## Immediate objective

**Reverse-engineer the internal pixel/shape record format in `hellcat.shp` and produce at least three visually recognizable Hellcat aircraft frames as real PNGs.** Work iteratively, test competing hypotheses, and document evidence. This is NOT a request to port the entire game immediately.

## Work sequence

1. Confirm paths, counts, archive structure and SHA-256 digests against the manifest. Create or improve `docs/extraction-notes.md`.
2. Make extraction tools portable CLIs (input/output arguments, no `/mnt/data` assumptions); add a requirements file if needed. Preserve raw inputs and never overwrite them.
3. Inspect `reference_assets/unpacked_shapes/hellcat/` and `hellcat.shp.unpacked`; examine `hc*`, `fa*`, `fb*`, `wh*` records. Compare record headers, dimensions/metadata, common byte patterns, palette files and likely planar formats. Build a hex/header comparison table.
4. Implement candidate shape decoders in Python and generate contact sheets. Verify against visible Wings of Fury gameplay references. Consider bitplanes, run-length encodings, vector commands, origin/offset, transparency and Amiga blitter-style data.
5. If needed, disassemble only the minimal relevant logic in the supplied `Wings_of_Fury/wings` executable or study emulator memory state to understand the format. State clearly whether deductions are established or provisional.
6. Once three frames are validated, write `docs/format-shp.md` describing fields, byte order, decoding and examples; create a reusable `tools/decode_shapes.py`, tests and exported PNGs in `assets_src/hellcat/`.
7. After this milestone, propose the next concrete work increment for an MSX2+ SCREEN 5 conversion and a minimal MSXgl/openMSX prototype. Do not prematurely implement a large engine.

## Constraints and quality bar

- Target standard-speed MSX2+ / V9958 with 128 KiB VRAM; use portable C and Z80 assembly selectively; consider SDCC and MSXgl.
- Host development is macOS + VS Code; output scripts must work with Python 3 and documented dependencies.
- All binary parsers must validate bounds, offsets and decoded sizes; do not silently truncate without logging.
- Provide reproducible terminal commands and keep a concise progress log.
- Do not invent source details or claim an image is correctly decoded without visual or structural evidence. If blocked, show candidate decodes and explain what test resolves the uncertainty.
- Preserve copyrights: original assets are reference materials, not automatically licensed for public redistribution.

## At the end of this work increment

Report: (a) files inspected and verified, (b) established vs uncertain format findings, (c) generated PNGs with paths and visual summary, (d) exact commands/tests run, (e) remaining blockers, and (f) the next recommended step. Start working now.
