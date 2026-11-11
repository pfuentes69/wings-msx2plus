# Wings of Fury MSX2+

Target: Panasonic FS-A1WX (MSX2+, V9958, 128 KiB VRAM).
Read [the handoff](CODEX_HANDOFF_PROMPT.md) and
[the port strategy](docs/PORT_ANALYSIS_AND_STRATEGY.md) for research status.

The project follows MSXgl's [alternative file layout](https://aoineko.org/msxgl/index.php?title=Alternative_file_layout),
with game source under `src/`:

```text
wings-msx2plus/
  build.sh / build.bat   Build entry points; run from any directory
  project_config.js     Project modules, machine and toolchain settings
  msxgl_config.h        MSXgl compile-time configuration
  src/main.c            MSX input, frame timing and SCREEN 5 rendering
  src/core/flight.c     Portable fixed-point movement simulation
  src/core/aircraft.c   Pitch selection and banked turn playback
  src/core/scenery.c    Synthetic scrolling benchmark strip
  src/generated/        Converted aircraft arrays included in the ROM
  MSXgl/                Copied engine and tools
  docs/                 Port strategy and development notes
  tools/                Original asset research scripts
  reference_assets/     Preserved original resources and extraction manifest
  assets_msx/           Packed SCREEN 5 artwork, palette and conversion manifest
  out/                  Generated ROM and intermediate files
```

On macOS, install native Node.js, SDCC and the Xcode command-line C++ tools.
For Homebrew users: `brew install node sdcc`; install Apple's tools with
`xcode-select --install` if needed. The bundled Unix executables in this copy
are Linux binaries. The launcher uses native Node/SDCC on macOS and compiles
the included MSXhex source to `tools/.build/MSXhex` without changing the engine.
Linux uses host Node if available and the bundled SDCC/MSXhex; Windows uses
the bundled executables.

```sh
./launch.sh           # Build and run on Panasonic_FS-A1WX-512K
./launch.sh world-flight # Fly over scrolling terrain with a following camera
./launch.sh tile-flight  # Original-art terrain tiles; 64 KiB ASCII8 prototype
./launch.sh mission-flight # Source-backed a.map layout and carrier; slower baseline
./build.sh            # Build out/wings.rom (32 KiB); no emulator auto-launch
./build.sh clean      # Remove generated out/ files
./build.sh rebuild    # Clean, compile, package and deploy to emul/rom/
```

On Windows use `build.bat` with the same arguments. MSXgl generates its shared
defaults in `MSXgl/projects/default_config.js` on first use. Keep project
overrides in `project_config.js`. Add new C/assembly modules to `ProjModules`
using paths without extensions, e.g. `src/core/flight`. MSXgl places intermediate
files in one output directory, so module basenames must be unique.

The ROM now lets you move the Hellcat over a static sky using **cursor keys**
or **joystick port 1**. Motion has acceleration and a short coast after release.
The aircraft selects pitch from velocity and plays a banked transition when
reversing direction. **T while stationary** requests a turn for inspection;
holding T starts only one turn.
**Space or joystick fire** resets it to the center. While resting, **1/2/3**
retain manual pose selection for graphics checks. Movement takes priority.
**S** toggles a synthetic scrolling terrain strip; **P** pauses it and **R**
reverses its camera. This is an independent rendering benchmark. See
[scenery benchmark results](docs/scrolling-benchmark.md) for its measured limits.
The renderer restores scenery and transparently draws on the hidden page,
then publishes at VBlank.
An independent [V9958 hardware-scroll benchmark](docs/hardware-scrolling.md)
now streams a full-height, 4,096-pixel synthetic landscape through a two-page
ring, with verified PAL/NTSC timing and pixel comparisons. Build it with
`./build.sh projname=hardware-scroll`; its ROM is
`out/hardware-scroll/hardware-scroll.rom`. P pauses and R reverses it.
The integrated [world-flight prototype](docs/world-flight.md) adds a bounded
4,096-pixel world, following camera, transparent aircraft and trail restoration
using two alternating single-page rings. Run `./launch.sh world-flight`;
arrows/joystick fly, stationary T turns, and Space/fire resets altitude and
velocity while retaining horizontal world position. PAL/NTSC checks pass.
The [original-art tile prototype](docs/tile-terrain.md) replaces its test
graphics with palms, huts and shoreline pieces in an authored island scene.
It uses 16×16 SCREEN 5 bitmap tiles, a shared reduced palette and a 64 KiB
ASCII8 ROM. Run `./launch.sh tile-flight`; this is not an original mission-map
decode. Both PAL and NTSC pass pixel, cache, mapper and timing checks.
The [a.map mission prototype](docs/mission-map.md) recovers original object
positions, depth offsets, carrier layout and reset X. Run
`./launch.sh mission-flight`. The [scenery fidelity pass](docs/scenery-fidelity.md)
lowers the carrier/land strip, animates the original wave frames, replaces the
central overview with a forward pilot view, and switches to original 1:8
scenery at altitude. It uses a 128 KiB ASCII8 ROM and currently targets
7.5/6.25 fps with nominal 150 Hz simulation; scale changes briefly rebuild the
hidden pages. Collision, original flight dynamics and instrument behavior are
still pending.
For a manual run with openMSX installed:

