# Three-frame SCREEN 5 prototype

Validated 2026-11-10 with native macOS SDCC 4.6.0 and openMSX 21.
The ROM displays recovered Hellcat artwork and accepts real keyboard matrix
input. Keys **1**, **2**, **3** select `hc01`, `hc05`, `hc09`; an underline
marks the active selection. Holding a key does not repeatedly redraw it.

| Key | View | Emulator capture |
| --- | --- | --- |
| 1 | Pitched side view | [frame-1.png](prototype/frame-1.png) |
| 2 | Level side view | [frame-2.png](prototype/frame-2.png) |
| 3 | Opposite-pitch view | [frame-3.png](prototype/frame-3.png) |

![SCREEN 5 level-flight frame](prototype/frame-2.png)

## Conversion and rendering

`tools/convert_hellcat.py` converts the three indexed PNGs to 48×32 canvases.
They jointly use eleven opaque source colors. A shared palette preserves
those color indices and quantizes each RGB component to the nearest 3-bit
MSX value. Source transparency index zero resolves to a solid sky color.
Four remaining entries are reserved for the small selection UI.
The conversion retains silhouettes and source padding, centers each frame
vertically, and records source/output hashes and palette mapping in
`assets_msx/hellcat/manifest.json`.

Each raw SCREEN 5 frame is 768 bytes, left pixel in the high nibble. These
files have no BSAVE header. Generated arrays under `src/generated/` contain
all three frames and the 32-byte palette; normal builds do not need Python.
Regenerate with Pillow after changing the source PNGs, and run `--check` to
verify the committed generated data is current.

The viewer uses two 32 KiB VRAM pages. Initialization clears both pages and
adds the number labels. A selection redraw transfers the fixed 48×32 region
row by row to the hidden page and updates its underline. After the next
VBlank it changes the display page. The BIOS ISR remains active and the
program polls the keyboard matrix once per idle VBlank.

This is a solid-sky bitmap viewer, not a mask/terrain compositor. It does not
apply the unconfirmed original hotspot fields. Flight, scrolling, sound,
collision and hardware sprite rendering are not implemented.

## Verification and measured limits

The 32 KiB ROM contains 4,496 occupied bytes including assets, code and header
(the remaining capacity is padded). The linker reports 48 bytes of static
RAM including library state, excluding stack/BIOS RAM. The two reserved VRAM
pages occupy 64 KiB of the machine's 128 KiB.

| Configuration | Interactive redraw | Observed key-to-publication latency |
| --- | --- | --- |
| C-BIOS MSX2+, NTSC | 10.55 ms | 21.42–22.19 ms |
| C-BIOS MSX2+, PAL | 10.55 ms | 27.93–30.35 ms |

Redraw timing includes the 768-byte transfer and selection underline updates;
it excludes keyboard polling and waiting to publish. Key-to-publication
latency includes those waits. Samples are emulated time on standard-speed
C-BIOS machines, not host wall-clock speed. Three interactive redraw samples
were measured per configuration; these are observed values, not worst-case
bounds. The renderer fits within one NTSC frame, but already consumes about
63% of that frame's time before any gameplay work. This is a baseline, not
a commitment to using CPU transfers for the complete game.

The emulator script waits for startup readiness, captures five states
(initial, key 2, held key 2, key 3, return to key 1), and checks:

- Selection state, expected redraw count and display-page register.
- All 32 rows of each displayed aircraft against the packed asset bytes.
- All sixteen palette entries, SCREEN 5 mode and 212-line display setting.
- Absence of stray pixels outside the aircraft, labels and underline.
- Each interactive publication occurs inside VBlank.
- Redraw duration and input/publication latency through linker-resolved
  diagnostic symbols. Startup RAM initialization is excluded from profiling.

Results are preserved in [NTSC verification](prototype/ntsc-verification.json)
and [PAL verification](prototype/pal-verification.json), including the tested
ROM's SHA-256. Native screenshots were visually inspected. The test uses
openMSX's [documented debugger and screenshot commands](https://openmsx.org/manual/commands.html).
No original Panasonic firmware was required; physical FS-A1WX validation
remains pending. Windows and Linux build execution also remains unverified.

## Reproduce

From the repository root, with `requirements.txt` installed in the active
Python environment and openMSX 21 available:

```sh
python tools/convert_hellcat.py --check
python -m unittest discover -s tests -v
./build.sh
python tools/verify_screen5.py
python tools/verify_screen5.py --machine C-BIOS_MSX2+_EU --output tools/.build/screen5-pal
```

The emulator check needs graphics access and opens/closes an emulator window.
It stores its own settings under the output directory, leaving personal
openMSX settings alone. Runtime captures, VRAM dumps and timing reports go
under `tools/.build/`; selected captures and reports are retained here.

Manual launch:

```sh
openmsx -machine C-BIOS_MSX2+ -cart out/wings.rom
```

Next: a small portable fixed-point flight state with directional input over
this static sky. Keep motion/animation independent from the platform code,
and measure the combined update/render budget before starting scrolling.
