# Wings of Fury MSX2+

Target: Panasonic FS-A1WX (MSX2+, V9958, 128 KiB VRAM).
The [implementation plan](docs/PORT_ANALYSIS_AND_STRATEGY.md) now targets the
supplied manual's complete game loop. See the [manual requirements and gaps](docs/MANUAL_FUNCTIONAL_SPEC.md)
for page references, prototype differences and acceptance criteria. The
[English Amiga reference](docs/AMIGA_ENGLISH_REFERENCE.md) adds held/short-click
Fire, one-torpedo stock and saved games; the
[French review](docs/AMIGA_MANUAL_REVIEW.md) supplies Space/Enter and landing-side
details and records conflicting double-Fire wording. The release MSX controls
use Space/trigger 1 for guns and N/GRAPH/trigger 2 for the secondary action;
Enter is reserved for menus/text. [P0 controls and state](docs/p0-foundation.md)
are implemented; the release starts at rank selection.
[P1 flight and takeoff](docs/p1-flight.md) now starts with the
[carrier elevator](docs/carrier-elevator.md) raising the plane from inside the ship.
The [flight model is rebuilt from the original](docs/flight-model.md):
hold Left to roll along the deck and off the bow, then Up+Left to climb away.
In flight, a direction with Up or Down steps through the climb and dive
angles; a dive holds until you pull out; pushing the other way flies the
original's turn. To land, approach from the right low over the sea and hold
Up alone (the stall flare) onto the deck, and keep holding it so the hook
catches a cable. Left/Right also taxi on deck and turn the plane round at
rest. Stop over the platform and press either logical Fire button to enter the
hold, reload and emerge with the same heading.
[Island combat](docs/island-combat.md) has begun: bombs wreck the island's
huts (150 points, then they smoke) and empty its manned dugouts (200). The
[original handoff](CODEX_HANDOFF_PROMPT.md) is historical research context.

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
./launch.sh           # Build and run the game (mission ROM) on Panasonic_FS-A1WX-512K
./launch.sh mission-flight-debug # Renderer/training harness (R/T shortcuts)
./launch.sh wings     # Original 32 KiB viewer (out/wings.rom)
./build.sh            # Build out/wings.rom (32 KiB); no emulator auto-launch
./build.sh clean      # Remove generated out/ files
./build.sh rebuild    # Clean, compile, package and deploy to emul/rom/
```

The launcher uses crisp pixel scaling for legible dashboard type and keeps
these display settings local to the emulator session.

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
The [world-flight](docs/world-flight.md) and [original-art tile](docs/tile-terrain.md)
prototypes established the following camera, trail restoration and 16×16
SCREEN 5 tile renderer that the mission build now uses. Both builds were
retired on 2026-11-13 after outgrowing their 32/64 KiB layouts; their source
remains in git history up to commit `af61737`. The tile converter is kept
because its palette and index mapping feed the mission, ship and dashboard
converters.
The [a.map mission prototype](docs/mission-map.md) recovers original object
positions, depth offsets, carrier layout and reset X. Run
`./launch.sh mission-flight`. The [scenery fidelity pass](docs/scenery-fidelity.md)
lowers the carrier/land strip, animates the original wave frames, replaces the
central overview with a forward pilot view, and switches to original 1:8
scenery at altitude. It uses a 256 KiB ASCII8 ROM with [banked code](docs/rom-banking.md) and currently targets
7.5/6.25 fps with nominal 150 Hz simulation; scale changes briefly rebuild the
hidden pages. The [weapons foundation](docs/combat-prototype.md) adds gunfire,
bombs and terrain impacts. [P0](docs/p0-foundation.md) supplies rank/briefing/loadout
shells, three lives and a 30-bomb load: Space/trigger 1 fires guns, while
N/GRAPH/trigger 2 releases the selected secondary. Esc pauses, Ctrl-R restarts
at rank selection, and Ctrl-F inverts joystick vertical input. Rockets/torpedo
are inventory previews; their launch behavior and actual save/load are deferred.
Use `./launch.sh mission-flight-debug` for instant-flight renderer inspection
with R reset and stationary T turn. Targets, damage, scoring, carrier landing
remain pending; P1 flight constants still need Amiga timing comparison.
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
