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
  shape atlas are the same for every map. The shape atlas is laid out
  around map a's 510 terrain tiles, so a map needing more would have to
  move it.
- **Map assets.** The terrain tiles, the column map and the C tables
  (`mission_tiles`, `mission_surfaces`, `mission_island`, `mission_heights`)
  come from the map. The sources include those tables by name, from the
  map's folder on the include path.

## What fits the terrain engine

The renderer was built around map a. Measured with the converter:

| Map | Tiles (≤ 576 in VRAM) | Column map (≤ 8 KiB, one bank) | Result |
| --- | --- | --- | --- |
| a | 510 | 6.5 KiB | fits |
| j | 306 | 4.5 KiB | fits: open sea, no islands, a destroyer and a battleship |
| b, f | 564, 601 | 8.9, 9.2 KiB | the column map needs two banks |
| c, d, e, g, i, k, l, n | 606..637 | 9.6..12.4 KiB | also over the RAM budget for the column table |
| h, m, o | 644..677 | 12.3..14.3 KiB | the tile bundle is also over 32 KiB |

Most maps are longer than a: up to 28,520 px against 7,608. Running them
needs:
- the column map read from ROM across banks;
- a column table in RAM for only the columns that change (wrecked huts),
  not the whole map;
- more VRAM for tiles, or tiles cached per region.

That is the campaign's work (P6). Map j serves the enemy ships until then
([research/amiga-ships.md](research/amiga-ships.md)).
