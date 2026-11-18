# Enemy planes

The fighters and torpedo planes of the doc's P5 (requirements WPN-01,
DEF-01/02/03, OBJ-03, HUD-07). The original's behaviour comes from
[research/amiga-enemy-planes.md](research/amiga-enemy-planes.md). Its
"Pseudo-code (for the port)" section is what the C follows.

| Step | Contents | State |
| --- | --- | --- |
| 1 | The plane core: 4 slots, spawning, speed, motion, turns, the shape index, drawing in both views; the torpedo-plane timer and the torpedo plane's flight (cruise, descent, the drop's state change, turns) | Done |
| 2 | The torpedo attack: the enemy torpedo (the player's torpedo code in a second slot), hits on the US carrier (4), its sinking and the game over, the pilot-window arrow, the player's weapons destroying the torpedo | |
| 3 | Shooting planes: the gun's hit test, 19 hits, +350, fall, crash, wreck, the kill counter and icons on the dashboard. Then map a is the original's first mission, with a scripted check | |
| 4 | Fighters: the AI (0xd9c6), the attack and its hit-scan fire (0xdccc, 0xde52), the muzzle flash, launches from ships (map j) and airstrips, the sounds | |
| 5 | Scripted verification of the fighters on map j | |

Map a, the original's first mission, has no fighters. A torpedo plane
attacks the carrier on every map, so steps 1 to 3 complete map a.

## The core (step 1)

**`src/core/planes.c`** (segment 31) runs once per original tick (the
world loop's 12-step tick). It holds the record of 0xe4d0 / 0xe7d6 field
for field (`Plane`, `src/core/planes.h`), in the original's units and word
arithmetic:

- the torpedo-plane timer (0xbc02):
  - 1350 ticks from each new plane (`Planes_NewPlane`, from `NewPlane`);
  - 500 after a drop;
  - held at 750 or more while the player fires, and it does not count
    down on those ticks;
  - at 0 a torpedo plane starts 6144 px from the player, on the side
    away from the carrier;
- the relation to the player and the rank (0xd3b4, 0xd476);
- the speed step (0xe64e: it settles at the target + 10), motion with the
  player's turn-factor table (0xd796), and turns of 25 frame steps of 3
  ticks with the flip at 14 (0xd562 / 0xd530, including the fighters'
  cut-short and reversal branches);
- the armed torpedo plane (0xdea4):
  - it cruises at 50;
  - it goes down to 20 within 1000 px of the carrier's near end, and
    drops at 20;
  - it turns back 500 px past the carrier, or when its overshoot timer
    runs out;
- after the drop it climbs to 60 at 1300 and is freed beyond 2600 px. Its
  chased behaviour (picking altitudes 25..95) is inferred.

The random source is the port's xorshift. The original's is the beam
position, which is equally uniform. `tests/test_planes.py` runs the C
against a model written from the pseudo-code. It covers:
- 150 random runs of 200 ticks, all fields compared;
- the level step at 900 (9, 8, 8, 8, 7, ... trunc(factor × 9));
- a 75-tick turn;
- the speed's settling;
- the timer's rules;
- a drop between 1000 px and the carrier's near end.

## Drawing

Enemy planes go through the smoke path (`src/msx/smoke_draw.c`), drawn 7 px
above their altitude as in 0x0e1a. The shape index (0..55) picks the view
by the original's tables (0xd1ea).

- **Close view: streamed frames.** japplane.shp's 16 turn views and the
  torpedo plane's and the wreck's two each (`jp10..jp1f`, `jt10/jt1a`,
  `jc10/jc1a`, up to 48 × 26) are too big for the atlas. They stay in ROM
  (aircraft banks; `g_PlaneFrames`). Each one drawn is copied into one of 4
  **frame slots** of 48 × 26 (page 3, x 64..159, rows 180..231) and drawn from
  there. Planes showing the same frame share a slot. A slot not used yet
  on this page takes a missing frame (`Atlas_LoadShape`, after the running
  VDP command). With no slot left, the plane is skipped for that frame.
- **Distant view:** 8thscale `zpn*` frames, and the muzzle flashes
  `fc10/fd10/fc1a/fd1a` (step 4), sit in the atlas like the rockets.
- The original draws enemy planes over the player. Here they are drawn
  with the smoke path, behind it.

## What it cost

- **VRAM:** the tile cache went from 52 to 40 slots
  (`TERRAIN_SLOTS`, [tile-cache.md](tile-cache.md)). The 12 slots freed
  hold the 4 frame slots and the leftover cells. A view may need at most
  `TERRAIN_SLOTS - TERRAIN_CHURN` = 32 strips: map j's worst is 32, the
  island maps' 25..26.
- **ROM:** aircraft data passed 32 KiB (39 KiB). Segments past bank 14 go
  to the free banks 4, 5 and 6 (`AIRCRAFT_BANKS` in
  `tools/convert_hellcat.py`, `mission-flight.js` and `s_AircraftBank` in
  `world_flight.c`). Bank 15 is the elevator.
- **Code:** segment 31 holds the planes and, moved from 22 for room, the
  engine smoke (`core/smoke.c`). Segment 22 keeps the smoke path's drawing
  and tables.

## Verification (step 1)

- `tests/test_planes.py` (above) and the whole unit suite pass.
- In the emulator (map j, a scratch scenario): a torpedo plane spawned by the
  timer, moved near the player, went down to 20 inside 1000 px of the
  carrier, dropped (state change only) and climbed away to 60 at 1310.
  `jt10` drew level with the sea at the right height.
- The P0 smoke passes on NTSC and PAL, and the ships gate on map j (NTSC).
  - On NTSC the island's bomb-burst frame (the hut wrecked: render
    about 105 ms, plus about 75 ms of sim) falls on either side of a VBlank
    from run to run. HEAD finished 2 ms past the 10th and was not
    counted. The P0 smoke now allows that one miss, between the release
    and the turn back, and logs it (`tolerated_miss`). It belongs to the
    optimisation pass.
  - A torpedo plane may come late in a P0 run (108 s after a new plane).
    The P0's pixel model does not know planes. It stayed off screen in
    every snapshot.

