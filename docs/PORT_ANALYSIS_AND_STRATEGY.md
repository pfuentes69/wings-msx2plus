# Wings of Fury (Amiga) to MSX2+ — Port Analysis and Development Strategy

**Handoff date:** 2026-11-10  
**Source:** user-provided `Wings of Fury (1990)(Broderbund)[a].adf` (880 KiB, AmigaDOS disk)  
**Target:** Panasonic FS-A1WX MSX2+ (Z80, V9958), initially at standard 3.58 MHz  
**Primary approach:** clean-room-compatible gameplay recreation driven by extracted asset data and behavioral analysis, rather than machine-code translation.

## 1. Executive summary

A playable adaptation is **technically feasible**, but high-fidelity reproduction at the original frame rate and visual resolution is uncertain until measured on an actual MSX2+. The central risks are the V9958 scrolling/rendering pipeline, Z80 CPU budget, hardware sprite scanline limits, and recovery of proprietary graphic and map formats. AI coding is particularly useful for building format inspectors, image decoders, asset conversion pipelines, unit tests, and modular C/assembly routines. It cannot replace validation on openMSX and actual hardware.

**Evidence already recovered from the uploaded ADF:** 73 files, 10 IFF/ILBM graphics decoded to PNG, 15 `.map` files, and 12 `.shp` graphics archives unpacked and split into **1,049** named binary records. The internal meaning of these individual records has **not** yet been fully decoded; do not label them finished sprites. The executable `Wings_of_Fury/wings` is present and can be studied for format usage if necessary.

**Next decisive milestone:** decode one record from `hellcat.shp` to a convincing, palette-correct image, then build and validate a batch decoder against several frames. Keep asset archaeology a separate track from MSX rendering development.

## 2. Verified evidence and file inventory

The accompanying `wings_of_fury_assets_handoff.zip` contains the recovered original game files, decompressed shape archives, individual PPkc records, decoded PNGs, contact sheet, and extraction scripts.

| Category | Verified contents | Status / caveat |
|---|---:|---|
| AmigaDOS files recovered | 73 | Filesystem traversal of supplied ADF; preserve hierarchy |
| IFF/ILBM graphics | 10 PNGs | Decoded with planar/ByteRun1 parser; inspect each for visual fidelity |
| Map files | 15 (`a.map`–`o.map`) | Original binaries, format not decoded |
| `.shp` archives | 12 | `Rpck` packed data expanded; `PPkc` records separated |
| Split resource records | 1,049 | Named raw binary records, **not** PNG sprites |
| Executable | `Wings_of_Fury/wings` | Original 68000 program, not ported |
| Sound files | `sounds/*` | Original data, not decoded/converted |

### Shape archive inventory

| Archive | Records |
|---|---:|
| `hellcat.shp` | 116 |
| `japplane.shp` | 27 |
| `world.shp` | 140 |
| `torpedo.shp` | 100 |
| `battleship.shp` | 25 |
| `destroyer.shp` | 28 |
| `cruiseship.shp` | 25 |
| `dash.shp` | 223 |
| `nightdash.shp` | 223 |
| `8thscale.shp` | 122 |
| `japcarrier.shp` | 12 |
| `selectrank.shp` | 8 |
| **Total** | **1,049** |

The existing unpacker recognizes `Rpck` at the start of `.shp` files and performs a byte-run-like expansion to the big-endian 32-bit target size. Inside expanded archives it recognizes `PPkc`, a big-endian 16-bit record count, 4-byte names, and a sequence of big-endian 32-bit offsets. **Both structures are reverse-engineered heuristics, not authenticated vendor specifications.** Check boundaries, sizes, duplicates, compression edge cases, and correctness against the game before depending on them. Some resource names may contain spaces. Record payloads appear to have binary headers but have not been formally identified.

The 10 PNGs are titles/UI artwork, **not yet the in-game airplane animation frames**. The preview contact sheet is `previews/wings_iff_contact_sheet.png`.

## 3. Technical constraints and target architecture