```sh
openmsx -machine Panasonic_FS-A1WX-512K -cart out/wings.rom
```

The first graphics milestone is complete: 52 Hellcat aircraft PNGs are in
`assets_src/hellcat/`, with a contact sheet and provenance manifest. Read
[the observed shape format](docs/format-shp.md) for established fields,
remaining uncertainties and visual comparisons. The SCREEN 5 conversion and
viewer are validated on the Panasonic reference configuration and C-BIOS MSX2+ in openMSX; see
[prototype results](docs/screen5-prototype.md) for captures and measurements.
The movement and animation increment targets 30 fps on the Panasonic reference
machine and 25 fps on PAL. See [flight prototype results](docs/flight-prototype.md)
for the initial movement milestone. The current
[orientation results](docs/aircraft-orientation.md) cover 49 cropped shapes,
recovered drawing pivots, clipping and both turn sequences. Authentic flight
physics and original-map integration remain future increments; animation playback timing
is currently authored for this prototype.

To regenerate converted assets or run the emulator check, use the Python
environment with `requirements.txt` installed:

```sh
python tools/convert_hellcat.py          # Regenerate committed data and C arrays
python tools/convert_hellcat.py --check  # Detect stale generated artifacts
./build.sh
python tools/verify_screen5.py          # Requires openMSX 21 and graphics access
python tools/verify_flight.py           # Motion, bounds, trails and frame deadlines
python tools/verify_turns.py            # Original bank-frame order, pivots and held T
python tools/verify_scrolling.py        # Terrain seams, transparency and frame deadlines
```

The reference emulator configuration is `Panasonic_FS-A1WX-512K`, matching
the development machine. The checker uses it by default and retains access
to personal openMSX machine definitions and ROMs while isolating test writes.
Use `--machine C-BIOS_MSX2+` for the firmware-free fallback.

The emulator checks boot the ROM and verify controls, VRAM, palette, page
switching and timing. Captures and results go under
`tools/.build/screen5-smoke/` and `tools/.build/flight-smoke/`.
The renderer caches aircraft in VRAM and preserves transparent pixels. It
applies the signed source drawing origins and clips cropped shapes at the
viewport edges. Most left-facing pitch poses are explicit reflections;
banking uses recovered original frames.

The research tools now accept explicit input and output paths and refuse to
overwrite output directories. Install `requirements.txt` in a Python virtual
environment, then use its Python executable for these commands:

```sh
python tools/unpack_shapes.py reference_assets/original_files/Wings_of_Fury/shapes NEW_SHAPE_OUTPUT
python tools/extract_iff.py reference_assets/original_files/Wings_of_Fury/shapes NEW_IFF_OUTPUT
python tools/decode_shapes.py reference_assets/original_files/Wings_of_Fury/shapes/hellcat.shp NEW_HELLCAT_OUTPUT --palette reference_assets/original_files/Wings_of_Fury/shapes/wingspalette
python tools/inspect_adf.py ORIGINAL.adf NEW_ADF_OUTPUT
python -m unittest discover -s tests -v
```

The ADF extractor supports standard 880 KiB DOS0/OFS images; the source ADF is
not included, so its refactor is tested with synthetic blocks only. The IFF
tool also finds two embedded palette images inside Rpck containers, bringing
its output to 12 images; all ten original previews reproduce exactly in RGB.
Original exploratory scripts are preserved under `tools/legacy/`.
See `reference_assets/README.md` and `reference_assets/MANIFEST.json` for
the unchanged source inventory and provenance.

Audio extraction is also working: `assets_src/audio/` contains eight effect
WAV previews, six recovered 8SVX instruments and four 10-second music previews
rendered through the original music replay format. Effect audition rates are
assumed; music previews are bounded clips. See
[audio extraction notes](docs/audio-extraction.md) for evidence and remaining
work before PSG/MSX-MUSIC adaptation.

```sh
python tools/extract_audio.py reference_assets/original_files/Wings_of_Fury NEW_AUDIO_OUTPUT
afplay assets_src/audio/music/previews/subsong-0.wav   # macOS audition
```
