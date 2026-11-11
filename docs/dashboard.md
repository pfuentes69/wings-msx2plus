# Original dashboard and pilot display

Mission-flight uses the supplied Amiga dashboard artwork, adapted from 640×37
to 248×36 pixels after the MSX's eight-pixel mask. A four-line separator gives
the line ISR time to stop horizontal scrolling before the dashboard begins.
VBlank restores the flight-view offsets.

![Original dashboard source](../assets_src/dashboard/original.png)

![Current dashboard in flight](mission/scenery-close.png)

The central window is a forward-looking pilot display, not a miniature
side-view map. It now uses original `3dl`/`3dc` perspective sprites, altitude
profiles, forward surface queries and a fixed `targ` reticle. The earlier 2D
overview has been replaced. The original continuous projection and dynamic
entities remain future work; the current profiles are an MSX adaptation.

The OIL/FUEL dials, equipment icons and counters remain static artwork until
those gameplay systems are implemented. They do not represent working fuel,
ammunition, lives or score. The complete layout is retained, with a reduced
shared palette.

The [source manifest](../assets_src/dashboard/manifest.json) retains hashes,
dimensions and origins for all 223 `dash.shp` records, as well as the packed
pilot atlas locations and 27 reduced aircraft records. Pilot frames load once into
unused atlas rectangles and are copied onto the hidden display page when the
profile changes. The atlas allocator and full-frame verification check that
these rectangles do not overlap aircraft or terrain.

See [the scenery fidelity pass](scenery-fidelity.md) for close/distant views,
waves, source evidence, memory layout, timing and remaining limitations.

```sh
python tools/convert_hellcat.py
python tools/decode_mission.py
python tools/convert_mission.py
python tools/convert_dashboard.py
./build.sh projname=mission-flight
```

Each converter supports `--check` to verify generated artifacts. Earlier
static-dashboard and side-overview reports are retained under `docs/mission/`
as historical milestones, with their original ROM hashes.