| Aspect | Amiga | MSX2+ approach |
|---|---|---|
| CPU | Motorola 68000 with custom graphics hardware | Z80 at ~3.58 MHz; fixed-point game simulation |
| Video | Amiga bitplanes, blitter, hardware sprites | V9958; SCREEN 5, 256x212 / 16 colors as initial candidate |
| VRAM | Amiga chip memory | Typical MSX2+ 128 KiB VRAM; budget pages and sprite patterns explicitly |
| Scrolling | Amiga chipset | V9958 horizontal scroll + staged VRAM updates; verify register details and edge behavior |
| Sprites | Amiga sprite system | MSX2 sprites: up to 32 total, limited to 8 per scanline (with color/size constraints) |
| Audio | Paula sampled channels | PSG by default; optionally MSX-MUSIC/OPLL; conversion/recomposition needed |
| Storage | Amiga disk files | ROM/MegaROM mapper or disk; first establish an easy-to-load development target |

**Important:** 256 x 212 x 4 bits = 27,136 bytes per SCREEN 5 bitmap display area. Two such display areas need 54,272 bytes, excluding padding, VDP address layout, sprite data and other allocations. A double-page scrolling strategy must be checked against the actual V9958 memory mapping; it is **not** automatically a complete seamless world streamer.

### Recommended software architecture

- **Portable core (C):** deterministic fixed-point flight simulation, world coordinates, mission state, projectiles, AI, collision and scoring. No direct VDP or ROM dependencies.
- **MSX platform layer (C + targeted Z80 asm):** joystick/keyboard, VBlank scheduling, V9958 register control, sprite attribute updates, graphics command queue, sound and memory management.
- **Asset pipeline (Python):** ADF extraction reference, SHP decompression, PPkc record decoding, palette recovery, indexed PNG previews, MSX palette quantization, tile/bitmap/sprite conversion, asset manifests and build integration.
- **Development harness:** host-native tests for simulation and format parsers, scripted openMSX launches and screenshot comparisons, real FS-A1WX acceptance tests.

Keep exact game design and code ownership distinct: do not translate copyrighted executable code verbatim or assume a public-release license for extracted assets. For publication, verify rights or replace artwork/audio with licensed equivalents.

## 4. Rendering strategy and tradeoffs

1. Start with **SCREEN 5** and a static one-scene prototype. Confirm the original artwork's usable sizes and palette before committing to a global palette.
2. Design **scrolling as a separately benchmarked subsystem**: use world-space coordinates and a V9958 display offset; draw incoming terrain columns/regions during safe windows. Measure VRAM command throughput, frame pacing, and edge artifacts. Consider camera bounds, page strategy and alternative pre-rendered screens if required.
3. Use **precomputed plane orientations** from recovered assets rather than rotation at runtime. Choose sprite-vs-software draw based on bounding boxes, colors, transparency, and scanline overlap; oversized/multicolored aircraft may need multiple sprites or VDP bitmap compositing.
4. Separate static terrain from dynamic objects. Explicitly manage 8-sprites-per-line pressure when aircraft, bombs, particles and explosions overlap.
5. Use **fixed-point** velocities, acceleration and gravity; tune behavior empirically against the original. Start with placeholder art until extracted graphics are proven.
6. Provide a **fallback render strategy** (lower frame rate, reduced detail, clipped playfield, fewer particles) instead of promising full-speed Amiga fidelity.
7. Run the first prototype on both PAL and NTSC timing if both will be supported. Target stable gameplay first; benchmark 25/30 fps before aiming for 50/60.

## 5. Development plan with acceptance gates

### Track A — Original asset research (do first; then parallelize)

**A1 — Inventory & reproducibility.** Produce a machine-readable inventory with path, size, SHA-256, signatures, archive membership, record name, offset and length. Run the supplied scripts from the repository root and compare outputs. Ensure all parsers are bounded and reject malformed data.

**A2 — Decode the Hellcat format.** Examine record headers and compare related IDs (`hc..`, `fa..`, `fb..`, `wh..`). Identify dimensions, origins/hotspots, pixel encoding, masks, bitplanes, palette selection and possible commands. Implement multiple candidate renderers and generate contact sheets; validate visually. If needed, inspect how the `wings` executable reads the records or compare emulator memory dumps. **Gate:** 3+ identifiable aircraft frames correctly rendered as PNG, with documented binary fields and tests.

**A3 — Batch decode remaining archives.** Reuse/extend decoder for enemy planes, world, ships, torpedoes and cockpit/UI. Export source-indexed PNGs, optional transparency, frame groups and a JSON manifest. **Gate:** decoded atlas and provenance back to exact source bytes.

