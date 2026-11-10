# Wings of Fury SHP records — observed format

Status: pixel layout validated for the supplied Hellcat archive, 2026-11-10.
This is a description inferred from the supplied files, not a vendor spec.
Drawing-origin subtraction has since been established by executable inspection
(see `aircraft-orientation.md`); masks and several other header semantics remain unconfirmed.

## Containers

Some `.shp` files start directly with `PPkc`; others wrap it in `Rpck`.

`Rpck` consists of its four-byte signature, a big-endian 32-bit expanded size,
then runs. A control byte `c >= 128` copies the next `256-c` literal bytes.
A control byte `c < 128` repeats the next byte `c+1` times (including `c=0`).
The implementation bounds both source reads and expanded output. The supplied
`japplane.shp` and `cruiseship.shp` each have two unconsumed bytes `ff 00`
after the declared output; the tool logs these as observed padding. Other
trailing sequences are rejected. Their original purpose is unknown.

`PPkc` has a four-byte signature, a big-endian 16-bit count, `count` four-byte
ASCII names, then `count` big-endian 32-bit offsets. Offsets are relative to
the data section at `6 + 8*count`. The next offset ends a record; the archive
end ends the last record. The parser rejects truncated tables, unordered or
out-of-range offsets, empty records, duplicate names and unsafe names.

All 12 expanded archives and all 1,049 extracted records reproduce the
preserved files byte for byte. This validates the extraction against the
handoff; it does not independently authenticate the original files.

## Record header

Every one of the 1,049 supplied records satisfies:

```text
record_bytes = 20 + row_stride_bytes * height * nonzero_plane_map_count
```

| Offset | Size | Observed interpretation | Confidence |
| --- | ---: | --- | --- |
| `0x00` | 2 | Big-endian row stride in bytes, word aligned; padded width = stride × 8 | Established for decoded records |
| `0x02` | 2 | Big-endian image height | Established for decoded records |
| `0x04` | 2 | Signed horizontal drawing origin, subtracted from object X | Observed in executable drawing calls |
| `0x06` | 2 | Signed vertical drawing origin, subtracted from object Y | Observed in executable drawing calls |
| `0x08` | 2 | Candidate source horizontal position | Provisional |
| `0x0a` | 2 | Candidate source vertical position | Provisional |
| `0x0c` | 1 | Candidate constant color bits; zero throughout Hellcat | Provisional outside Hellcat |
| `0x0d` | 1 | Unknown; zero throughout Hellcat | Unknown |
| `0x0e` | 6 | Nonzero plane-to-color bit maps followed by zero entries | Established for Hellcat pixel reconstruction |

The complete header comparison is [hellcat-headers.csv](research/hellcat-headers.csv).
A short comparison:

| Record | Stride | Height | Plane maps | Payload bytes |
| --- | ---: | ---: | --- | ---: |
| `hc01` | 6 | 29 | `01 02 04 08 10` | 870 |
| `hc05` | 6 | 13 | `01 02 04 08 10` | 390 |
| `hc09` | 6 | 32 | `01 02 04 08 10` | 960 |
| `hc3b` | 4 | 28 | `01 02 14 08` | 448 |
| `wh01` | 6 | 17 | `01 02 04 18` | 408 |
| `spl0` | 2 | 9 | `17 08` | 36 |

A map value such as `0x14` contributes both color bits `0x04` and `0x10`
from a single stored plane. These shared planes explain the varying plane
counts without requiring a different compression scheme. All 116 Hellcat
archive records, including `fa`, `fb`, `wh` and `spl`, pass the decoder's
bounds and color-index validation. The exported aircraft subset contains
52 names beginning with `hc`.

## Pixels

After byte 19, each complete bitplane is stored contiguously, followed by the
next plane. Each plane contains `height` rows of `stride` bytes. The leftmost
pixel uses the most significant bit of the first byte. For `(x,y)`, plane `k`:

```text
byte_offset = 20 + (k * height + y) * stride + floor(x / 8)
bit = 0x80 >> (x % 8)
color_index = OR of plane_map[k] for all set bits
```

