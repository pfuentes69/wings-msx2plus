# ROM size projection

Estimated 2026-11-14 from the current mission ROM and the original assets.
Segments are 8 KiB (ASCII8). Each kind of data starts on a segment boundary,
so part-filled segments waste space; the projection allows about 15% for that.

## Today: 21 of 32 segments, ~130 KB of data

The ROM is 1 MiB since 2026-11-21 (512 KiB from 2026-11-17): the terrain
tile cache keeps tiles in banks 64+ and the column map in banks 72+. Banks
4–6, 24 and 32–46 are free (some of the table below predates that).

| Content | Segments | Bytes |
| --- | --- | --- |
| Resident code + constants | 0–2 | 22.9 K |
| Banked code (HUD; menus/ship/elevator/engine/landing) | 3, 16 | 13.0 K |
| Mission A terrain: 510 tiles + map (moved 2026-11-17, [tile-cache.md](tile-cache.md)) | 32–33, 40 | 22.2 K |
| Aircraft (Hellcat, cannon flash, crash art) | 8–10, 14 | 28.1 K |
| Dashboard: panel, pilot views, waves, tables | 7, 11, 12 | 14.7 K |
| Ship, crew, elevator | 13, 15 | 7.0 K |
| HUD values: digits, dials dark/lit | 17–20 | 25.7 K |

This covers one mission of fifteen, with no enemies, sound, title or intro.

## Still to come (estimates)

| Content | Source | Estimate |
| --- | --- | --- |
| 14 more mission maps | `b.map`..`o.map`: 3.5–7.1 KB each, 66 KB in total. Mission A's 1.9 KB map converts to 6.4 KB (column RLE of 16-bit tile ids, 3.3×) | **120–180 K** at the current encoding; **~70–90 K** with a denser runtime format |
| Extra terrain tiles for other islands | world.shp | 10–20 K |
| Enemies: battleship, destroyer, cruiser, Japanese carrier, aircraft, torpedoes, soldiers, guns | 160 KB of packed archives | **60–120 K**, depending on how many frames are kept |
| Night missions | `nightdash.shp`, palettes | ~15 K |
| Title, rank, briefing and high-score screens | `wingstitle` (30 KB IFF) etc. | 15–40 K |
| Music and effects (PSG) | `wofsongs`/`songplay`; the 52 KB of PCM effects are not usable on PSG | 10–20 K |
| More code (enemy AI, missions, scoring, saves, menus, sound driver) | | 40–60 K |

## Verdict

| ROM | Fit |
| --- | --- |
| **256 KiB** | **No.** 21 segments are already used with one mission and no enemies; the remaining content is several times the 11 free segments. |
| **512 KiB** | **Probably**, with care: about 400–450 K needed if maps get a denser encoding. At today's map encoding it is about 480–520 K, which is too tight. |
| 1 MiB | Comfortable at today's encodings. |

ASCII8 addresses up to 256 segments (2 MiB), so growing the ROM is a
configuration change (`ROMSize` in `mission-flight.js`; the layout check
follows). The real constraint is the cartridge: commercial-style ASCII8
megaROM boards or flash carts in 512 KiB or 1 MiB sizes.

**Decision (2026-11-14):** plan for 512 KiB; 1 MiB is acceptable if the game finally needs it.
**Decision (2026-11-21):** 1 MiB for the complete campaign ([release-plan.md](release-plan.md)).
Measured that day with the converter (13 of the 15 maps; h and m do not
convert yet): one map's tiles and column map take 4–10 banks, about 85 in
all, more than the 64 of the upper half. The maps share most tiles (12,257
tiles, 2,462 different: 79 KB): a shared tile pool brings all maps to about
40 banks. Phase 3 of the release plan needs it.

**Recommendation:** plan for 512 KiB. Before adding missions, design a denser
map format (for example the original map words decoded at runtime, or
dictionary-coded columns). Keep 1 MiB as the fallback. Re-run this projection
after the first enemy set (P3) and after a second mission.

Resident space (window 0–2, 24 KiB) is a separate, tighter limit: 1.6 KB is
free. New code must go into banked segments, as `engine.c` and `landing.c`
already do.
