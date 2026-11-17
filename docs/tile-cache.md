# Terrain tile cache

Added 2026-11-17. Applies to the mission ROM (`mission-flight`,
`mission-flight-debug`).

## Why

Up to now every terrain tile was uploaded once at boot into fixed VRAM
cells on pages 2/3, which hold 576 tiles. Map a needs 510. Map j with its
enemy ships baked into the scene needs 841, and most other maps need over
600 ([maps.md](maps.md)). The tiles now stay in ROM and VRAM keeps only
the ones near the camera.

## Layout

The converter (`tools/convert_mission.py`) orders the tiles:

1. **Uniform tiles first.** A tile with every pixel the same colour gets
   one of the lowest ids (`TERRAIN_UNIFORM_COUNT` of them). The renderer
   paints them with HMMV in `g_TerrainUniformColor[id]` and never needs
   their pixels. Tile 0 must be uniform (the sky).
2. **The others in first-seen order**, walking the map left to right, so a
   column's new tiles have consecutive ids.

Ids are grouped in **strips** of 8 consecutive tiles (id >> 3). A strip is
8 × 64 pixels, 256 bytes: its 8 tiles stacked. Strip pixels are stored in
ROM from bank 32 (`TERRAIN_TILE_BANK`), 32 strips per 8 KiB bank. The
column map follows from bank 40 (`TERRAIN_MAP_BANK`), padded so that no
column record crosses a bank.

VRAM has **52 slots** (`TERRAIN_SLOTS`). Slot s is at
x = (s % 32) × 8, y = 180 on page 2 + s / 32, so rows 180..243 of pages 2
and 3. They lie within the 56 whole 8 × 72 columns the static tiles used
to fill; the shape atlas is laid out around those. The 57th column was only
partly free and holds pilot-window frames. The rest of the old tile cells
(rows 244..251, and 4 columns of page 3 given up on 2026-11-17) hold the
rocket, muzzle-flash and splash frames (`atlas_slots(reserve_rockets=)`).

The converter checks that no 40-column stretch of the map needs more than
`TERRAIN_SLOTS - 12` strips (40), leaving 12 slots for churn. Map a needs
25 at most, map j with ships 32.

## Runtime (`src/msx/mission_streamer.c`)

- `Terrain_TileY(tile)` returns the VRAM y of the tile's top row and sets
  `g_TileSourceX`. A strip not in VRAM is loaded first. The Z80 run loop
  (`Column_Runs` in `column_ops.c`), `Terrain_RepaintBand` and the smoke
  restore all fetch their copy sources through it.
- `LoadStrip` picks a slot by **clock eviction**: a slot used since the
  hand last passed it has its mark cleared and is skipped. It waits for the
  running VDP command (a copy may still read the slot), then `UploadStrip`
  (Z80) maps the tile bank into window 3 and writes 64 rows of 4 bytes.
- `Terrain_Prefetch(camera, direction)` runs in the idle loop while a
  frame waits for its VBlank. It decodes the 4 columns ahead of the view in
  the direction of flight and loads one missing strip per call. Most new
  terrain finds its strips already in VRAM.
- `g_TerrainSlotStrip[slot]` (255: free) is global so that the verifiers
  can compare every loaded slot with the ROM.
- `Rope_Reset` clears the arresting rope's saved background at boot. Before,
  its uninitialised state restored garbage from a stale slot.

## Cost

Measured on the FS-A1WX (NTSC):

- `Terrain_TileY`: 0.39 ms per frame on average;
- render over the carrier: 48.7 ms;
- low over the carrier, p99 frame 132 ms against the 133 ms limit;
- the weapons verifier's publication intervals are the same as before the
  cache, tick for tick.

Strip uploads happen mostly in idle time through `Terrain_Prefetch`.

## Verification

- `tools/verify_p0.py` and `tools/verify_world_flight.py` dump
  `g_TerrainSlotStrip` with each snapshot (`.slots`). Every slot that holds a
  strip must match `tiles.sc5` byte for byte.
- `verify_world_flight.py` also checks that the tile banks and map banks in
  the ROM match the converter's output.
- `tests/test_column_runs_z80.py` and `tests/test_column_ops_z80.py` stub
  `Terrain_TileY`.

Possible next step: move `Terrain_TileY` to Z80.
