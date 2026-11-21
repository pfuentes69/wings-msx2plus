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
| Cheats | A cheat screen opened with F5 during the intro: infinite lives, ammo, fuel and oil; invulnerable; starting map; skip the intro (phase 2). F1 refill is removed then |

## Phase 0: SofaRun's memory-mapper mode (done 2026-11-21)

Diagnostic ROMs 1-3 ([diag-rom.md](diag-rom.md)) on the user's cartridge.
SofaRun's helpers use only F6EDh-F808h of page 3 (BASIC's work area). The
RAM it reserves below them (E6B0h-F37Fh) is free once the game runs: the
diag filled it with HALT around bank switches and they still worked. Two
fixes, both done before phase 1: the stack at F380h, not HIMEM (E6B0h
there); the five `LD (HL),A` switches turned into `LD (nnnn),A` (build
check in `tools/check_rom_layout.py`). The RAM target is then the same as
on any machine: variables and stack below F380h.

SofaRun copies the ROM into the cartridge's RAM, so a 1 MiB ROM needs a RAM
cartridge of more than 1 MiB; the user's 512 KiB one runs only the 512 KiB
builds (0.1.x).

## Phase 1: map runtime, 1 MiB, RAM

Status 2026-11-21: steps 1, 2, 4 and 5 done; 3 (loading at the briefing)
and the map choice remain. See [map-records.md](map-records.md).

1. **1 MiB ROM** (done, 0d934f5). Map data from bank 64.
2. **Map records** (done). `tools/build_maps.py` packs every converted map:
   its banks, a record with its tables (the surfaces, heights, island,
   ships, planes, cockpit features, palette, the carrier's x, the world's
   width), loaded into `g_Map` by `Map_Load`. The ROM build reads the
   per-map names from `g_Map`; the host tests keep one map's headers.
3. **Loading a mission.** `Map_Load(map)` runs once at boot today (the map
   `WINGS_MAP` names). Next: at the briefing (the original's 0x2adc), the
   map of the rank and mission, then the tile cache, column state, island,
   ships and plane lists rebuilt. The verifiers choose the map by writing
   the map number before the briefing.
4. **RAM** (done, 6df2d7a). The column table stays in ROM; a change list
   in RAM holds the columns that differ. Variables end at EF48h with
   records, stack at F380h.
5. **Bank switches** (done in phase 0).
6. **Check** (done for maps a and j from the same ROM: P0 NTSC and PAL and
   every verifier). SofaRun's memory-mapper mode can't hold a 1 MiB ROM on
   the user's 512 KiB cartridge.

Milestone: one 1 MiB ROM holding maps a and j.

## Phase 2: the cheat screen

The user asked for a key pressed during the intro that opens a screen of
cheats. Phase 3 needs it too: a starting map is the way to test each map.

- **Opening it:** F5 during the intro (title, credits or story), agreed
  2026-11-21. F1–F5 are already sampled by the interrupt. It goes to a new
  `GAME_CHEATS` state, and Return or Esc goes back to rank selection.
- **The screen:** the menu font (`msx/menu.c`), Up/Down to choose a line,
  Left/Right or fire to change it:
  - infinite lives (a crash keeps the plane count);
  - infinite ammo (guns, bombs, rockets and the torpedo aren't used up);
  - starting map a..o, shown as rank + mission. Maps not built yet are
    skipped;
  - infinite fuel and oil;
  - invulnerable (no hits from guns or planes);
  - skip the intro next time (until reset).
- **State:** a `g_Cheats` byte of flags, kept until the machine is reset.
  The briefing shows "CHEATS" when any cheat is on.
- **F1 refill goes away** once the screen works (the user, 2026-11-21):
  remove `ACTION_CHEAT_REFILL` and its key; infinite ammo replaces it.
- **Code:** banked (segment 27 has about 3.2 KB free, segment 49 about
  2.4 KB). `tests/test_game.py` covers the flags. smoke_lib gets a way to set
  the starting map without the screen.

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
  known to work, the F5 cheat screen, MSX-MUSIC optional), and a GitHub release only
  after asking the user.

Later, not for 1.0: saves and high scores (password or disk), the MSX2
(V9938) version.
