# Rockets

Added 2026-11-17. The second step of the enemy ships
([research/amiga-ships.md](research/amiga-ships.md)). Rockets follow the
Amiga executable, recovered by static disassembly; the addresses below are
CODE-hunk offsets and A4-relative variables, as in the research notes.

## What the player sees

- Rockets can be chosen at the loadout and in service: 15 of them. Held, the
  secondary button fires them at the bombs' rate (4 a second, the user's
  observed rate, [combat-prototype.md](combat-prototype.md)). The torpedo is
  in [torpedo.md](torpedo.md).
- A rocket leaves level with the plane (its altitude + 11, drawn 11 px
  lower) and falls back from it, unlit,
  for 4, 8 or 12 ticks (8 twice as likely). Then it lights and accelerates
  along the plane's flight path at that moment.
- Fired in a dive steeper than about 15°, a rocket that lights with a ship
  gun on the sea below re-aims at it.
- It bursts 12 px above the sea or an island, or 11 above a deck. A burst on
  land flashes the sky white, or red when it wrecked a hut or struck a
  dugout. Over the sea or a deck it flashes only near a hull: white, red
  when it destroyed a gun (+200, the gun smokes 49 puffs).
- Huts, dugouts and soldiers react to a rocket as to a bomb. Bombs and the
  cannon do nothing to ships.

## The original

