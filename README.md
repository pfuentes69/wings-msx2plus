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
  src/main.c            Three-frame SCREEN 5 viewer
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
./build.sh            # Build out/wings.rom (32 KiB); no emulator auto-launch
./build.sh clean      # Remove generated out/ files
./build.sh rebuild    # Clean, compile, package and deploy to emul/rom/
```

On Windows use `build.bat` with the same arguments. MSXgl generates its shared
defaults in `MSXgl/projects/default_config.js` on first use. Keep project
overrides in `project_config.js`. Add new C/assembly modules to `ProjModules`
using paths without extensions, e.g. `src/core/flight`. MSXgl places intermediate
files in one output directory, so module basenames must be unique.

The ROM displays three decoded Hellcat views in SCREEN 5. Press **1**, **2**
or **3** to switch between pitched, level and opposite-pitch frames. An
underline identifies the selection. Each complete frame is drawn to a hidden
page and published at VBlank. For a manual run with openMSX installed:

```sh
openmsx -machine Panasonic_FS-A1WX-512K -cart out/wings.rom
```

The first graphics milestone is complete: 52 Hellcat aircraft PNGs are in
`assets_src/hellcat/`, with a contact sheet and provenance manifest. Read
[the observed shape format](docs/format-shp.md) for established fields,
remaining uncertainties and visual comparisons. The SCREEN 5 conversion and
viewer are validated on the Panasonic reference configuration and C-BIOS MSX2+ in openMSX; see
[prototype results](docs/screen5-prototype.md) for captures and measurements.
Flight physics and scrolling remain future increments.

To regenerate converted assets or run the emulator check, use the Python
environment with `requirements.txt` installed:

```sh
python tools/convert_hellcat.py          # Regenerate committed data and C arrays
python tools/convert_hellcat.py --check  # Detect stale generated artifacts
./build.sh
python tools/verify_screen5.py          # Requires openMSX 21 and graphics access
```

The reference emulator configuration is `Panasonic_FS-A1WX-512K`, matching
the development machine. The checker uses it by default and retains access
to personal openMSX machine definitions and ROMs while isolating test writes.
Use `--machine C-BIOS_MSX2+` for the firmware-free fallback.

The emulator check boots the ROM, presses selection keys and verifies VRAM,
palette, page switching and timing. Captures and results go under
`tools/.build/screen5-smoke/`. The viewer currently flattens transparent pixels
to solid sky and centers each padded source frame; it does not apply the
unconfirmed original hotspots.

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
