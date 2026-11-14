# P2 part 1: fuel, oil, engine failure and lives

Implemented 2026-11-14. The evidence is in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md).

## Behaviour

| Rule | Value | Source |
| --- | --- | --- |
| New plane / hold service | fuel 192, oil 128 | Executable (plane init 0xb7ec) |
| Fuel burn | 1 unit per 28 ticks of flight: a full tank lasts ~7.2 min | Executable (0x1386, 0xb8b4) |
| Oil | stays at 128 until damaged; then leaks 1 per 80 ticks (6.4 s) | Executable (0x1386) |
| Engine failure | oil < 96 or the tank runs dry; no power, no guns | Executable (0xc6a0, mode 4) |
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

- After failure the plane noses down (forced dive input). The original's
  engine-out physics (mode 4) is not recovered.
- The crash happens when the dead plane reaches sea level, followed by a
  1-second hold. Splash/explosion art, deck collisions and crashing into the
  sea under power are P2 part 2 (landing and collisions).
- The next plane keeps the current weapon with a full load.
- GAME OVER returns to rank selection (the high-score table is P6).
- Damage (`Engine_Damage`) is injected by tests until enemy fire exists
  (P3–P5). The executable's two hit types are documented; smoke is not drawn
  yet.

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