| Part | Address | What it does |
| --- | --- | --- |
| Launch | 0x088e, 0x08fe | Stock −1. Position, velocity: the plane's x, altitude + 11, its horizontal step × facing and vertical step. Angle a (+$26) = `-$5bfa` / 2, where `-$5bfa` = flight path (`-$555c`, hundredths of a degree) × 1024 / 18000. Speed (+$28) = airspeed (`-$5bea`). Acceleration: ax = ±2 cos a, ay = 2 sin a in 16.16 (Q15 sine), ax with the sign of vx. Ignition delay +$24: random 4, 8 or 12 (0 becomes 8). Frame: clamp(4 − (`-$5bfa` >> 5), 0..9), + 10 when vx < 0. |
| Tick | 0x0aa6 | Before ignition: x −= the plane's facing (1 px), altitude −= 1; x += vx. At ignition: aim (0x099a), then as lit. Lit: vy += ay, vx += ax, x += vx. Removed when more than 1280 px from the plane (5760 in the distant view). Altitude (a whole word; no fraction is kept) += floor(vy + ay). |
| Burst | 0x0bf0 | At or below altitude 12 over the sea or land, deck + 11 over a ship column (0x5714: +e − sink − bob). Sound: splash on the sea, boom otherwise. Then the impact handler 0x46dc and the soldiers within 16 px (0x1a8c). In an airstrip zone a rocket vanishes at altitude 30 (no such zone on maps a and j). |
| Aim | 0x099a | Only when a / 2 < 0 (down). The sea points (0x1a46) of a / 2, a / 2 + 20 and a / 2 − 20, from the plane's x and altitude: x ± altitude × 256 / tan (Q8 table, divu.w). The first ship gun, live or not, between the first and second points, else the first and third (0x11a6, ships with a bonus); else the islands' live AA guns (0x115c). Then the angle to it, atan2(altitude, \|dx\|) (0x5ca6), downward, at speed airspeed / 100: vx = cos × speed (sign of vx kept), vy = sin × speed. The launch acceleration stays. |
| Impact | 0x46dc, 0x4986, 0x49dc | Land: white flash (`-$5be8` = 5, `-$5be6` = 0xfff); a hut, a dugout or an AA gun found turns it red (0xf00). Sea or deck: the hull under x (0x4a4e, the player's carrier last); for a rocket, white, then the first live gun within 16 px is destroyed: +200, red. |
| Flash | 0x031a | Each drawn frame the counter drops; on odd counts (5, 3, 1) the background colour is the flash. |
| Drawing | 0x0702 | torpedo.shp `ro01..ro14` (shape 0x74 + frame) before ignition, `rc01..rc14` (0x4c + frame, with the flame) lit; 8thscale `bumb` (shape 9) in the distant view. Ordnance is drawn 11 px below its altitude (0x5174). |

The sine (`-$6692`), tangent (`-$6892`) and arctangent (`-$5810`) tables are
copied out of the executable by `tools/convert_rockets.py` into
`src/generated/rocket_tables.h`, which checks the code that reads them.

## The port

- **`src/core/rockets.c`** (segment 29): launch, tick, aim and burst, in the
  original's units: x and velocities 16.16, altitude a whole word, on the
  original's 12.5 Hz tick (every second weapon tick). Up to 15 in flight
  (`CombatState.rocket`).
- **`src/core/combat.c`**: the launch on the secondary button, the 12.5 Hz
  step, and the burst height shared with bombs. Bombs over an enemy ship
  now burst at its deck too.
- **`src/core/ships.c`** (segment 28): the map's ships from the converter
  (`mission_ships.h`: hull range, deck, hits, bonus, guns), the hull test
  0x4a4e, the gun kill 0x49dc, the aim's target search 0x11a6 and the
  destroyed guns' smoke. Guns are not drawn and do not fire yet (next step).
- **`src/core/island.c`**: `Island_Impacts` sends rocket bursts (marked
  `COMBAT_ROCKET_BURST` in the impact slot's vx) to the huts and dugouts or
  the ships, and starts the flash.
- **Drawing** (`src/msx/smoke_draw.c`): rockets are smoke-path frames 46..86,
  drawn after the puffs and erased by the tile repaint, so they need no VRAM
  backup. Their 59 atlas pieces sit in the static-tile cells the tile cache
  freed ([tile-cache.md](tile-cache.md)): one piece each.
- **Open sea past the map** (2026-11-17, user report): the plane flies up
  to 16,000 px past either end of the map, but every weapon was off
  outside it (on map a just right of the carrier). Projectile x is now a
  16-bit ring of quarter pixels (16,384 px) read relative to the plane
  (`Combat_WorldX`); past the ends the shots, bombs and rockets meet the
  open sea.
- **Flash** (`src/world_flight.c`, `SkyFlash`): set at publication, in
  VBlank, by writing palette colour 0 (the sky; the dashboard does not use
  it and the line interrupts never write it): white 777, red 700.
- **Speed:** SDCC's long arithmetic through the rocket pointer cost about
  5,000 T-states a rocket a tick. `src/core/rocket_move.c` does the tick's
  motion in Z80 (`Rocket_Move`, at most 1,109 T-states) and the aim's two
  divisions (`Rocket_Divide`, 68000 `divu.w`, at most 1,654), each with a C
  reference that `tests/test_rocket_move_z80.py` checks on an emulated Z80.
  16.16 values are a union with their whole word (`CombatFixed`), so no
  long shift is left. Rockets in flight also get the bombs' 2 extra
  VBlanks per frame.
- **Banking:** the rocket code has its own segment (29); the terrain patch
  moved from 23 to 30 and the sound's game side from 22 to 26 to make room.
  The aim still links SDCC's 32-bit multiply into resident code (with its
  divide, 502 bytes).

Differences from the original:
- the islands' AA guns are not targets yet (maps a and j have none), nor are
  airstrip zones;
- the US carrier's deck is 33 for bursts, without its bob, as for bombs;
- a rocket's launch velocity comes from the port's flight velocity, rounded
  to the original's whole-pixel steps.

## Cost

Measured on map j's release ROM (FS-A1WX, NTSC), a salvo of 7 rockets
fired low at the destroyer: `Rockets_Step` 2.9 ms a call on average
(5.4 at most, with 6 in flight), the aim 2.2 ms a rocket. Drawing and
erasing them in the smoke path adds 5–25 ms a frame, the bursts more.
Low over the ship such a salvo misses 2 or 3 frame deadlines (frames of
up to 250 ms against 200): a short stutter, as a bomb salvo does
(`verify_world_flight --weapons`, bomb_salvo). The same flight without
firing misses none. Next candidates: fewer atlas pieces per rocket frame
(most are split in 2 or 3) and cheaper erases near the sea.

## Verification

- `tests/test_rockets.py` runs the C against a model written from the 68000
  routines, tick for tick: 300 random flights (both facings, turns, both
  views) and aimed dives over map j's destroyer; the gun kill, the aim's
  target search and the gun smoke.
- `tests/test_rocket_move_z80.py`: the Z80 move and divide against their
  C references.
- `tools/convert_rockets.py --check` keeps the tables current.
- In the emulator (map j release ROM, a scripted dive and a low pass over
  the destroyer): rockets drawn unlit and lit in both views, re-aimed at
  ignition, bursting at the sea and the deck; two guns destroyed (+400),
  the sky flashing white and red.
- The P0 smoke (map a) passes on NTSC and PAL; its loadout and service
  steps no longer confirm rockets (they are playable).
