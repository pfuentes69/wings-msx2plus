# P2 part 1: fuel, oil, engine failure and lives

Implemented 2026-11-14. The evidence is in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md).

## Behaviour

| Rule | Value | Source |
| --- | --- | --- |
| New plane / hold service | fuel 192, oil 128 | Executable (plane init 0xb7ec) |
| Fuel burn | 1 unit per 28 ticks of flight: a full tank lasts ~7.2 min | Executable (0x1386, 0xb8b4) |
| Oil | stays at 128 until damaged; then leaks 1 per 80 ticks (6.4 s) | Executable (0x1386) |
| Engine failure | oil < 96 or the tank runs dry; no power, no guns; the plane falls as the original's does (see [flight-model.md](flight-model.md)) | Executable (0xc6a0, mode 4, 0xafba) |
| OIL needle | `(oil − 96) / 2`; +6 frames under throttle (the flight model's flag: pushing the way you fly, or Down alone) | Executable (0xee5e, 0xbff4) |
| FUEL needle | `fuel / 8`, at most frame 22; twitches at empty | Executable (0xef2a) |
| Lamps | oil < 116 and fuel ≤ 64; the original blink counters (10 and 8) | Executable |
| Needle motion | one frame per tick toward the target | Executable |
| Lives | crash → one plane lost → next plane on deck, or GAME OVER at zero | Manual |

One original tick is 12 steps of the 150 Hz simulation clock (12.5 Hz, from
the PAL VBlank server running logic every 4th interrupt). `src/core/engine.c`
holds the rules (banked, segment 16; one `Engine_Tick` call per original
tick). `src/world_flight.c` drives it: fuel burns only while airborne, and
warnings are active in flight and on deck. The hold refills through
`Game_OpenService` + `Engine_Reset`.

**Provisional, until the original is mapped further or observed:**

- The crash happens when the dead plane reaches sea level, followed by a
  1-second hold. As in the original (0xafba), the plane is first clamped to
  the surface, so the splash or explosion plays on it, not where the
  plane's lowest point first touched. Splash/explosion art, deck collisions and crashing into the
  sea under power are P2 part 2 (landing and collisions).
- The next plane keeps the current weapon with a full load.
- GAME OVER returns to rank selection (the high-score table is P6).
- Damage (`Engine_Damage`) is injected by tests until enemy fire exists
  (P3–P5). The executable's two hit types are documented.

## Engine smoke

A damaged engine smokes as the original's does (0x1bfc; evidence in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md#engine-smoke-0x1bfc-0x54e0-0x5460-0x0ee0)).
Damage is 128 − oil. Above 19 a puff comes every time, below that with the
original's odds (3/16 rising to 12/16). Puffs start 10 px ahead of the
plane and 2 px above its origin, rise and drift right 1–2 px a tick, and
shrink through `smk4`..`smk0` in 2.8 s. The far view uses its two small
dots. `src/core/smoke.c` holds the rules and `src/msx/smoke_draw.c` the
drawing, both banked in segment 22.

| MSX choice | Why |
| --- | --- |
| 8 puffs; the emitter checks every 4th tick (the original: every other tick, from a 40-effect pool) | Bounds the drawing cost |
| Puffs are drawn behind the plane and erased without VRAM backups: a sky fill over plain sky tiles, otherwise the tiles repainted one at a time from the page's tile cache (sky fill above the terrain rows). Rows under the signalmen and the elevator, which the cache marks for repaint, are repainted from the map, and the overlays draw again on top | The atlas has no room for backups |
| Erasing happens before the frame's new terrain columns | Puffs that scrolled out of view are still in the page's ring, and the tile cache does not know about them |
| Smoke stays above the wave strip (row 159) | The strip has its own backup and restore |

`tests/test_smoke.py` covers the emitter odds, spawn point, drift, the
five 7-tick stages, the 16 px floor, the pool and the turn offsets. The P0
run damages the engine (oil 100) during the engine scenario and
pixel-checks a snapshot of the trail (`engine_smoke`).

## Instruments

Each dial has all 23 original needle frames with the lamp dark and lit, in
banks 17–20 (see [dashboard.md](dashboard.md)). At most one dial is redrawn
per rendered page (about 5 ms each). Because the needles move only one frame
per tick, the deferral is invisible. `Dashboard_Gauges` reports what the page
shows, so the published gauge state, `g_DisplayGauges`, and the pixel
oracles stay exact.

## Verification

- `tests/test_engine.py` covers:
  - new-plane values and needles;
  - burn rate and flight-only burning;
  - the 7.2-minute tank and dry-tank failure;
  - the post-damage leak and seizure below 96;
  - heavy-hit fuel loss;
  - instrument mapping, needle sweep, the original blink patterns, and the
    empty-tank twitch.
- The `tools/verify_p0.py` P0 smoke run adds:
  - low fuel, where the lamp must blink and the needle sweep down;
  - a dry tank, where the engine fails, the plane crashes, a life is lost,
    and the next plane is refuelled and repaired on deck;
  - a last-plane crash leading to GAME OVER, with a button returning to rank
    selection.
- Every snapshot, menus included, compares the whole dashboard with
  `compose()` for the dumped game and gauge state.
- Results: 93 snapshots pass on NTSC and on PAL.