**A4 — Maps and audio.** Reverse engineer `a.map`–`o.map`, identify terrain/object placement and mission metadata. Determine sound sample encoding/rates; design PSG/OPLL substitutions. **Gate:** one map visualized with correctly located objects and one representative sound reconstructed or approximated.

### Track B — MSX2+ game prototype

**B1 — Toolchain:** use VS Code + Codex, MSXgl and SDCC, openMSX debugger, `make` or a documented task runner. Begin with a tiny build and run target. **Gate:** deterministic clean build and automatic emulator launch.

**B2 — Flying plane:** player aircraft with fixed-point motion and directional frames over static ocean. **Gate:** continuous controllable flight with measured input response and frame timing.

**B3 — Scrolling terrain:** V9958 scrolling and streamed scene updates over a long landscape, separate camera/world coordinates. **Gate:** continuous scene without tearing, stutter or corrupted VRAM at the chosen frame rate.

**B4 — Combat:** projectiles, bombs, basic ground enemies, hitboxes, explosions. **Gate:** playable skirmish with safe sprite/CPU budgets.

**B5 — Carrier loop:** takeoff, landing, repairs, refuel/rearm. **Gate:** repeatable full gameplay loop.

**B6 — Missions, polishing, packaging:** missions, enemy AI, audio, menus, testing on FS-A1WX and MegaFlashROM SCC+ SD (verify mapper support). **Gate:** reproducible ROM/disk release with known compatibility and performance profile.

## 6. First Codex tasks (prioritized)

1. **Do not begin by writing the whole game.** Inspect files and generate an evidence-backed asset inventory.
2. Refactor the extraction scripts into portable CLI tools with arguments and no hard-coded `/mnt/data` paths.
3. Write tests for `Rpck`, `PPkc`, IFF/ILBM and record boundary handling. Preserve original source bytes.
4. Reverse engineer the `hellcat` individual record format and export first verified aircraft frames as PNG, together with a format note; log assumptions and counterexamples.
5. Build a minimal MSXgl project separately with one aircraft placeholder, input and frame timing diagnostics.
6. Only after the graphics format is understood, decide the target art conversion/layout strategy based on actual dimensions and palettes.

## 7. Suggested repository layout

```text
wings-msx2plus/
  docs/
    PORT_ANALYSIS_AND_STRATEGY.md
    extraction-notes.md
    format-shp.md
    hardware-budget.md
  reference_assets/              # original game resources; not to be redistributed blindly
    original_files/
    unpacked_shapes/
    previews/
  tools/
    inspect_adf.py
    unpack_shapes.py
    extract_iff.py
    ...
  assets_src/                    # decoded verified source assets
  assets_msx/                    # converted indexed artwork and metadata
  src/core/                      # portable C
  src/msx/                       # V9958, input, audio, build glue
  tests/
  Makefile
  README.md
```

Do not commit original proprietary game assets to a public repository without appropriate rights. Add explicit provenance markers to generated assets.

## 8. Unknowns and risks to resolve

- **Record encoding:** `PPkc` extraction succeeds structurally, but pixel format, orientation, masks, origins and possible drawing commands remain unknown.
- **Decompression validity:** current script does not fully validate every offset sequence or archival invariants. Regression-test and harden it.
- **Gameplay fidelity:** original physics, animation switching, AI and map semantics are not documented; determine by observation or disassembly.
- **MSX timing:** large bitmap updates and too many overlapping hardware sprites may be the main bottlenecks.
- **Cross-platform dev:** previous scripts assumed `/mnt/data`; Codex should make them portable on macOS/Python 3 and document dependencies (Pillow for IFF PNG previews).
- **Licensing:** private research and technical availability do not imply distribution permission for original code, images, music or sound samples.

## 9. How to use the handoff

1. Create a `wings-msx2plus` folder on your Mac.
2. Extract `wings_of_fury_assets_handoff.zip` in that folder (it contains `reference_assets/`, `tools/`, and a manifest/README). Put this strategy file in `docs/`.
3. Open the folder in VS Code and read `CODEX_HANDOFF_PROMPT.md`.
4. Ask Codex to inventory the extraction and decode **one Hellcat graphic record**, while maintaining clear notes on confidence and reproducibility.

**Definition of success for the next iteration:** a reproducible command that turns one named original `hellcat.shp` record into a visually validated PNG, plus an explanation of how the pixel data is encoded.
