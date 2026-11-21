# Plan to the complete release (1.0)

Agreed 2026-11-21. The game today is one map per ROM, chosen when it is
built (`WINGS_MAP`). Map a (mission 1) is complete and runs on real
hardware (MegaFlashROM SCC+). Map j is the test bed for ships and fighters.
1.0 is the whole campaign: 15 maps, 7 ranks.

## Decisions

| Question | Decision |
|---|---|
| ROM size | **1 MiB** ASCII8 (128 banks) |
| Saves and high scores | **Dropped** for 1.0. `WINGS_HIGH_SCORES` stays off, and the load and save menus stay out of the ROM. Keep `MissionProgress` small and self-contained, so a password or a disk save could come back later |
| Order | Map runtime and RAM first, then the maps by rank (one new feature per step), then optimisation, then the game flow and tuning |
| Cheats | A cheat screen opened from the intro: infinite lives, infinite ammo, starting map (phase 2) |

## Phase 0: SofaRun's memory-mapper mode (waiting for the user's report)

Diagnostic ROM 2 ([diag-rom.md](diag-rom.md)) shows the bytes SofaRun puts
in place of `LD (nnnn),A` and where its helper code sits. From diag 1 we
already know: HIMEM is E6B0h; only `LD (nnnn),A` is patched; the 6000h and
A000h windows switch at no cost; the 8000h window can't be switched; and
C000h–E5A1h is free. The report decides phase 1's RAM target:
- **Helper small and at a known place:** keep the variables clear of it.
- **Helper uses all of E6B0h upward:** the variables have to end below
  about E4B0h. That leaves room for a stack below HIMEM, and means freeing
  about 2.8 KB.

## Phase 1: map runtime, 1 MiB, RAM

1. **1 MiB ROM.** `ROMSize = 1024` in `mission-flight.js`. Shared assets
   (code, aircraft, dashboard, screens, music) stay in banks 0–63; map data
   moves to banks 64+. Update `tools/check_rom_layout.py` and
   [rom-budget.md](rom-budget.md).
2. **Map table.** `tools/convert_mission.py` converts every map into its
   own banks and writes one table of map records. Each record holds: the
   banks of the tiles and the column map, the surfaces, island, heights,
   ships and planes tables, the carrier's x, the world's width, the reset x,
   and the briefing counts. The compile-time `WINGS_CARRIER_X`,
   `WINGS_WORLD_WIDTH`, `WINGS_WORLD_START` and the `map_<x>` include path
   become values read from the record.
   - Watch the step loop and the render: a constant that turns into a
     variable can cost time there (see [sdcc-pitfalls.md](sdcc-pitfalls.md)).
     Profile with `tools/profile_p0.py` before and after.
3. **Loading a mission.** `Mission_Load(map)` at the briefing (the
   original's 0x2adc): read the record, rebuild the tile cache, the column
   state, the island, the ships and the plane lists.
4. **RAM.** The column table holds only the columns that change (wrecked
   huts, as a list of changes over the ROM's column map), not 2 bytes for
   every column. Map o would need 6.9 KB the old way. Then reach phase 0's
   target. The biggest variables today are `g_TerrainCached` (2432 bytes),
   `g_TerrainMap` (2204), `g_DashboardTables` (801), `g_SmokeDrawn` (800)
   and `g_FMDriver` (700).
5. **Bank switches.** The five `LD (HL),A` switches (three in
   `Scenery_Read`, two in `Terrain_InitPage`) become `LD (nnnn),A`. Nothing
   switches the 8000h window after start-up; keep it that way (note it in
   [rom-banking.md](rom-banking.md)).
6. **Check.** Maps a and j from the same ROM: P0 and every verifier (the
   verifiers choose the map). Then SofaRun's memory-mapper mode on the
   user's cartridge.

Milestone: one 1 MiB ROM holding maps a and j.

## Phase 2: the cheat screen

The user asked for a key pressed during the intro that opens a screen of
cheats. Phase 3 needs it too: a starting map is the way to test each map.

- **Opening it:** a key during the intro (title, credits or story). The
  proposal is F5: F1–F5 are already sampled by the interrupt, and F1 is the
  refill cheat in flight. It goes to a new `GAME_CHEATS` state, and Return
  or Esc goes back to rank selection.
- **The screen:** the menu font (`msx/menu.c`), Up/Down to choose a line,
  Left/Right or fire to change it:
  - infinite lives (a crash keeps the plane count);
  - infinite ammo (guns, bombs, rockets and the torpedo aren't used up);
  - starting map a..o, shown as rank + mission. Maps not built yet are
    skipped;
  - to offer the user: infinite fuel and oil, invulnerable (no hits from
    guns or planes), skip the intro next time.
- **State:** a `g_Cheats` byte of flags, kept until the machine is reset.
  The briefing shows "CHEATS" when any cheat is on. F1 refill stays as it
  is.
- **Code:** banked (segment 27 has about 3.2 KB free, segment 49 about
  2.4 KB). `tests/test_game.py` covers the flags. smoke_lib gets a way to set
  the starting map without the screen.
- **To confirm with the user:** the key, and the extra cheats.

## Phase 3: the maps, by rank

Each map: convert, check its islands, targets and ships against the
original, write or extend a scripted check, play-test with the cheat screen.

| Step | Maps | New in the step |
|---|---|---|
| 3.1 | b | nothing new: proves a second ordinary map |
| 3.2 | c | **AA guns**: only rockets destroy them; damaged state; cockpit `pil*` art |
| 3.3 | d, e | **Airstrips** that launch fighters (0x1622, zones from 0x2c84) |
| | | Milestone: **ranks 1–2 (maps a–e) playable in one ROM** |
| 3.4 | f, g | **Cruiser** (side-on `cruiseship.shp`, its fighters; cockpit `cl*`/`cr*`) |
| 3.5 | h, i | h: the surface lookup grows past its limits. Destroyer and airstrip together |
| 3.6 | j, k, l | battleships and destroyers with airstrips; up to 13 fighters |
| 3.7 | m | **Japanese carrier** (deck roll 0x1510, `3dc*` art); surface lookup limits again |
| 3.8 | n, o | the heaviest maps (o: 20 fighters) |

Research before the step that needs it:
- **night missions:** which maps load `nightdash.shp` (table `-$56f6`,
  0x6540) and their palettes;
- the cruiser's and the Japanese carrier's behaviour, if
  [research/amiga-ships.md](research/amiga-ships.md) doesn't cover them;
- AA gun fire and damage ([research/amiga-island-combat.md](research/amiga-island-combat.md)).

## Phase 4: speed on the late maps

Profile maps l–o. Candidates already found: decoding terrain columns during
the pan's page move, a VDP command queue so the CPU and VDP work in
parallel, and the rest of the smoke path ([frame-budget.md](frame-budget.md)).

## Phase 5: the game flow

- the victory ceremony on promotion; the end of the campaign after rank 7;
- the short black-out before the next plane; "THE END" over the burning
  last wreck;
- intro fades; the credits wording ("Programming" vs "Development") and
  their order.

## Phase 6: tuning, testing, release

- difficulty and balance from play-testing every map; music tuned by ear;
- the suite: P0 and the per-map checks, on NTSC and PAL;
- real hardware: MegaFlashROM SCC+, SofaRun's memory-mapper mode if
  phase 1 made it work, an FS-A1WX or another MSX2+;
- `tools/package_release.py` 1.0: README (1 MiB ASCII8, the cartridges
  known to work, the cheats, MSX-MUSIC optional), and a GitHub release only
  after asking the user.

Later, not for 1.0: saves and high scores (password or disk), the MSX2
(V9938) version.
