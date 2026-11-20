# Spare planes on the deck

Updated 2026-11-20.

The original draws the planes left as parked planes on the carrier's deck
(0x3abc, [research/amiga-player-crash.md](research/amiga-player-crash.md)).
When the next plane comes after a loss, one fewer is shown.

## The original

- While the carrier is afloat, it draws `planes left − 1` copies of `Cpln`
  (world.shp, 32×15, origin (14, 47)), at most 8.
- The first is 200 px bow-ward of the elevator (the map's reset x). The
  others follow 30 px further each.
- They stand on the deck: world altitude 11, less the deck's heave and
  sink.
- The distant view draws the 8thscale `Cpln` (a few pixels).

## The port

- At most **2** are shown. Cheats or promotions may give more planes, but
  the deck stays at 2.
- They are part of the scenery, not overlays. `tools/convert_mission.py`
  draws every view with 2 planes (`reconstruct(..., parked=2)` in
  `tools/decode_mission.py`). It also keeps the deck's changed columns,
  rendered with 1 plane and with none, as variant columns, as for wrecked
  huts:
  - 8 near columns and 1 far column on maps a and j;
  - in `parked-variants.indices`, `s_ParkedNear` / `s_ParkedFar` in
    `mission_island.h`.
- `Island_Parked(lives)` (`src/core/island.c`) runs once a frame. When
  `lives − 1` (capped at 2) changes, it remaps those columns
  (`Terrain_Remap`). This happens when the next plane comes after a loss,
  on a new game, and on a promotion. Nothing is drawn per frame.
- With one plane left, the plane nearer the elevator stays (the original's
  first).
- Cost: map a went from 510 to 532 tiles (one more tile bank, 34); map j
  needs one more bank (36). The VRAM atlas no longer follows map a's tile
  count. It is laid out around the old static footprint of 510 tiles
  (`STATIC_TILE_FOOTPRINT` in `tools/convert_dashboard.py`), so new tiles
  move nothing.

## Verification

- `tests/test_mission.py`: the scene shows both planes; the variants show
  the near one, then none; the tiles round-trip with the variant columns.
- `tools/verify_crash.py`: the next plane rolls past the deck after the
  first loss (one parked plane) and after the second (none). Both
  snapshots are compared with the pixel model.
- `verify_p0` and `verify_crash` pass the lives to the model's background
  (`island_background(..., lives)`), so every carrier snapshot is checked
  at the right count.
