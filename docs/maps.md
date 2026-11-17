# Maps and per-map builds

Added 2026-11-17. The original has 15 maps, `a.map` .. `o.map`. Their map
numbers 0..14 come from rank × 4 + mission ([mission-flow.md](mission-flow.md)).
The mission ROM is built for one map at a time.

```sh
python tools/convert_mission.py --map j    # assets_msx/mission_j, src/generated/map_j
WINGS_MAP=j ./build.sh projname=mission-flight   # out/mission-flight-j/mission-flight.rom
```

Without `WINGS_MAP` the build is map a, in `out/mission-flight/` as before.

- **The carrier** stands at a different x on every map: the map's
  reset_x, given to the build as `WINGS_CARRIER_X`. The deck, cables,
  elevator, ship and signalman overlays are offsets from `CARRIER_X`. The
  converter's overlay tops are too.
- **Shared assets.** The carrier art, the palette, the dashboard and the
  shape atlas are the same for every map. Terrain tiles load into a
  56-slot VRAM cache as they come into view ([tile-cache.md](tile-cache.md)),
  so the tile count no longer has a VRAM limit.
- **Map assets.** The terrain tiles, the column map and the C tables
  (`mission_tiles`, `mission_surfaces`, `mission_island`, `mission_heights`)
  come from the map. The sources include those tables by name, from the
  map's folder on the include path.

## What fits the terrain engine

Updated 2026-11-17 with the tile cache. Tiles live in ROM from bank 32 and
the column map from bank 40, across as many banks as needed. Measured with
the converter:

| Map | Tiles | Strips (worst view ≤ 44) | Map width | Result |
| --- | --- | --- | --- | --- |
| a | 510 | 64 (25) | 7,608 px | built and verified |
| j | 841 with ships | 106 (32) | 7,944 px | built: open sea, no islands, a destroyer and a battleship |
| b, d, f | 564..606 | 71..76 (25) | 13,920..14,328 px | converts |
| c, e, g, i, k, l, n, o | 614..661 | 77..83 (25..26) | 15,576..27,712 px | converts |
| h, m | | | | the surface lookup is over its index/coordinate limits |

"Converts" means the converter accepts the map. It has not been built or
run. Before these maps can be played:
- the column table is in RAM, 2 bytes a column (up to 6.9 KiB for map o).
  The converter's estimate of RAM for the table and caches stays under its
  12,000-byte limit, but it should hold only the columns that change
  (wrecked huts);
- the surface lookup has to grow for h and m;
- the islands, ships and mission targets of each map need checking.

That is the campaign's work (P6). Map j serves the enemy ships until then
([research/amiga-ships.md](research/amiga-ships.md)).
