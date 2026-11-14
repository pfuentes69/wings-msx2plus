# Amiga cannon: executable findings

Recovered 2026-11-13 from `reference_assets/original_files/Wings_of_Fury/wings`
by static 68000 disassembly. Nothing here was observed running on an Amiga;
each item carries a confidence label.

## Executable layout

| Item | Value | Confidence |
| --- | --- | --- |
| Format | AmigaDOS hunk file, not packed: CODE 77,644 bytes, DATA 15,456 bytes plus 5,008 bytes BSS | Established |
| Code style | Mostly Lattice/SAS C plus hand-written assembly (`init.asm` string) | Established |
| Globals | Small-data model: A4 = DATA hunk + 0x7FFE, so data offset `d` is `d - 0x7FFE(a4)` | Established (startup clears BSS at `-0x439e(a4)`) |
| Far calls | `jsr -$xxxx(a4)` jumps into `jmp abs.l` stubs at the start of the DATA hunk | Established |
| Floats | Motorola Fast Floating Point (mathffp) values in tables | Established |

Code addresses below are offsets into the CODE hunk (file offset = 0x28 + address).

## Gunfire is an overlay, not travelling bullets

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| `hellcat.shp` records `fa01`..`fa14`, `fb01`..`fb14` | 40 muzzle flash + tracer overlays: poses 1..10 right, then 1..10 left; `fb` has the longer tracer | Established (pixels, origins and geometric fit) |
| Player renderer at 0x0672 | While fire flag `-0x5c94(a4)` is set, steps a 4-phase counter over pattern `[0,1,0,2]` (data `-0x63f6(a4)`), then draws hellcat shape `pose - 5 + 0x43` (pattern 1) or `+ 0x57` (pattern 2), plus 10 when facing left (`-0x4084(a4) < 0`), at the aircraft's own position using the shape's drawing origin | Established control flow; index-to-record mapping inferred from the 40-record count and the geometric fit |
| Composite check | Drawn at the same object point as the matching `hc` pose, every flash lands on the propeller in all 10 poses and both facings | Established ([image](../cannon/original-flash-overlays.png)) |
| No bullet sprites or bullet list | Shape archives contain no bullet art; the allocated object lists are Ricochet, Splashes, Smoke, Balloons, MasterList and AthList | Established for the files present |

## Surface strikes are hit-scan

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| 0x19bc, called each frame from 0x143a | If firing, the pitch term `-0x5bfa(a4)` < 0 (nose down) and altitude `-0x5f86(a4)` < 0xa0, finds a free entry in the 20-slot Splashes list | Established control flow |
| 0x1a46 | Impact X = plane X `-0x41a2(a4)` ± (altitude × 256) / `tan_table[angle]`, sign by facing `-0x5f72(a4)`; returns 0 when not firing downward | Established arithmetic |
| `-0x6892(a4)` | 256-entry table, entry k = 256·tan(k·90°/256) | Established (checked against values) |
| 0x1a8c | Marks every object within ±16 px of the impact X in list `-0x5afe(a4)` as hit | Established control flow; object types not yet mapped |
| 0x12a0 | Angle index = pitch × 1024 / 18000, where pitch `-0x555c(a4)` is in centidegrees. Against the tan table's 90°/256 scale this is about **twice** the nose pitch | Arithmetic established; whether the doubling is deliberate is **unknown** |

Hits on aircraft and ships were not traced. They probably use other routines.

## Flight model notes found on the way

| Global or table | Meaning | Confidence |
| --- | --- | --- |
| `-0x3212(a4)` | Player aircraft structure: +0x0c state, +0x14 facing (+1/−1), +0x16 turn/pitch step | Probable |
| `-0x555c(a4)`, `-0x5bf6(a4)` | Pitch and turn components of the heading, centidegrees | Probable |
| `-0x5a6c(a4)` | Pitch pose 0..10 used for drawing and gunfire | Probable |
| `-0x5bf0(a4)` | 26-step turn sequence counter; facing flips at step 14 | Probable |
| Data 0x2b74 | Sine table in 1° steps (FFP), used with `|angle| / 100` | Established |
| Data 0x2b0c | 26 FFP per-step speed factors (1.0 … 0 … 0.98) | Values established; use probable |
| Data 0x2aac / 0x2ac2 | Per-pose body and gear clearance below the pivot, used for ground contact | Probable |
| Data 0x2de0 / 0x2ad8 | 20 angle steps map to poses `hc0a hc0a hc09 … hc01` | Established |

## How the MSX port uses this

- The renderer draws the original `fa`/`fb` overlay for the drawn pitch pose,
  alternating them on every presented frame. At 5–8 fps the original's blank
  phases would read as stutter, so they are dropped. There is no overlay
  for distant, ground or turning poses, because no source art exists for them.
- Cannon strikes are hit-scan. Only downward fire within 160 px of the surface
  strikes, at the point where the drawn tracer's line meets the sea, deck or
  ground. The per-pose slope comes from the `fb` tracer art
  (`tests/test_combat.py` recomputes it). The original's apparent doubled angle
  is not copied until it can be checked at runtime.
- Each overlay variant streams into a 16×12 VRAM slot at page 0, x=240, rows
  212/224, the only free hidden-row space. See `tests/test_vram_layout.py`.
- The original's pale-yellow flash core (RGB3 7,7,3) has no match in the
  16-colour playfield palette. It maps to white, the closest colour by
  brightness; nearest colour distance tied grey with orange.

The reproduction helpers used for this note are not committed. Repeat the
analysis by parsing the hunks and disassembling with Capstone (`CS_ARCH_M68K`).