The decoder also initializes the color index from byte `0x0c`; this has no
effect on the zero-base Hellcat records. Its behavior on other archives is
an implementation hypothesis, not a general validated specification.
Nonzero byte `0x0d` variants are rejected explicitly.

The competing row-interleaved hypothesis produces disconnected horizontal
noise. Plane-major data produces consistent airframes, propellers, canopies,
white stars, front views and banked views. See
[the hypothesis comparison](research/layout-comparison.png), which uses the
stored RGB values without brightness expansion. The final contact sheet uses
the expanded palette described below.

Width includes padding to a whole 16-pixel word. No exact visible-width field
has been established. PNGs retain this padding rather than guessing a crop.
No independent mask plane has been established. Palette index 0 is treated
as transparent for previews; this is a documented assumption. The origins
and placement fields are exported to the original PNG manifest without applying
them. The current orientation converter applies the established drawing origins;
the decoder's legacy `origin_candidate` JSON key is retained for compatibility.

## Palette and visual evidence

The supplied `shapes/wingspalette` is 104 bytes: `CMAP`, four opaque bytes,
then 32 RGB triples. Those opaque bytes are not treated as an IFF chunk size.
Every component is stored in the upper nibble (`00` through `f0`). The default
PNG export expands `(component >> 4) * 17` to the full 8-bit range, matching
Amiga 4-bit RGB display levels. `--palette-scale stored` retains the literal
RGB bytes for comparison. The manifest records the palette SHA-256 and
selected transformation; no quantization or invented colors are applied.

Inspected examples:

- `hc01.png`: 48×29 padded canvas, diagonally pitched side view, white star,
  blue upper fuselage and pale underside.
- `hc05.png`: 48×13, near-level right-facing side view and propeller.
- `hc09.png`: 48×32, opposite pitch, consistent markings and shading.
- Other frames include front views, banking, opposite-facing flight,
  landing gear and damaged-looking aircraft. These are visual descriptions,
  not established animation-state assignments.

For external comparison, inspected the Amiga gameplay screenshot linked from
[OpenRetro's Wings of Fury page](https://openretro.org/amiga/wings-of-fury):
[reference image](https://openretro.org/image/628ead5a3abca04efd122d7b0fcf033e61564136?s=2x).
The blue/gray aircraft silhouette, white star and palette match visually.
Downsampling that 640×428 image by exactly two with nearest-neighbor gives
320×214 including its black border. At native screenshot origin `(138,26)`,
291 of `hc28`'s 306 nonzero-index pixels match RGB exactly (95.1%). Fifteen
pixels differ; a complete frame identity and the reason for those differences
are not established. This comparison supports the reconstruction without
claiming a pixel-perfect emulator capture of every frame. The external image
was used from `/tmp` and is not copied into the repository.

## Reproduce

Install dependencies in a virtual environment, then use a new output path:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/decode_shapes.py \
  reference_assets/original_files/Wings_of_Fury/shapes/hellcat.shp \
  tools/.build/hellcat-check \
  --palette reference_assets/original_files/Wings_of_Fury/shapes/wingspalette
.venv/bin/python -m unittest discover -s tests -v
```

Outputs are indexed PNGs, a nearest-neighbor contact sheet, and a manifest
linking record names, byte offsets, hashes, dimensions and candidate metadata
to the original archive and palette. Tools refuse to overwrite output folders.
For the row-interleaved rejected candidate, use `--layout row` and a different
output path. `--prefix ''` includes all 116 Hellcat archive records.

## Next increment

Convert the three validated frames to MSX SCREEN 5 data and demonstrate
switching between them in the minimal ROM, before adding flight physics.
Those frames jointly use only 11 opaque colors plus transparent index 0,
so they fit a 16-entry palette without color-count reduction. MSX color
precision, transparency and VRAM drawing strategy still require explicit
conversion and emulator checks. At 48×32 maximum for these three samples,
each would need 768 packed bitmap bytes when padded to that canvas;
this is a source-data calculation, not a measured rendering budget.
