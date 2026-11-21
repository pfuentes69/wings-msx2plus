# Map records

Added 2026-11-21 (release plan phase 1). The 1 MiB ROM holds every map; a
map's tables are loaded at run time instead of being compiled in.

## Pieces

| Piece | Where |
| --- | --- |
| Converters (unchanged) | `tools/convert_mission.py`, `tools/convert_cockpit.py` write each map's tables to `src/generated/map_<x>/` (C headers) and its tile and column-map banks to `assets_msx/mission_<x>/` |
| Packer | `tools/build_maps.py` reads those tables and writes one record per map (`assets_msx/maps/record_<x>.bin`), the bank of everything (`assets_msx/maps/maps.json`) and the ROM build's headers (`src/generated/map_rom/`) |
| Runtime | `src/msx/map_record.c` (resident): `g_Map`, `Map_Load`, `Mission_Surface`, `Mission_Query`, `Mission_Height` |

Banks are given from 64 up, map by map: the tile strips, the column map,
then the record (one bank). Map a: 64–66, 67, 68; map j: 69–73, 74–75, 76.

## The record

A record is its RAM part, `MapRecord` (`map_record.h`, about 1.4 KB, sized
for the largest map: the `MAP_*_MAX` capacities), followed by the tables
that stay in ROM: the surface runs (`end, word`) and the height runs (ends,
then heights). `Map_Load(n)` maps the record's bank into window 3 and copies
the RAM part into `g_Map`; the ROM tables are read by resident code that
maps window 3 for the moment and gives the caller's segment back (the
shadow `g_Bank3Segment` first, as `Decode` does), so banked code can call
it. `runs_at` and `heights_at` are their window-3 addresses. `Mission_Query`,
`Mission_Height` and `Mission_Surface` keep the last run found: the landing
check asks the height every step, and without the cache P0's takeoff off
the bow missed its NTSC deadline (137.5 ms of 133).

The first two bytes are the tile and column-map banks, read by Z80 code at
`_g_Map` and `_g_Map + 1`. Every u16 field sits at an even offset, so a
host compiler lays the struct out as SDCC does.

## Two builds of the same sources

- **ROM** (`mission-flight.js`): `-DWINGS_MAP_RECORD -Isrc/generated/map_rom`.
  The headers there have the per-map names (`mission_island.h`,
  `ISLAND_HUTS`, `s_HutX`...) as macros into `g_Map`.
- **Host tests**: one map's own headers (`-Isrc/generated/map_a`), compile-time
  tables as before.

So the module code works with either: an `#if` on a map's count goes
through `MAP_HAS(count)` (1 in the ROM, where the code must also be right
for a count of 0; `ships.c`, `cockpit.c`, `smoke_draw.c`), arrays are sized
by capacities, compile-time checks stay outside `WINGS_MAP_RECORD`, and
Z80 code reaches a field as `_g_Map + MAP_AT_<FIELD>`.
`TERRAIN_TILE_COUNT` is 2048 in the ROM (any id below it is a tile; the
tile cache's markers are 65534 and 65535). The values the same on every map
stay constants (`TERRAIN_UNIFORM_COUNT`, `TERRAIN_MAP_ROWS`, `PARKED_MAX`...),
checked by the packer.

## Cost

Profiled 2026-11-21 against the build before records: about 2 ms more a
frame over the carrier (values loaded instead of folded constants; the
world's width in a 32-bit compare had to become a shift, or SDCC called
the 32-bit multiply). Resident space is the tight limit: 64 bytes free.

## Columns

The column table stays in ROM (the column map's first bank). The columns
that show other runs (wrecked huts, the deck's spare planes, sinking ships)
are in a change list in RAM, sorted by column (`TERRAIN_CHANGES`,
`terrain_patch.c`). `TableWord` (Z80) reads a column's entry;
`tests/test_mission.py` checks that every change of a map fits the list at
once. Beyond the map's ends the views draw an open-sea column, chosen by
the packer (the middle of the longest sea run, checked plain).
