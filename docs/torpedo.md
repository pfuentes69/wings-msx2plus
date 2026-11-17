# The torpedo

Added 2026-11-17. Step 4 of the enemy ships ([ships.md](ships.md)). The
torpedo follows the Amiga executable, read by static disassembly; the
addresses are CODE-hunk offsets and A4-relative variables, as in
[research/amiga-ships.md](research/amiga-ships.md).

## What the player sees

- The torpedo can be chosen at the loadout and in service: 1 per sortie.
  The secondary button releases it, at any height, speed or heading.
- It drops from under the plane (tor2, tor7 facing left; the distant view's
  bumb) and keeps most of the plane's speed while it falls.
- It must meet the sea within 13 ticks: from level flight, release at
  altitude 41 or lower. From higher it hits the water too fast and
  explodes. On a deck or land it explodes like a bomb (on a deck it
  destroys a gun, as a rocket does).
- Otherwise it splashes in and runs at 4.3125 px a tick for 199 moves
  (about 858 px, 16 s). It is invisible while running; its wake of splashes
  shows where it is.
- The first column that is not sea stops it. On a hull: a boom, a red flash,
  and one hit off the ship's hits (destroyer 1, cruiser 1, battleship 2,
  Japanese carrier 3, the player's carrier 4). Sinking is step 5. On land it
  acts as a bomb. If it runs out, it vanishes without a sound.
- Each shell splash from a live ship gun destroys a torpedo within 10 px.
  The splashes fall at the plane's x ± 32, so a torpedo released near a
  defended ship usually dies under the plane: the manual's "disable the guns
  first". Any bomb, rocket or cannon burst destroys a torpedo in
  [x − 48, x + 16] too (0x1a8c). A destroyed torpedo explodes harmlessly
  and silently.

## The original

| Part | Address | What it does |
| --- | --- | --- |
| Release | 0x088e | Stock −1. x = plane x, altitude = plane altitude + 11, velocity = the plane's (vx × facing); +1f = facing (tor7 when negative). |
| Fall | 0x0b58 | vx −= trunc(whole vx / 10) whole pixels (divs.w); x += vx; vy −= 0.375; the altitude keeps no fraction (+6 is never written), so it moves by floor(vy). |
| Surface | 0x0bf0..0x0d32 | At 12 over the sea or land, deck + 11 over a deck (class 1). Splash sound over the sea, boom otherwise. Not sea, or vy's whole word < −5: explode (0x46dc, then 0x1a8c). Else vx = ±0x45000 by vx's sign, frame 10, life 200, and the run step follows in the same tick. |
| Run | 0x0d50 | Life −1; at 0 it is freed (no sound, a stray splash). x += vx; a non-sea column: 0x46dc with frame 10, boom and splash, the sea explosion. Else a splash (0x52b0) at x: the wake. |
| Hull hit | 0x4986, 0x49a6 | Running (frame 10): white then red, +c −1 while > 0; at 0 +18 = 20 (sinking). Not running: as a rocket, the first live gun within 16 px (0x49dc). On land, type 2 gets no flash. |
| Kill | 0x1ae2 | Every torpedo whose snapshot x (+8, copied each frame at 0x0fc0) is within r of x: state 8, no impact, no sound. Called with r = 10 by each shell splash (0x4efc) and as (x − 16, 32) by 0x1a8c. |
| Drawing | 0x0726 | Falling: 0x88 tor2 or 0x89 tor7, 8thscale shape 9 far off. Running (frame 10): nothing. |

## The port

- **`src/core/rockets.c`** (segment 29): `Torpedo_Launch`, the tick
  (`Torpedo`, run from `Rockets_Step` on the 12.5 Hz tick) and
  `Torpedo_Kill`, in the original's units (16.16 x and velocities, a whole
  altitude). `CombatState.torpedo`, last in the struct: the verification
  scripts read the fields before it by offset.
- **Bursts** go through the bombs' impact slots, marked in `vx`:
  `COMBAT_TORPEDO_BURST` (exploded where it fell), `COMBAT_TORPEDO_HIT` (a
  running strike), `COMBAT_TORPEDO_DUD` (destroyed: drawn only).
  `Island_Impacts` sends them to the huts and dugouts, `Ships_Rocket` (gun
  kill) or `Ships_Torpedo` (hull hit), and runs the 0x1a8c kill window for
  every other burst and cannon strike. `Sound_Bursts` plays the splash as it
  meets the sea, a boom for a strike (the original adds a splash; one effect
  plays at a time), nothing for a dud.
- **`src/core/ships.c`**: `Ships_Torpedo` and the hulls' hits left
  (`g_Ships.hull`, the player's carrier last). `Ships_Guns` now runs
  whenever splashes are alive or a torpedo is in the water, on every map:
  it ages the splashes, adds the wake, and each gun's shell splash calls
  `Torpedo_Kill` whether or not a splash slot was free.
- **The wake**: the original adds a 6-frame splash every tick (its pool
  holds 21). The port adds one each presented frame, spl4 down to spl1, in
  a pool of 6, of which shell splashes may take 4.
- **Drawing** (`src/msx/smoke_draw.c`): smoke-path frames 97 (tor2) and 98
  (tor7), from the atlas gaps the rockets use; no tile-cache slot was given
  up (113 pieces).
- The ships' bob is now set for every weapon, so bombs and the torpedo burst
  at an enemy deck's true height too.

## Verification

- `tests/test_torpedo.py`: the C against a model written from the 68000
  routines, tick for tick, over 300 random releases on map j (bursts, hull
  strikes, runs that end); the release envelope (41 runs, 42 explodes); 199
  moves and the first hull; hull hits per ship; the kill window; the wake and
  the guns destroying a torpedo.
- In the emulator (FS-A1WX, NTSC), map j: released at x 1402, altitude 33,
  it fell 7 ticks, ran 629 px in 12.1 s and struck the destroyer's stern
  (hull 1 → 0, boom, red flash). Released at x 820 over the bow guns, a shell
  splash destroyed it mid-fall. Map a: it ran 199 moves over open sea and
  vanished.
- The P0 smoke passes on NTSC and PAL. Its loadout step no longer refuses
  the torpedo. Its `pan_mid` band is now 14..32: the old 17..29 band (13 px)
  was narrower than one frame's descent and was stepped over on PAL.
