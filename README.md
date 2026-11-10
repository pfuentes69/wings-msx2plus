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
  src/main.c            Minimal SCREEN 5 build scaffold
  MSXgl/                Copied engine and tools
  docs/                 Port strategy and development notes
  tools/                Original asset research scripts
  reference_assets/     Preserved original resources and extraction manifest
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

The scaffold switches to SCREEN 5 and waits; it contains no gameplay or
decoded aircraft art. For a manual emulator check with openMSX installed:

```sh
openmsx -machine C-BIOS_MSX2+ -cart out/wings.rom
```

The first graphics milestone is complete: 52 Hellcat aircraft PNGs are in
`assets_src/hellcat/`, with a contact sheet and provenance manifest. Read
[the observed shape format](docs/format-shp.md) for established fields,
remaining uncertainties and visual comparisons. The next increment is a
three-frame SCREEN 5 conversion and emulator display test.

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
