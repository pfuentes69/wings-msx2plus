# Amiga enemy aircraft: executable findings

Recovered 2026-11-18 by static 68000 disassembly (Capstone) of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-ships.md](amiga-ships.md) and
[amiga-island-combat.md](amiga-island-combat.md): code addresses are
CODE-hunk offsets, variables A4-relative, a tick is one 12.5 Hz logic tick,
fixed point is 16.16, and "map offset" is a byte offset into the map words
(column × 2; px = offset × 4). Speeds are in the player's units
(hundredths of a px per tick, see [amiga-fuel-oil.md](amiga-fuel-oil.md)).
`rand(n)` is 0xcac8: (random & 0xffff) mod n, so 0..n−1. Nothing was observed
running on an Amiga. Each claim is marked **confirmed** (read directly from
the code or data) or **inferred** (a reading of what the code implies).

Timing: enemy plane AI and motion (0xe7d6), the player's gun hit test
(0xb682), the torpedo-plane timer (0xbc02, inside the flight handler 0xc660),
ship launches (0x1574/0x1510) and airstrip launches (0x1622) run in the logic
tick (0x1386). Drawing (0x0da6, called from 0x38c6), the pilot-window view
(0x4206) and the dashboard arrow and kill counter (0xee16 → 0xf21a, 0xf178)
run in the render loop.

## Summary

- There are two kinds of enemy plane, both made by 0xe4d0: the **fighter**
  (kind 0, a Zero, `jp` shapes) and the **torpedo plane** (kind 1, `jt`
  shapes while it still carries the torpedo). No other kind exists. All
  live in one array of **4 records of 52 bytes** at `-$5dd4`.
- **Fighters** come from enemy ships (while the player is near a ship) and
  from **airstrips** on islands (map ids 0x114/0x115, when the player is
  within 480 px). The counts and the most airborne at once come from
  per-map tables. Maps a, b and c have no fighters. Map o has up to 20.
  Fighters never despawn: they stay until shot down.
- **Torpedo planes** come from a timer on every map while the US carrier
  is afloat. The timer is 1350 ticks (108 s) from each new plane on the deck,
  500 ticks (40 s) after a torpedo drop. On any tick with fire input it
  does not count down, and it is raised to 750 ticks (60 s) if lower. A torpedo plane starts 6144 px
  from the player, toward the carrier, at altitude 50. Only one carrying a
  torpedo can exist at a time.
- Fighters chase at up to 26 px/tick (the player flies at 10..14). The nearest
  one on the player's tail holds 130 px behind at the player's altitude and
  fires. Enemy fire is hit-scan: it hurts only on exactly the same altitude,
  within 160 px, on every other tick. Each hit takes 1 off the hit counter.
  When the counter runs out the oil drops by 8 and the fuel by 0..31.
- Player's gun: a plane must be ahead of the player, flying the same way,
  within 160 px and 20 px of altitude, with the player's commanded climb at
  exactly 0. One "hit" every 5..9 ticks of fire. **19 hits** kill (health
  240, −8 per hit, dead below 96): about 140 ticks (11 s) of fire on
  target. **+350 points** at the kill. The kill counter goes up when the
  wreck comes to rest. Rockets, bombs and torpedoes never hit planes. There is
  no collision between the player and an enemy plane.
- The torpedo plane descends to altitude 20 within 1000 px of the carrier.
  It drops when it reaches 20 while still short of the deck. The torpedo is
  the player's own torpedo code in the extra slot `-$5a6a`: it runs at
  4.3125 px/tick and takes one of the carrier's 4 hull points. At 0 the
  carrier sinks, and the game ends at the next new plane. Any bomb or
  rocket burst, or gun strike on the sea, within the 0x1ae2 window
  destroys the torpedo.
- While a torpedo plane still carries its torpedo, the dashboard shows an
  arrow at the top centre of the pilot window: `ltar` if the plane is to
  the left (or level), `rtar` if it is to the right.

## Spawning: 0xe4d0(kind, x, altitude, direction)

The routine scans the 4 slots and keeps the **last free one** (`+0` = 0).
It refuses kind ≠ 0 while any active record has behaviour bit 2 (an armed
torpedo plane, behaviour 4 or 12). Kind 0 is always accepted while a slot is
free. **Confirmed.**

| Field set at spawn | Value | Confidence |
| --- | --- | --- |
| +0 state | 2 (flying) | confirmed |
| +14 facing | direction argument (−1 left, +1 right) | confirmed |
| +20 x | x argument | confirmed |
| +24 target altitude | 50 | confirmed |
| +1c speed, +1e target speed | 900 (`-$50ac`, the minimum) | confirmed |
| +8 health | 240 | confirmed |
| +a hit sub-counter | 5 + rand(3) = 5..7 | confirmed |
| +4, +6, +c, +16, +18 | 0 | confirmed |
| Kind 0 | +2 = 1 (fighter), +26 altitude = altitude argument, airborne count `-$5e28` + 1 | confirmed |
| Kind 1 | +2 = 4 (torpedo plane), +26 altitude = 50 (the argument is ignored); **not counted** in `-$5e28` | confirmed |
| Not reset | +10, +12, +1a, +22, +2c, +32 keep the slot's last values (cleared only at a new game, 0xe608) | confirmed |

### Callers

| Caller | Source | Kind | Position and direction | Condition | Confidence |
| --- | --- | --- | --- | --- | --- |
| 0x1574 | Enemy ship plane list | 0 | the parked entry's (x, altitude), direction −1 | shared cooldown `-$3cb6` = 0, ship afloat, player x in the ship's window, `-$5e28` < list max, planes left. Cooldown 100. See [amiga-ships.md](amiga-ships.md) | confirmed |
| 0x1510 | Japanese carrier deck roll | 0 | x when it passes the bow, altitude 33, −1 | after the roll (ships note) | confirmed |
| 0x1622 | Airstrip zone `-$5d04` | 0 | the zone's end, altitude **0**, the zone's direction | after a take-off roll, below | confirmed |
| 0xbca4 | Torpedo-plane timer | 1 | player x − 6144, direction +1 | timer reaches 0, player left of the carrier | confirmed |
| 0xbcc4 | Torpedo-plane timer | 1 | player x + 6144, direction −1 | player right of the carrier | confirmed |

Over the carrier (between `-$5c02` and `-$5c00`, the landing range) the side
is random (bit 15 of 0x103be). **Confirmed.**

### Airstrips (`-$5d04`, 4 zones of 20 bytes; built by 0x2c84)

A zone runs between two markers in the map, ids 0x114 and 0x115. The first
marker gives +0 (start x in px), the second gives +2 (end x). The second
marker's id sets the direction: 0x114 west (−1), 0x115 east (+1). Per-map
bytes `-$7b0a`[map × 4]: (count, max) for zone 0, then zone 1. **Confirmed.**

| Offset | Field |
| --- | --- |
| +0 / +2 | start / end x, px |
| +4 | most airborne (compared with the global `-$5e28`) |
| +6 | planes parked |
| +8 | x of the plane rolling for take-off (0 = none) |
| +c | roll speed × 8 (0..56) |
| +e | direction |
| +10 / +12 | render copies of +6 / +8 (0x100c) |

- **Start (0x169a):** when the cooldown `-$3cb6` is 0, the player's x is in
  [start − 480, end + 480], `-$5e28` < +4 and +6 > 0: +6 − 1, cooldown 100,
  and a plane starts rolling at end − 32 − 64 × +6 (west) or
  start + 32 + 64 × +6 (east), from its parking place. **Confirmed.**
- **Roll (0x1628, every tick):** +c = min(+c + 1, 56); x moves +c >> 3 px
  (up to 7 px/tick). Past the far end it takes off as a fighter at altitude
  0 (0xe4d0 kind 0). **Confirmed.**
- **Drawing (0x3a18):** the +10 parked planes, `jp21` (west) or `jp22`
  (east), 64 px apart from end − 32 / start + 32, at altitude 0, and the
  rolling plane. Far view: 8thscale shapes from `-$4188`. **Confirmed.**

### Fighters and airstrips per map

Ship lists are from [amiga-ships.md](amiga-ships.md) (count / most airborne
at once). Airstrips from `-$7b0a` and the map words. **Confirmed.**

| Map | Ship fighters | Airstrip (x, direction: count / max) | Fighters in total |
| --- | --- | --- | --- |
| a, b, c | none | none | 0 |
| d | none | 3200..3544 W: 2 / 1 | 2 |
| e | none | 15664..16008 W: 3 / 1 | 3 |
| f | cruiser 2 / 1 | none | 2 |
| g | cruiser 3 / 1 | none | 3 |
| h | destroyer 3 / 1 | 6624..6968 E: 3 / 1 | 6 |
| i | destroyer 4 / 1; cruiser 2 / 1 | 3120..3464 W: 2 / 1 | 8 |
| j | destroyer 4 / 2; battleship 6 / 2 (one is the "ghost", below) | none | 10 |
| k | battleship 5 / 2 | 19752..20096 W: 3 / 1 | 8 |
| l | battleship 4 / 2; destroyer 3 / 2 | 5832..6176 W: 3 / 2; 19448..19792 W: 3 / 2 | 13 |
| m | battleship 5 / 2; carrier 6 / 3 | 3368..3712 E: 3 / 2; 5192..5536 W: 3 / 1 | 17 |
| n | battleship 5 / 3; destroyer 4 / 2 | 23000..23344 W: 4 / 1 | 13 |
| o | carrier 7 / 3; battleship 5 / 2; destroyer 4 / 2 | 3672..4016 E: 4 / 2 | 20 |

- The "max" values are all compared with one global count, so the real limit
  is the largest max among the sources the player is near. 4 slots are the
  hard cap, shared with torpedo planes. **Confirmed.**
- Torpedo planes come on **every** map (a..o) while the US carrier is
  afloat. **Confirmed** (no per-map table; condition below).
- No other parameter changes with rank or mission: the speed limits
  (`-$50ac` 900, `-$50aa` 2600) and the timers are constants. Difficulty is
  in the maps alone. **Confirmed** (no writes found).
- Shooting fighters is not part of any mission objective: the kill counter
  is only read by the dashboard. This is the manual's OBJ-03. **Confirmed.**

### Torpedo-plane timer `-$5f6a` (0xbc02, every tick in every player mode)

| Event | Effect | Confidence |
| --- | --- | --- |
| New plane on deck (0xb89a, in 0xb7ec) | timer = 1350 (108 s) | confirmed |
| Torpedo dropped (0xe14e) | timer = 500 (40 s) | confirmed |
| Fire input (`-$42bc` bits 4/5: gun held or weapon tap) | no count-down that tick; if 0 < timer < 750, timer = 750 | confirmed |
| Each tick, if the timer ≠ 0, the US carrier is present (`-$5b22`) and its hull `-$5b1a` > 0 | timer − 1; at 0, spawn kind 1 | confirmed |
| Spawn guard | only when \|32767 − player x\| > 6656, that is player x < 26111 (keeps x + 6144 within a signed word) | confirmed code; purpose inferred |

If the spawn is refused (guard, no free slot, or an armed torpedo plane
already flying) the timer stays at 0 and no torpedo plane comes until the
next drop or new plane. Shooting the torpedo plane down does not restart the
timer. **Confirmed.**

At 9 px/tick a plane 6144 px away needs about 680 ticks (55 s) to reach the
player's position, so the first attack arrives roughly 2.5 to 3 minutes after
leaving the deck. **Inferred** (arithmetic).

## The enemy plane record (52 bytes, 4 slots at `-$5dd4`)

| Offset | Field | Confidence |
| --- | --- | --- |
| +0.w | State: 0 free, 2 flying, 4 shot down (falling and sliding), 16 burning wreck on an island. 1 and 8 have empty handlers (0xe4c8, none) | confirmed |
| +2.w | Behaviour: 1 fighter, 2 fighter attacking, 4 torpedo plane armed, 16 torpedo plane after the drop; **+8** is the "turning" flag; 0 for a wreck | confirmed |
| +4.w | Relation to the player (0xd3b4, every tick): 1 same heading, the plane behind the player; 3 same heading, the plane ahead (the player on its tail); 2 opposite heading, plane to the right; 4 opposite heading, plane to the left | confirmed |
| +6.w | Hit flag, set by the player's gun (0xb6fe), cleared by the AI | confirmed |
| +8.w | Health, 240; −8 per hit; shot down below 96 | confirmed |
| +a.w | Gun hits until the next health loss (5..7, then 6..9) | confirmed |
| +c.w | Rank among planes with +4 = 1, by distance (1 = nearest), 0xd476 | confirmed |
| +10.w | Flee timer: 550 when the player gets on its tail (+4 = 3), or after a hit; 275 for a hit torpedo plane | confirmed |
| +12.w | Firing (muzzle flash and gun sound) | confirmed |
| +14.w | Facing, −1 / +1 | confirmed |
| +16.w | Turn frame 0..25 | confirmed |
| +18.w | Countdown to the next turn (sets +2 bit 3 at 0) | confirmed |
| +1a.w | Turn reversals in a row | confirmed |
| +1c.w | Speed (900..2600) | confirmed |
| +1e.w | Target speed | confirmed |
| +20.w | x, px | confirmed |
| +22.w | Vertical speed while falling, 1/100 px, −10 per tick | confirmed |
| +24.w | Target altitude | confirmed |
| +26.w | Altitude | confirmed |
| +28.w | \|dx\| to the player (the torpedo plane overwrites it, 0xdf06) | confirmed |
| +2c.w | Draw counter (muzzle flash phase) | confirmed |
| +2e.w | Render copy: x / 8 × 2, a map offset, for the pilot window (0x0ff2) | confirmed |
| +30.w | Shape index into `-$4070` / `-$3f90` / `-$3ba2` (0xd35a) | confirmed |
| +32.w | Turn sub-step counter | confirmed |

Other enemy-plane globals: `-$5e28` fighters airborne, `-$3cb6` shared
launch cooldown, `-$5f6a` torpedo-plane timer, `-$5c7f` kills (byte),
`-$5e24` / `-$5e26` island wreck list (40 words of x × facing, and its
count), `-$3198` per-tick counter used to space fleeing fighters.
**Confirmed.**

## Update loop (0xe7d6, every tick, slots 0..3)

For each slot with +0 ≠ 0, in order. **Confirmed.**

1. 0xd3b4: relation +4, distance +28 (and +10 = 550 when +4 becomes 3 with
   +10 = 0).
2. 0xd476: ranks +c.
3. By state: 2 → 0xe728 (damage smoke, then the behaviour below; fighters
   keep +24 ≥ 33); 4 → 0xe244 (shot down); 16 → 0xe3e8 (wreck).
4. 0xe64e: speed toward the target (state 2 only). The target is clamped to
   900..2600. Below it: speed += (target − speed) / 2 + 5. Above it: speed
   −= (speed − target) / 2 − 5. The speed is clamped to the same range.
5. 0xd796: motion (all states except 16).
6. 0xd35a: shape index.

### Motion (0xd796)

| Part | Rule | Confidence |
| --- | --- | --- |
| x | x += fix(turn[+16] × trunc(+1c / 100) × facing). turn[] is the player's turn-factor table `-$54f2` (1.0 at frame 0, 0 at frame 14). So 9..26 px/tick in level flight | confirmed |
| Altitude | Step toward +24 by `-$4e06`[min(\|+24 − +26\|, 100) / 20] + rand(2): 1, 2, 2, 3, 4, 5 px, plus 0..1. So 1..2 px/tick when within 20 px, 5..6 when 100 or more away. No pitch: the plane is always drawn level | confirmed |
| Falling (state 4) | also +26 += +22 / 100 and +22 −= 10 while above the target | confirmed |
| Fighter floor | +24 ≥ 33 for anything but a torpedo plane; +24 = 70 while the player is on deck (mode 1) | confirmed |
| Player down | When the player's mode is 4, 6 or 8 (engine out, sinking, crashed): +1e = 1700. The AI rewrites +1e every tick before the speed step, so this has little effect | confirmed; effect inferred |
| Turn timer | +18 counts down; at 0 the turn flag (+2 bit 3) is set | confirmed |
| Terrain | No terrain or ship test: fighters fly through anything above altitude 33 | confirmed (absence) |

### Turns (0xd562, 0xd530)

A turn uses the player's 26-frame sequence, one frame every 3 ticks (+32).
On reaching frame 14 the heading flips and the frame moves on to 15 in the
same tick, so frame 14 is never drawn. A whole turn is 25 steps, 75 ticks
(6 s). See the pseudo-code below. **Confirmed.**

- Fighters (behaviour bit 0 or 1) set their target altitude to the
  player's during a turn (player flying). **Confirmed.**
- **Cut short:** when the player is flying and not turning, at frame ≥ 19
  with +4 = 1 or 3, the turn ends at once (frame 0). **Confirmed.**
- **Reversal at frame 20** (fighters, player flying): unless cut short, the
  frame becomes 26 − 20 = 6. The plane then flips back at 14, so it returns
  to its old heading. This follows a player who is turning:
  - +4 = 1: always. If the player is in turn frames 1..5, +18 = \|dx\| × 100 /
    speed.
  - +4 = 2: only if the player is in turn frames 1..5.
  - +4 = 3: always.
  - +4 = 4: always, with +18 = \|dx\| × 100 / (speed + player speed).

  +1a counts reversals. At 3 it is cleared and no reversal happens on that
  tick. But the frame stays 20 for two more ticks, and the test runs again
  with +1a = 0, so the limit at most delays a reversal. The +10 = 550 written
  there is cleared the next tick by 0xd530. **Confirmed**; the purpose is
  **inferred**.
- 0xaa6e: the **player's** turn frame does not advance while any fighter
  in state 2, behaviour 1, +4 = 3 is at its own turn frame 13. This was the
  unidentified object in amiga-fuel-oil.md. **Confirmed**; it probably keeps
  the two flips from coinciding (**inferred**).

### Fighter AI, behaviour 1 (0xd9c6, by relation +4)

| +4 | Situation | Action | Confidence |
| --- | --- | --- | --- |
| 1 | On the player's tail, \|dx\| < 160 | If the player is in turn frames 1..5 (not on deck) and +18 = 0: +18 = \|dx\| × 100 / speed + 2 × rank, so it turns where the player turned. Otherwise, if rank 1 and +18 = 0: behaviour **2 (attack)**. Otherwise: +12 = 0, target altitude = the player's, target speed = player speed − 70 × rank | confirmed |
| 1 | \|dx\| ≥ 160, not turning | target speed = \|dx\| + player speed, then + 80 for rank 1 or − 80 × rank for the others: it closes fast, up to 2600 | confirmed |
| 2 | Opposite heading, plane to the right | If the player is flying in turn frames 1..10: target speed 900 (wait). Otherwise turn now | confirmed |
| 3 | The player on its tail, \|dx\| < 1536 | +10 − 1. Turn (and +10 = 0) when +10 runs out, when the player starts a turn (frames 1..5), or when the player is on deck. If hit (+6): +6 = 0, +18 = 8 + rand(6) if 0, +10 = 550: it breaks 8..13 ticks after the hit. Else target speed = player speed − \|dx\| / 4 + 70 × (fleeing planes before it this tick, `-$3198`), and on reaching its target altitude it picks a new one, 35 + 10 × rand(7) (35..95) | confirmed |
| 3 | \|dx\| ≥ 1536 | turn | confirmed |
| 4 | Opposite heading, plane to the left | If the player is flying: target speed 900, target altitude = player ± 32 (above if it is not below), +18 = \|dx\| × 100 / (speed + player's horizontal step), and turn now | confirmed |

A fleeing fighter (+4 = 3) slows down as the player falls back, which keeps
it in gun range. Its speed matches the player's at dx = 0 (first plane) or
at dx = 280 (second). **Inferred** (arithmetic).

### Attack, behaviour 2 (0xdccc)

- Leaves the attack (behaviour 1) as soon as +4 ≠ 1. If the player turns or
  is on deck: behaviour 9 (1 + turning), +18 = \|dx\| / (speed / 100): it
  overshoots and turns where the player was. **Confirmed.**
- Holds 130 px behind: target speed = player speed + 50 beyond 130 px,
  − 50 inside. Target altitude = the player's. **Confirmed.**
- **Firing** (+12 = 1) when all hold: the player is flying (mode 0);
  behaviour exactly 2; rank 1; \|altitude difference\| < 8; turn frame 0;
  \|dx\| < 160; same heading; the plane behind the player. So only one fighter
  fires at a time. **Confirmed.**
- **Damage (0xde52)** while firing, when also the debug invulnerability
  `-$408c` is off, **the altitudes are exactly equal**, and the tick parity
  `-$3cb8` is 1 (every other tick): player hit counter (+10) − 1. At ≤ 0:
  oil (+12) − 8, fuel (+e) − rand(32), counter = 6 + rand(5). **Confirmed.**
- No range falloff and no random roll apart from the counter reset. The
  attacker's altitude steps by 1..2 px near the target, so it hits only on
  some ticks. **Inferred.**
- Oil 128 fails below 96. So 5 counter run-outs (about 35..45 damaging
  ticks, at least twice that in ticks of firing) stop the engine, sooner
  with the leak (1 per 80 ticks once damaged). **Inferred** (arithmetic,
  with amiga-fuel-oil.md).

### Torpedo plane, behaviour 4 (0xdea4)

The carrier's range is `-$5c02` .. `-$5c00`: the US carrier's hull × 4,
16 px in at each end (0xb7bc). "Approaching" means facing −1 with
x > `-$5c00`, or facing +1 with x < `-$5c02`. **Confirmed.**

| Part | Rule | Confidence |
| --- | --- | --- |
| Cruise | Speed stays 900 (9 px/tick, 112 px/s) at altitude 50 unless chased | confirmed |
| Chased (+4 = 3) | If hit: +18 = 8 + rand(6), +10 = 275. If \|dx\| > 150: target speed = player speed − 240 (so 900 in practice). Inside 150: player speed + (150 − \|dx\|): it stays about 150 px ahead. New target altitude 35..95 whenever it reaches the old one | confirmed |
| Descent | Approaching and within 1000 px of the carrier's near end: target altitude 20 | confirmed |
| Drop | Approaching, altitude exactly 20, turn frame 0: torpedo released (below). Then target speed 1300 (2600 / 2), target altitude 60, behaviour 16, timer `-$5f6a` = 500 | confirmed |
| Overshoot | Not approaching (past the near end without dropping): +10 − 1, and a turn when it runs out (at once, since +10 is normally 0). Also a turn more than 500 px beyond the far end | confirmed |
| Arrival point | 50 → 20 takes about 12 ticks, so the drop comes about 870 px short of the deck end. The torpedo falls about 11 ticks (≈ 100 px) and runs the rest, about 770 px of its 858 px range. It reaches the carrier unless something solid lies between | inferred (arithmetic) |

Torpedo planes do not follow the player's altitude and never fire.
**Confirmed** (the altitude-follow and firing code test behaviour bits 0/1
and behaviour 2).

**After the drop (behaviour 16, 0xe17a):** freed when more than 2600 px from
the player (0xd18c; the only distance despawn in the game). It turns if
the player gets ahead of it on the same heading (+4 = 1). When chased it
picks altitudes 25..95 and breaks after hits like a fighter. It is not
counted in `-$5e28`. **Confirmed.**

### The enemy torpedo (`-$5a6a`, 42 bytes, the ordnance layout)

Dropped by 0xe08c **without checking whether the slot is busy**: type 2,
x = plane x, altitude = plane altitude + 15 (35 at the drop), vx = speed ×
0x28f (speed / 100 px/tick) negated facing left, vy = 0, +1f = facing (it
selects `tor2` / `tor7`), state 0xff. It is then moved, drawn and
detonated by the player's ordnance code (0x0a92 → 0x0aa6, 0x06ea → 0x0702).
**Confirmed.**

- Fall, surfacing at altitude ≤ 12 (needs vy ≥ −5), run at 4.3125 px/tick
  for 199 moves, wake of splashes, invisible while running: exactly the
  player's torpedo ([amiga-ships.md](amiga-ships.md)). **Confirmed.**
- It hits the first non-sea column. On the US carrier (0x4a4e, always
  last) a running torpedo takes 1 off the hull `-$5b1a` (4 at each map,
  0x3056). **Confirmed.**
- At hull 0 the carrier sinks on the ships' clock. Torpedo planes stop
  coming. At the next new plane (0x35fe) the game is over (`-$5c9c`,
  `-$5c3c`), and at sink step 120 `-$5a3d` is set. **Confirmed** control
  flow. The game-over meaning is **inferred**.
- **Destroyed by** 0x1ae2 (0x1b24 checks `-$5a6a` while its state copy
  +c ≠ 0, falling or running): any player bomb or rocket burst, or gun
  strike on the sea, in [x − 48, x + 16] of the impact; and any shell splash
  from an enemy ship gun within 10 px. **Confirmed.** This is DEF-02.
- A new plane on deck (0x3684 → 0x3756) clears all ordnance, the enemy
  torpedo included. **Confirmed.**
- No sound at the drop. The sea entry plays the splash (0x233e), and the
  hit plays boom + splash, as for the player's torpedo. **Confirmed.**

## The player's gun against planes (0xb682, every tick while firing)

Runs while the fire flag `-$5c94` is set. It walks all 4 slots **without
testing +0**. **Confirmed.**

| Test | Value | Confidence |
| --- | --- | --- |
| Relation | +4 = 3: the plane ahead of the player, same heading | confirmed |
| Range | \|dx\| < 160 px and \|altitude difference\| < 20 px | confirmed |
| Attitude | the player's commanded climb `-$5bfc` = 0 exactly (level; a dive or climb input misses) | confirmed |
| Each tick in the box | +6 = 1 (the plane breaks), +a − 1 | confirmed |
| When +a reaches 0 | spark effect type 6 at (x − 16 + rand(8), altitude + 16); health − 8; +a = 6 + rand(4) | confirmed |
| Kill (health < 96) | score `-$5cb2` **+350**; state 4; target altitude −3; turn frame 0, turn flag off | confirmed |

- 19 health losses are needed: 5..7 ticks for the first, 6..9 for each of
  the next 18, so about 140 ticks (11 s) in the box. **Inferred**
  (arithmetic).
- Damage smoke (0xe728): while flying with health < 128 (after 14 hits),
  each tick with probability (128 − health) / 64, a puff of type
  (128 − health) / 8 + 1 (2..5 grows into fire 6) at (x + rand(8),
  altitude + 17). **Confirmed.**
- Rockets, bombs and torpedoes have no test against planes. The only
  references to the plane array are the 11 sites listed in this note, and
  none is a weapon or a collision test. **Confirmed.**
- **No collisions** between the player and enemy planes (same evidence).
  **Confirmed.**
- Quirk: a falling plane still answers the test, so continued fire on it
  scores +350 again each time +a runs out while it stays in the box.
  A freed slot keeps a stale +4, x and altitude, so a level pass through
  that spot while firing can "kill" it again and bring it back as a falling
  plane. **Confirmed** control flow; how often this happens is **inferred**
  (rarely, near the surface).

## Shot down: fall, crash, wreck (0xe244, 0xe3e8)

| Phase | Rule | Confidence |
| --- | --- | --- |
| Fall | Keeps its x speed (turn factor 1) and heading. The altitude falls by gravity (+22) plus the 5..6 px/tick step toward −3. Fire and smoke puffs as above, at (x − 16 + rand(8), altitude + 16) | confirmed |
| Surface | When the altitude reaches the target: speed − 35 per tick. Every tick: soldiers within 20 px die (0x1a84); a splash/dust effect (0x52ac) at x + 4 × facing; while speed > 500, a rocket-type impact on the column below (0x46c6) | confirmed |
| Sea, speed < 300 | every other tick the target altitude − 1 and speed + 24: it slides and sinks slowly | confirmed |
| Rest (speed < 100) | kills `-$5c7f` + 1. On island ground (class 2) inside the map: state 16 (wreck), +2 = 0, smoke size 6, countdown 30. Elsewhere (sea, ship or carrier deck): freed, and `-$5e28` − 1 unless it was a torpedo plane | confirmed |
| Wreck (state 16) | Drawn as the level plane (see Shape index). The smoke size falls 6 → 1 at intervals 30, 25, 20, 15, 10 ticks (100 ticks), with a puff every 4th tick at (x − 4, 12). Then x × facing goes into the wreck list `-$5e24`, `-$5e28` − 1, and the slot is freed | confirmed |
| Wreck list | Drawn every frame for the rest of the mission at altitude 4 as `jc1a` / `jc10` (0x0da6). Cleared per mission (0x35c0) | confirmed |

- The rocket-type impact can destroy huts and AA guns, or a ship gun (+200),
  and dying soldiers score +25. So a fighter crashing on an island can
  score points for the player. **Inferred** from 0x46dc's handlers.
- No sound for the kill, the fall or the crash. **Confirmed** (no sound
  call in 0xd18c..0xe8c0).
- Quirk: a torpedo plane that crashes on an island gets +2 = 0. At the end of
  its wreck `-$5e28` is decremented though it was never counted, which lets
  one extra fighter up. **Confirmed** control flow.
- Quirk: the wreck list has 40 entries and no bound. A 41st island wreck in
  one mission would overwrite slot 0 of the plane array. **Confirmed**
  layout; never reached in play (**inferred**).

## Kill counter (HUD-07, 0xf178)

`-$5c7f` (byte) is cleared once per game (0x0096), so it carries across
missions, and incremented when a shot-down plane comes to rest. It is shown
capped at 99, redrawn only when it changes. **Confirmed.**

- **Number:** two digits from the dash `wnum` strip (a vertical strip;
  digit d is offset by 88 − 8d), at dashboard x 508 and 522, y 21, clipped
  to rows 20..28. **Confirmed.**
- **Icons:** dash shape `zero`, one per kill, 13 px apart from x 534: the
  first 7 on row y 19, the next 7 on y 25, clipped to rows 19..31 (at most
  14 icons). **Confirmed.**
- The score is drawn the same way at y 11, x 512 + 14 per digit. **Confirmed.**

## Pilot-window arrow (DEF-03, 0xf21a)

Every dashboard update (0xee16 → 0xee5a, in every player mode), the first
slot with +0 ≠ 0 and (+2 & 7) = 4 (an armed torpedo plane, turning or
not) gets the arrow: dash `ltar` if player x − plane x ≥ 0, else `rtar`.
It is drawn at (320, 10), the top centre of the pilot window, using the
shape's origin. **Confirmed.** It shows from the spawn, 6144 px away, until
the drop, and also while the plane falls after being shot (+2 stays 4).
There is no distance condition. **Confirmed.**

## Drawing

### Shape index (0xd35a)

+30 = turn frame +16, or 26 for an armed torpedo plane when not turning,
+ 28 when facing right. 0xe3e8 writes 27 / 55 for a burning wreck, but
0xd35a runs after it in the same tick and overwrites it with +16 (0) + 28 by
facing. So a burning wreck is drawn as the level plane `jp1a` / `jp10`. Only
the wreck list (0x0da6) draws `jc1a` / `jc10`. **Confirmed** (call order
0xe85e → 0xe8a2).

Tables built by 0xd1ea from name lists (`-$50a6` / `-$5036` near,
`-$4fc6` / `-$4f56` far):

| Frame | Facing left (near / far) | Facing right (near / far) |
| --- | --- | --- |
| 0 (level) | jp1a / zpn0 | jp10 / zpnn |
| 1..3 | jp19 / zpn6 | jp11 / zpn8 |
| 4..6 | jp18 / zpn7 | jp12 / zpn9 |
| 7..8 | jp1b / zpnb | jp13 / zpng |
| 9..11 | jp1c / zpnc | jp14 / zpnh |
| 12..13 | jp1d / zpnd | jp15 / zpni |
| 14 | jp15 / zpni | jp1d / zpnd |
| 15..17 | jp16 / zpnj | jp1e / zpne |
| 18..19 | jp17 / zpnk | jp1f / zpnf |
| 20..22 | jp18 / zpn7 | jp12 / zpn9 |
| 23..25 | jp19 / zpn6 | jp11 / zpn8 |
| 26 torpedo plane | jt1a / zpn0 | jt10 / zpnn |
| 27 wreck (only via the wreck list) | jc1a / zpn0 | jc10 / zpnn |

There are no climb or dive poses. The far view shows the torpedo plane and
the wreck as a level `zpn`. **Confirmed.** japplane.shp also holds `jp21` /
`jp22` (parked) and `fc10 fd10 fc1a fd1a` (muzzle flash).

### Planes in the world view (0x0e1a)

- Position: screen x = +20 − camera x (`-$60ce`), y = camera base
  (`-$60cc`) − altitude − 7. In the far view (`-$60ca` ≠ 0) both are
  shifted right by 3 (÷ 8). Drawn only when −128 ≤ x ≤ 448. **Confirmed.**
- Muzzle flash while +12 is set, near view only: +2c counts draws. On odd
  counts it draws `fc10` / `fd10` (right) or `fc1a` / `fd1a` (left), the
  two alternating: off, fc, off, fd. **Confirmed.**
- **Draw order** (0x38ba..0x38e2): terrain, carrier, player (0x03a6),
  island wrecks then enemy planes (0x0da6), dugout and AA guns, ship guns,
  airstrip planes, parked ship planes, then the rest. Enemy planes are drawn
  over the player. **Confirmed.**

### Pilot window (0x4206)

The 3-D view scans 11 depth bands ahead of the player. In columns ahead,
from `-$6948`: 130..160, 105..130, 90..105, 76..90, 63..76, 51..63, 40..51,
30..40, 21..30, 13..21 and 6..13 (48 to 1280 px). It draws the bands far to
near and moves the horizon row `-$5c1c` down 1 px per band. A
plane whose +2e falls in a band is drawn at x 319, y = horizon − (altitude
/ 4 + 4). The shape is `-$3ba2`[+30 (+ 28 mod 56 when the player faces
right) + `-$696c`[band]] from dash.shp: 3 sets `zr1*`, `zr2*`, `zr3*` of
56. The band offsets are 0 (nearest 3 bands), 28, 56, 84 (farthest 2).
**Confirmed** data and control flow. An offset of 28 or 84 straddles two
sets (a different view of the same size, or the next size), and `zr4*` is
never used. Whether this is deliberate is **open**.

## Sounds

| Event | Sound | Confidence |
| --- | --- | --- |
| Any enemy plane firing (+12 of any slot) | `machinegun` loop, period 160 (the player's gun: 200), volume 57, channel `-$3c66` | confirmed (0x2204, 0x1fba) |
| Enemy engine | `Engine` loop, period 330 (player 380), channel `-$3c4e`; volume by the nearest plane in state 1..2, d = \|dx\| + \|dalt\|: v = d >> 4; silent above 44 (about 720 px); 64 − 4v up to 5, else 64 − (v + 20) | confirmed (0x21c6, 0x22ce) |
| Player hits a plane, kill, fall, crash, wreck | none (spark and smoke effects only) | confirmed |
| Enemy torpedo meets the sea / hits | splash; boom + splash (the shared ordnance code) | confirmed |

## Map j's sixth battleship plane

The battleship on j launches 6 planes from a 5-entry table. The first
launch reads past the table: x = H + 320, altitude **−32768**
([amiga-ships.md](amiga-ships.md)). In the plane code: **confirmed**
arithmetic, **inferred** effects.

- The fighter floor makes its target altitude ≥ 33. The difference
  33 − (−32768) overflows a word, its absolute value is still > 100, so it
  climbs 5..6 px/tick. It needs about 5,960 ticks (8 minutes) to come up.
- Until then it is never drawn on screen (y is far outside the playfield),
  never in the gun box (\|dalt\| ≥ 20), never fires (\|dalt\| ≥ 8), and its
  engine is silent.
- It still counts in `-$5e28` (max 2 for that ship), so only one real
  fighter at a time can come from the battleship.
- It can take rank 1 among planes on the player's tail (rank is by \|dx\|
  only). The real fighter then has rank 2 and never fires.

## Pseudo-code (for the port)

Added 2026-11-18 from the same disassembly. C-like; every variable is a
signed 16-bit word (`int16`) unless marked, and every comparison is signed
(`blt`/`bgt`/`ble`/`bge`) unless marked unsigned. `/` is the 68000 `divs`
(truncation toward zero). `P` is the player record `-$5f86` (via `-$3212`):
`P.alt` +0, `P.x` +2 (`-$5f84`), `P.mode` +c, `P.hits` +10, `P.oil` +12,
`P.fuel` +e, `P.facing` +14 (`-$5f72`), `P.hstep` +16. Other player values:
`ptf` = turn frame `-$5bf0`, `pspeed` = airspeed `-$5bea`, `pclimb` =
commanded climb `-$5bfc`. `e` is the enemy record. **Confirmed** unless a
line says otherwise.

### Order within a logic tick (0x1386)

```
flight handler 0xc660 (player controls, integration; 0xbc02 timer first)
enemy update  0xe7d6  (below)
sound         0x2132
player gun    0xb682
... ordnance 0x0a72 (enemy torpedo moves here), cooldown, launches 0x1622, 0x1510/0x1574
```

So the enemy code reads the player's x, altitude and facing **after** the
player's move in this tick. Each plane's own x is from before its move
(0xd3b4 runs before 0xd796).

### Random numbers (0x103be, 0xcac8)

```
rand16():                              // 0x103be, A4 stub -$7d52
    d0 = (int32)(int16)seed * 0x1afb + 0x1fccd   // seed = -$46ec
    d0.low16 ^= VHPOSR                   // $dff006: beam (line<<8)|hpos
    -$46ee = d0.low16;  return d0        // -$46ec itself is not updated
rand(n) = (uint16)rand16().low16 % n     // 0xcac8: divu, remainder, 0..n-1
```

`-$46ec` is written only by 0x103da, called at 0x8486 in demo record/playback
mode. In normal play it is 0, so the value is 0xfccd XOR the beam position
at the moment of the call. The randomness is the beam position. For the
port any uniform generator gives the same distribution: rand(n) is 0..n−1,
with the slight bias of a 16-bit value mod n. 0xbc02 tests bit 15 of
`rand16()` directly. **Confirmed** code; "uniform enough" **inferred**.

### 0xd3b4: relation and distance

```
same = (P.facing == e.facing)                 // word compare
dx   = e.x - P.x                              // word subtraction
if (same) {
    e.rel = 1
    if ((int16)(dx ^ P.facing) >= 0) {         // the plane is ahead of the player
        e.rel = 3
        if (e.t10 == 0) e.t10 = 550
    }
} else {
    e.rel = 2
    if (dx < 0) e.rel = 4
}
e.dist = (e.x - P.x);  if (e.dist < 0) e.dist = -e.dist     // +28
```

For dx = 0: same heading facing right gives 0 ^ 1 = 1 ≥ 0, so rel 3; facing
left gives 0 ^ −1 = −1, so rel 1. Opposite heading gives rel 2.

### 0xd476: rank (called once per slot, 4 times a tick)

```
for (i = 0; i < 4; i++) {
    if (slot[i].beh == 0 || slot[i].rel != 1) continue   // +c left unchanged
    r = 1
    for (j = 0; j < i; j++) {
        if (slot[j].rel != 1) continue        // NOTE: slot j's beh/state not tested
        if (slot[j].dist < slot[i].dist) r++
        else slot[j].rank++                    // equal distance: the later slot wins
    }
    slot[i].rank = r
}
```

- Slots take part when +2 ≠ 0 and +4 = 1. A slot with no relation 1 keeps
  a stale +c.
- In the inner loop a free slot with a stale +4 = 1 still counts. **Confirmed**
  (quirk).
- On ties the slot with the higher index gets the better rank.

### 0xe64e: speed step (state 2 only)

```
if (e.state != 2) return
if (e.tspeed < 900)  e.tspeed = 900
if (e.tspeed > 2600) e.tspeed = 2600
if (e.speed < e.tspeed) {
    e.speed += (int16)((int32)(e.tspeed - e.speed) / 2) + 5
    if (e.speed > 2600) e.speed = 2600
} else if (e.speed > e.tspeed) {
    e.speed -= (int16)((int32)(e.speed - e.tspeed) / 2) - 5
    if (e.speed < 900) e.speed = 900
}
```

Both differences are positive, so `/2` is a plain halving. The ±5 makes
small differences grow: from below or above, the speed settles at target +
10 (or + 11) and stays there. **Confirmed** arithmetic.

### 0xd796: motion

```
if ((e.state & 0x14) == 0 && (P.mode == 4 || P.mode == 8 || P.mode == 6))
    e.tspeed = 1700

// x step (mathffp: 0x11ce2 SPFlt, 0x11cec SPMul, 0x11cc4 SPFix)
q    = (int16)((int32)e.speed / 100)              // divs, truncated
n    = (int32)(q * e.facing)                       // muls.w, then ext.l
e.x += (int16)SPFix(SPMul(turnFFP[e.frame], SPFlt(n)))

if ((e.state & 0x14) == 0 && !(e.beh & 4)) {      // not an armed torpedo plane
    if (P.mode == 1) e.talt = 70
    if (e.talt < 33) e.talt = 33
}

d = e.talt - e.alt;  if (d < 0) d = -d             // word; 0x8000 stays negative
if (d > 100) d = 100
k = d / 20                                          // 0..5

if (e.state & 4) {                                  // shot down: gravity
    if (e.alt > e.talt) { e.alt += (int16)((int32)e.vy / 100); e.vy -= 10 }
    else if (e.alt < e.talt) e.alt = e.talt
}
if      (e.alt > e.talt) e.alt -= ALTSTEP[k] + rand(2)   // re-reads e.alt
else if (e.alt < e.talt) e.alt += ALTSTEP[k] + rand(2)
// equal: no change. No clamp: a step can overshoot the target.

if ((e.state & 0x14) == 0 && e.t18 != 0) {
    e.t18 -= 1
    if (e.t18 <= 0) { e.beh |= 8; e.t18 = 0 }
}
if ((e.beh & 8) && e.state == 2) turn(e)            // 0xd562
```

- `turnFFP` (`-$54f2`, 26 FFP longs) is 1.0, 0.98, 0.95, 0.91, 0.86, 0.81,
  0.75, 0.70, 0.60, 0.50, 0.40, 0.30, 0.23, 0.20, 0.0, 0.05, 0.25, 0.45,
  0.60, 0.70, 0.75, 0.81, 0.86, 0.91, 0.95, 0.98 (decoded from the FFP
  values, for example 0x80000041 = 1.0 and 0xfae14840 = 0.98).
- `ALTSTEP` (`-$4e06`) is 6 words: 1, 2, 2, 3, 4, 5. k cannot exceed 5.
- The facing is applied before the multiply, so the product is negative
  facing left. Whether SPFix truncates toward zero (symmetric) is
  **inferred** from the mathffp library, which is not in this executable.
  With truncation the step is trunc(f × q) × sign: at speed 900 it is 9, 8,
  8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 2, 1, 0, 0, 2, 4, 5, 6, 6, 7, 7, 8, 8, 8
  (**inferred**).
- k uses the altitude from before the gravity step. The comparison after it
  uses the new altitude. Near the target (d < 20) the step is 1 or 2, so a
  plane can overshoot by 1 and alternate around the target.

### 0xd562 / 0xd530: turns (state 2 with +2 bit 3 set; called from 0xd796)

```
turn(e):
    onDeck = (P.mode == 1)
    fighter = (e.beh & 3) != 0                // behaviour 1, 2, 9, 10
    if (P.mode == 0 && fighter) e.talt = P.alt
    if (ptf == 0 && !onDeck && P.mode == 0 && e.frame >= 19
        && (e.rel == 1 || e.rel == 3) && fighter) {
        e.frame = 0;  e.beh &= ~8;  return     // cut short
    }
    // 0xd530
    e.t10 = 0
    t = e.sub;  e.sub -= 1
    if (t <= 0) { e.sub = 2;  e.frame += 1 }
    if (e.frame > 25) { e.frame = 0;  e.beh &= ~8;  return }
    if (e.frame == 14) { e.facing = -e.facing;  e.frame += 1;  return }   // 14 → 15 at once
    if (e.frame != 20 || !fighter || P.mode != 0) return
    if (e.rev >= 3) { e.rev = 0;  e.t10 = 550;  return }
    flag = 0
    switch (e.rel) {
    case 1: if (ptf > 0 && ptf < 6 && e.t10 == 0) e.t18 = (int32)(e.dist * 100) / e.speed
            flag = 1;  break
    case 2: if (ptf > 0 && ptf < 6) flag = 1;  break
    case 3: flag = 1;  break
    case 4: if (e.t10 == 0) e.t18 = (int32)(e.dist * 100) / (e.speed + pspeed)
            flag = 1;  break
    }
    if (flag && !onDeck && e.t10 == 0) {
        e.frame -= (e.frame - 13) * 2          // 20 → 6
        e.rev += 1
    }
```

- **Start:** a turn starts when anything sets +2 bit 3 (the AI branches, or
  +18 reaching 0). 0xd796 runs after the AI in the same tick, so turn()
  runs that same tick. The frame stays 0 until `e.sub`, left over from the
  last turn (2 after a full turn), has counted down. Then it advances to 1
  on the tick where the value before the decrement is ≤ 0: 3 ticks after a
  full turn, 1..3 after a cut-short one.
- **Steps:** one frame per 3 ticks. Frames 1..13, then 14 → 15 with the
  flip in the same tick, then 15..25, then 26 → frame 0 and the flag cleared
  in the same tick. That is 25 advances, 75 ticks. The facing changes on
  the tick the frame would become 14.
- t10 is always 0 at the frame-20 test (0xd530 cleared it just before), so
  those `e.t10 == 0` tests always pass.
- `e.frame == 20` holds for 3 ticks. A tick that returns early (no flag, or
  the rev ≥ 3 reset) is followed by another test on the next tick.
- Torpedo planes (behaviour 4, 12, 16, 24) only step and flip.
- The muls/divs above are 16 × 16 → 32 and 32 / 16. The quotient is the low
  word.

### 0xdea4: torpedo plane, behaviour 4 (with or without +8)

L = `-$5c02` = US carrier +0 × 4 + 16, and R = `-$5c00` = US carrier +2 ×
4 − 16 (0xb7bc): the landing range.

```
if (e.rel == 3) {                                   // chased
    if (e.hit == 1) {
        e.hit = 0
        if (e.t18 == 0) e.t18 = rand(6) + 8
        e.t10 = 275
    }
    if (e.dist > 150) e.dist = 240
    if (e.dist < 150) {
        e.dist -= 150
        if (e.alt == e.talt) e.talt = rand(7) * 10 + 35
    }
    e.tspeed = pspeed - e.dist                       // dist == 150: pspeed - 150
} else {
    if (e.facing == -1 && e.x < L - 500) e.beh |= 8
    else if (e.facing == 1 && e.x > R + 500) e.beh |= 8
}
// descent: within 1000 px of the near end, measured from L or R
if (e.facing == -1 && e.x > R && e.x - R < 1000) e.talt = 20
else if (e.facing == 1 && e.x < L && L - e.x < 1000) e.talt = 20
approaching = (e.facing == -1 && e.x > R) || (e.facing == 1 && e.x < L)
if (approaching) {
    if (e.alt == 20 && e.frame == 0) drop(e)
} else {
    e.t10 -= 1
    if (e.t10 <= 0) { e.beh |= 8;  e.t10 = 0 }
}

drop(e):                                             // T = -$5a6a, not tested for busy
    T.type(+22.w) = 2;   T.vy(+12.l) = 0
    T.vx(+e.l) = (int32)e.speed * 0x28f              // speed/100 px/tick in 16.16
    T.y(+4.l)  = (int32)(e.alt + 15) << 16
    T.x(+0.l)  = (int32)e.x << 16
    T.facing(+1f.b) = low byte of e.facing;  if (T.facing == 0xff) T.vx = -T.vx
    T.state(+20.b) = 0xff;   T.frame(+1e.b) = 0
    e.state = 2;  e.tspeed = 2600 / 2;  e.talt = 60
    e.beh = 16                                       // also clears the turn flag
    torpedoTimer = 500
```

- All comparisons are signed and strict as written: x > R, x < L, x − R
  < 1000, x < L − 500, x > R + 500.
- The chased branch skips the 500 px turn rule. The descent and drop tests
  run in both branches.
- `e.dist` (+28) is overwritten here, but 0xd3b4 recomputes it at the start
  of the next tick.
- Because 0xd3b4 sets t10 = 550 whenever rel = 3 and t10 = 0, a plane that
  was chased while past the carrier waits up to 550 ticks before it turns.
  Otherwise t10 is 0, and it turns on the first tick past the near end.
- The torpedo's +16/+1a (accelerations) and +21 are not written. **Confirmed**;
  the ordnance code does not read them for a falling torpedo (**inferred**
  from amiga-ships.md).

### 0xbc02: torpedo-plane timer

```
d = 0x7fff - P.x;  if (d < 0) d = -d                 // word
if (input(-$42bc) & 0x30) {                          // fire: tap (bit 5) or hold (bit 4)
    if (timer != 0 && timer < 750) timer = 750
    return                                           // no count-down this tick
}
if (timer == 0) return
if (carrier.present(-$5b22) == 0) return
if (carrier.hull(-$5b1a) == 0) return
timer -= 1
if (timer != 0) return
if (d <= 0x1a00) return                              // signed ble: spawn needs d > 6656
if (P.x < L)                      spawn(1, P.x - 0x1800, 0, +1)
else if (P.x > R)                 spawn(1, P.x + 0x1800, 0, -1)
else if (rand16() & 0x8000)       spawn(1, P.x - 0x1800, 0, +1)   // btst #15
else                              spawn(1, P.x + 0x1800, 0, -1)
```

L and R are the same landing-range bounds, both strict. Over the carrier
(L ≤ x ≤ R) the side depends on bit 15 of rand16, which is 1 XOR bit 7 of
the beam line. P.x ± 0x1800 is word arithmetic.

### 0xd35a: shape index

```
idx = e.frame                                        // +16
if ((e.beh & 4) && e.frame == 0) idx = 26
e.shape = (e.facing == -1) ? idx : idx + 28          // any facing other than -1 adds 28
```

Called for every active slot at the end of the update, after the state
handler, so it overrides 0xe3e8's 27 / 55.

### 0x0e1a vs 0x03a6: where the planes are drawn

```
// camera (0x0260): shift = far ? 3 : 0
camX = renderPlayerX(-$41a2) + (-160 << shift)
base = far ? 1208 : 151 + max(0, renderPlayerAlt(-$419e) - 131)   // -$60cc

// player (0x04fc): anchor before the shape origin
px = 160
py = (base - renderPlayerAlt) >> shift              // asr
blit(shape, px - shape.ox, py - shape.oy)

// enemy plane (0x0e26)
ex = e.x - camX
ey = -e.alt + base - 7
if (far) { ex >>= 3;  ey >>= 3 }                     // asr
if (ex < -128 || ex > 448) skip                       // checked after the shift
blit(shape, ex - shape.ox, ey - shape.oy)
```

- `shape.ox` / `shape.oy` are words +4 / +6 of the shape record (+0 is the
  byte stride, +2 the height). The blitter draws with the shape's top-left
  at the computed point. **Confirmed** code.
- The enemy's anchor is **7 px higher** than the player's at the same
  altitude, in the near view. The origins in the archives: hc05 (level
  Hellcat, 48 × 13) has its origin at (25, 8); jp1a / jp10 (level Zero,
  48 × 11) at (25, 6); jt1a (48 × 13) at (21, 6) and jt10 at (27, 6).
  So at equal altitude the Zero's top row is 13 px above the anchor point
  and the Hellcat's is 8 px above. The Zero's centre row is about 6 px above
  the Hellcat's.
- In the far view the 7 px becomes 0..1 px after the shift. zpn0 / zpnn
  have origin y 1. **Confirmed** data, assuming the file header is the
  runtime record (it is what the code subtracts at +4/+6). The visual
  result is **inferred**.
- The player uses the render copies `-$41a2` / `-$419e` (copied at 0x045c
  before drawing); the enemies use their live +20 / +26. In the port both
  come from the same tick.

So an enemy at exactly the player's altitude (the only altitude at which it
can damage the player) is drawn about 6 px above the Hellcat. The original
does this. **Confirmed** arithmetic; whether it is intended is **open**.

### The fire flag `-$5c94` (0xb5b0, first thing in the flight handler 0xc660)

The input word `-$42bc` comes from the VBlank sampler (0xc9ca/0xca32). Bit 4
is "button held for 10 or more VBlanks" (0.2 s, the gun). Bit 5 is "pressed
and released within 10 VBlanks" (a tap, the selected weapon).

```
in = input & 0x30
if (in == 0) { fireFlag = 0; return }
if (P.mode == 0) {
    if (input & 0x20) {                        // tap
        if (ptf < 6 || ptf > 16) fireWeapon()  // 0x107c; fireFlag unchanged
    } else {                                   // held
        if (ptf == 0 && ammo(-$50ea) > 0) fireFlag = 1
        else fireFlag = 0
    }
} else if (P.mode == 1) { ...carrier/elevator branch, fireFlag untouched... }
// other modes: fireFlag untouched
```

- `-$50ea` is set to 1536 (0x600) for each new plane (0x36b0) and never
  decremented, so the gun has no ammunition limit. **Confirmed** (the only
  write).
- The gun fires only with the turn frame at 0. There is no cooldown or
  bullet object: the flag is on for every tick the button is held.
- The deck controls (0xc4f2, mode 1) and the engine failure (0xc75e,
  mode 4) clear the flag every tick. In modes 6, 7, 8 and others it keeps
  its value until the button is released. So holding fire through a crash
  keeps the gun "on" for 0xb682, which does not test the mode. **Confirmed**
  control flow (quirk).
- The player's gun sound copies the flag (0x21c0 → `-$3c96`).

### The commanded climb `-$5bfc` (set by 0xbff4, read by 0xb682)

The commanded climb is in hundredths of a degree. The step `-$50e8` is 600.
The full rules are in [amiga-fuel-oil.md](amiga-fuel-oil.md). What matters
for "= 0":

```
no input at all (input & 0xf == 0):
    if turning (ptf != 0): climb -= 150, min -2250
    else if (climb > 0):   climb -= 600, and if climb < 0: climb = 0
    // climb <= 0 and not turning: unchanged (a dive is kept)
horizontal only, no up/down: the same two rules (0xc21e..0xc284)
up/down held: changes by ±600 / ±300 / +150 / +75 / -1200 (see the fuel note)
new plane (0xb896), crash code (0xb034, 0xb092, 0xb17e): climb = 0
```

So `-$5bfc` = 0 exactly when a positive climb has decayed to the clamp at 0
with no vertical input and no turn, or when nothing has changed it since
the plane left the deck. A dive never returns to 0 by itself: the player
must press up until the climb is positive, then let go. Any turn, or any
vertical input that leaves it non-zero, stops the gun from hitting planes.
**Confirmed.**

### 0xb682: the player's gun against planes (logic tick, after 0xe7d6)

```
if (fireFlag == 0) return
for (i = 0; i < 4; i++) {                       // NOTE: e.state not tested
    e = &slot[i]
    if (e.rel != 3) continue
    dx = P.x - e.x;  if (dx < 0) dx = -dx
    da = P.alt - e.alt;  if (da < 0) da = -da
    if (dx >= 160) continue
    if (da >= 20) continue
    if (pclimb != 0) continue
    e.hit = 1                                   // +6
    e.hitsub -= 1                               // +a
    if (e.hitsub > 0) continue
    effect(0, 6, e.x - 16, e.alt + 10)          // 0xcae0, see below
    e.health -= 8                               // +8
    if (e.health < 96) {
        score(-$5cb2, long) += 350
        e.state = 4;  e.talt = -3;  e.frame = 0;  e.beh &= ~8
        shapeIndex(e)                           // 0xd35a
    }
    e.hitsub = rand(4) + 6                      // 6..9, also after a kill
}
```

`e.rel`, `e.x` and `e.alt` are this tick's values: 0xd3b4 and 0xd796 ran
earlier in the tick. P is after the player's move. **Confirmed.**

### Effects: 0xcae0 and the puff pool

```
effect(unused, type, x, alt):                    // 0xcae0
    x   += rand16() & 7                          // 0..7
    alt += 6
    spawnPuff((int32)x << 16, (int32)alt << 16, type)   // 0x54cc -> 0x5460

spawnPuff(x16, y16, type):                       // 0x5460
    for (k = 0; k < 40; k++) if (pool[k].type == 0) break
    if (k == 40) return                          // pool full: dropped
    pool[k].x = x16
    pool[k].y = max(y16, 16 << 16)               // altitude at least 16
    pool[k].type = type;  pool[k].life = 6
    pool[k].vx = 0x10000 + (rand16() & 0xffff)   // 1.0 .. 2.0 px per draw, rightward
    pool[k].vy = 0x10000 + (rand16() & 0xffff)   // 1.0 .. 2.0 px per draw, upward
```

- It is the same pool as the engine smoke: `-$40a6`, 40 entries of 20
  bytes. **Confirmed.**
- The first argument of 0xcae0 (0 or 1) is never read. **Confirmed.**
- The update and draw (0x0ee0, once per drawn frame) draws world shape
  0x60 + type at (x, y). Then x += vx, y += vy, and life −1. When life goes
  below 0 it is reset to 6 and the type drops by 1. Type 0 is free. So each
  type shows for 7 draws. **Confirmed.**
- World ids 0x61..0x66 are `smk0`..`smk5` (5 the largest smoke, 6 the
  fire-coloured `smk5`). Types 7, 8, … would be 0x67 `spl0`, 0x68 `spl1`
  (splash frames) and decay down through `smk5`. The far view draws
  8thscale `smk0` (type ≤ 3) or `smk1`. **Confirmed.**
- **Gun hit spark:** type 6 at (e.x − 16 + 0..7, e.alt + 16).

### 0xe728: damage smoke while flying (state 2, before the AI)

```
p = 128 - e.health                               // word
if (p > (rand16() & 63)) effect(1, (p >> 3) + 1, e.x, e.alt + 11)   // asr
// then the behaviour dispatch (0xd9c6 / 0xdccc / 0xdea4 / 0xe17a by beh & ~8)
```

- The puff appears at (e.x + 0..7, e.alt + 17).
- The probability per tick is p/64 for 0 < p < 64: no smoke at health ≥ 128,
  1/64 at 127, and 32/64 at 96, the lowest health a flying plane can have.
  The type is 1 at p = 1..7, rising to 5 at p = 32..39.
- Health only falls in steps of 8 from 240, so a flying plane shows p = 8,
  16, 24, 32 (types 2, 3, 4, 5) after 14, 15, 16 and 17 hits, and p = 40
  (type 6) after 18 hits. The 19th hit kills it. **Confirmed** arithmetic.

### 0xe244: shot down (state 4; runs before 0xd796 each tick)

```
p = 128 - e.health
if (p > (rand16() & 63))                          // always true once p >= 64
    effect(1, (p >> 3) + 1, e.x - 16, e.alt + 10) // at (x-16+0..7, alt+16)
if (e.alt != e.talt) return                       // exact equality, last tick's altitude
col = mapWordPtr(e.x)                             // 0xc982
if (isSea(col) && e.speed < 300) {                // 0xcb74; strict <
    seaSlideCounter(-$4368) += 1                  // one global for all planes
    if (seaSlideCounter >= 2) { seaSlideCounter = 0;  e.talt -= 1 }
    e.speed += 24
}
e.speed -= 35
killSoldiersAndTorpedoes(e.x, 20)                 // 0x1a84
if (e.speed > 500) rocketImpactAt(col)            // 0x46c6
splashAt(e.x + e.facing * 4)                      // 0x52ac (an altitude is pushed, not read)
if (e.speed < 100) {
    kills(-$5c7f, byte) += 1
    if (isLand(col) && col >= mapBase && col < mapEnd) {   // 0xcbb2 + range tests
        e.state = 16;  e.size(+1e) = 6;  e.count(+1c) = 30;  e.beh = 0
    } else {
        if (e.beh != 4 && e.beh != 16) fightersAirborne(-$5e28) -= 1
        e.state = 0;  e.beh = 0
    }
}
```

- At a health of 88 after the kill, p = 40: a type-6 fire puff on 40 ticks
  in 64. Puffs every tick need p ≥ 64.
- **Column lookup** `mapWordPtr(x)` (0xc982): x < 0 becomes 0; then
  base + (x / 8) × 2 (`divs`), clamped to the last word (end − 2).
- `isSea(col)` (0xcb74) is true when col ≤ base (column 0 counts as sea),
  when col ≥ end − 2, or when (word & 3) = 0.
- `isLand(col)` (0xcbb2) is false outside (base, end − 2) and otherwise
  (word & 3) = 2. 0xcb34 (class 1, decks) is not used here.
- **"Reaches the target":** e.alt == e.talt exactly. In state 4, 0xd796 snaps
  the altitude up to the target when below it (before its gravity step),
  so a fall that overshoots −3 settles on exactly −3 within a few ticks.
  There is no surface height in the test: wrecks over a deck or island stop
  at −3, behind the terrain drawing. **Confirmed** code; the drawing result
  is **inferred**.
- **Speed decay:** −35 per tick on land and deck; −11 per tick
  (+24 − 35) on the sea below 300. On the sea it also sinks 1 px every other
  tick (shared counter). +1c is the speed at the kill, unchanged during the
  fall (0xe64e only runs in state 2). The x motion continues through 0xd796
  at trunc(speed/100) px/tick. **Confirmed.**
- **0x1a84(x, 20)** = 0x1a8c with r = 20. Every walking soldier with
  (unsigned)(sx − (x − 20)) ≤ 40 dies (state 2, frame 5, delay 2), with the
  scream sample (0x23ac); +25 each when the death finishes (0x3f40). Then
  0x1ae2(x − 20, 40): every player torpedo, and the enemy torpedo, with
  \|tx − (x − 20)\| ≤ 40 (that is [x − 60, x + 20]) explodes (state 8, no
  sound). This happens every tick of the slide. **Confirmed.**
- **0x46c6(col)** builds the fake ordnance `-$38fe`: x = (col − base) × 4
  (px), type 0 (rocket). It calls the impact handler 0x46dc every tick
  while speed > 500. **Confirmed.** Effects by column class:
  - Sea (class 0): only a ship lookup by x (0x4a4e); none is found on open
    sea, so nothing happens.
  - Ship or carrier column: white flash (`-$5be8` = 5, colour 0xfff), and
    the first live gun within 16 px is destroyed: +200, red flash.
  - Land (class 2): white flash every tick. A hut is wrecked (+150), a
    manned dugout empties (+200, once), an AA gun is destroyed (+200) and
    then gains damage art.
- **0x52ac(x)**: one Splashes entry (`-$40ce`, 21 × 4 bytes) at x. Over land
  (class 2) it is a 4-frame `ric0` at altitude 9; otherwise a 6-frame
  `spl6` → `spl1` at altitude 13 (0x52b0, 0x52f8). One entry per tick while
  sliding, dropped if the list is full. **Confirmed.**
- The kill counter and the freeing happen on the tick the speed goes below
  100. That tick still did the soldier, impact and splash calls. **Confirmed.**

### 0xe3e8: burning wreck on an island (state 16; 0xd796 is skipped)

```
e.shape = (e.facing == -1) ? 27 : 55              // overwritten by 0xd35a later this tick
e.count -= 1
if (e.count == 0) { e.size -= 1;  e.count = e.size * 5 }
if (e.size > 1) {
    if ((e.count & 3) == 0) effect(1, e.size, e.x - 4, 6)   // at (x-4+0..7, 12)
    return
}
wreckList[wreckCount++] = (int16)(e.facing * e.x)          // -$5e24, no bound
if (e.beh != 4 && e.beh != 16) fightersAirborne -= 1       // beh is 0 here: always
e.state = 0;  e.beh = 0
```

- Timeline from entry: size 6 for 30 ticks, then 5 for 25, 4 for 20,
  3 for 15 and 2 for 10. On tick 100 the size becomes 1 and the wreck ends
  in the same tick.
- Puffs come when the count after the update is a multiple of 4: 7 puffs at
  size 6, 6 at size 5, 5 at size 4, 3 at size 3, and 2 at size 2. Each puff
  type equals the size (6 is the fire `smk5`, then `smk4`..`smk1`).
- The torpedo-plane quirk: `beh` was set to 0 on entry, so the fighter
  count is always decremented here. **Confirmed.**

### 0x0da6: the island wreck list (render loop, before the planes)

```
for (k = 0; k < wreckCount; k++) {
    v = wreckList[k];  x = (v < 0) ? -v : v
    sx = x - camX;  sy = base - 4                // anchor at altitude 4
    if (far) { sx >>= 3;  sy >>= 3 }             // asr
    if (sx < -128 || sx > 448) continue
    s = (far ? farTable : nearTable)[(v < 0) ? 27 : 55]   // jc1a/zpn0 : jc10/zpnn
    blit(s, sx - s.ox, sy - s.oy)
}
```

- v = 0 counts as facing right. Both views draw it; the far view uses
  8thscale `zpn0` / `zpnn`, the level Zero, because there is no far wreck
  shape.
- jc1a is 48 × 10 with origin (23, 6); jc10 is 48 × 10 with origin (25, 6).
- The list is cleared per mission (`-$5e26` = 0 at 0x35c0) and drawn over
  the island terrain whatever happens to the island later. **Confirmed.**

### 0xf178: kill counter and icons (render loop, per display buffer)

```
c = min(kills(-$5c7f, unsigned byte), 99)
if (c == cache.kills) return                      // cache = -$30ce + buffer offset, +e
cache.kills = c
clip rows 20..28 (-$46a2 = 20, -$46a0 = 28)
digit(508, 21, c / 10);  digit(522, 21, c % 10)   // divu
clip rows 19..31
icons(534, 19, min(c, 7))
icons(534, 25, clamp(c - 7, ..7))                 // c - 7 <= 0: none

digit(x, y, d):                                   // 0xf2b0
    s = dash[7]                                   // wnum
    blit_clipped(s, x - s.ox, y + DIGITY[d] - s.oy)   // 0x10b0c, unmasked
DIGITY (-$6402) = 88, 80, 72, 64, 56, 48, 40, 32, 24, 16   // 88 - 8d
icons(x, y, n): repeat n: blit_masked(dash[116] zero, x - ox, y - oy); x += 13
```

- **Redraw:** only when the capped count differs from that buffer's cache.
  At each mission start 0xedaa (called at 0x00b6) sets the high byte of
  every cached word of both buffers to 0xff, which forces a redraw.
  **Confirmed.**
- **Kill count 0:** the digits are drawn as "0" and "0" (DIGITY[0] = 88),
  and no icons. So the dashboard shows "00". **Confirmed** code; the look of
  the `wnum` strip at offset 88 is **inferred**.
- The icons are only ever added. Nothing clears the icon rows when the
  count changes, and the count only grows during a game. **Confirmed**
  (no clear in 0xf178); the dashboard background is redrawn at other times
  (**inferred**).
- The score uses the same digit routine: rows 11..18, y 11, x 512 + 14 per
  digit, via the formatted string `-$30dc` (0x5078).

### Sound and score effects found in these paths

| Path | Effect | Confidence |
| --- | --- | --- |
| 0xb682 kill | +350 only; no sound | confirmed |
| 0xe244 slide | soldiers within 20 px: scream (0x23ac) and +25 each; torpedoes in [x − 60, x + 20] destroyed | confirmed |
| 0xe244 slide, speed > 500 | white screen flash on land or a ship column every tick; hut +150, manned dugout +200, AA gun +200, ship gun +200 (red flash) | confirmed |
| 0xe244 / 0xe3e8 | no sound calls | confirmed |
| Player gun | machinegun loop while the fire flag is set (0x21c0); no hit sound | confirmed |

### Behaviour dispatch (0xe728, state 2)

```
smoke (above)
switch (e.beh & ~8) {          // bclr #3: the turning flag is ignored here
case 1:  fighter(e);  break    // 0xd9c6: so behaviour 9 runs the same code
case 2:  attack(e);   break    // 0xdccc: behaviour 10 too
case 4:  torpedo(e);  break    // 0xdea4
case 16: afterDrop(e); break   // 0xe17a
}
// back in 0xe7d6: if (!(e.beh & 4) && e.talt < 33) e.talt = 33
```

The AI runs every tick, also during a turn. 0xd796 (and turn()) run after it
in the same tick. **Confirmed.**

### 0xd9c6: fighter, behaviour 1 (and 9)

`fleeCount` is `-$3198`. It is cleared once per tick at the start of 0xe7d6
(0xe7dc) and incremented only in case 3 below, in slot order.

```
switch (e.rel) {
case 1:                                            // on the player's tail
    if (e.dist < 160) {
        if (ptf > 0 && ptf < 6 && P.mode != 1 && e.t18 == 0)
            e.t18 = (int16)(e.dist * 100) / e.speed + e.rank * 2
        else if (e.t18 == 0 && e.rank == 1)
            e.beh = (e.beh & 8) | 2                // attack; keeps a running turn
        else {
            e.firing = 0                           // +12
            e.talt = P.alt
            e.tspeed = pspeed - e.rank * 70
        }
    } else if (e.frame == 0) {
        e.tspeed = e.dist + pspeed
        if (e.rank == 1) e.tspeed += 80
        else             e.tspeed -= e.rank * 80
    }
    break
case 2:                                            // opposite heading, plane right of player
    if (P.mode == 0 && ptf > 0 && ptf < 11) e.tspeed = 900
    else e.beh |= 8
    break
case 3:                                            // the player on its tail
    if (e.dist >= 1536) { e.beh |= 8;  break }
    e.t10 -= 1
    if (e.t10 <= 0 || (ptf > 0 && ptf < 6) || P.mode == 1) {
        e.beh |= 8;  e.t10 = 0;  break
    }
    if (e.hit == 1) {
        e.hit = 0
        if (e.t18 == 0) e.t18 = rand(6) + 8
        e.t10 = 550
        break
    }
    e.tspeed = pspeed - e.dist / 4                 // divs
    e.tspeed += fleeCount++ * 70
    if (e.alt == e.talt) e.talt = rand(7) * 10 + 35
    break
case 4:                                            // opposite heading, plane left of player
    if (P.mode != 0) break
    e.tspeed = 900
    e.talt = (e.alt >= P.alt) ? P.alt + 32 : P.alt - 32
    e.t18 = (int16)(e.dist * 100) / (e.speed + P.hstep)    // P.hstep = player +16
    e.beh |= 8
    break
}                                                  // rel 0: nothing
```

- `(int16)(e.dist * 100)`: the code does `muls.w #100` then `ext.l`, so
  only the low word of the product is kept. Above dist 327 it wraps, and
  t18 becomes garbage, possibly negative. A negative t18 expires on the next
  0xd796 (−1, ≤ 0: turn flag, t18 = 0). The same truncation is in turn()
  (cases 1 and 4 at frame 20). Case 1 here only runs with dist < 160, so it
  is exact. **Confirmed** (quirk).
- P.hstep is the player's horizontal step in px/tick (10..14), added to a
  speed in hundredths. The units are mixed; the code does exactly this.
- **Rank** is used here for the speed offsets (−70 × rank, ±80), for the
  +2 × rank delay in t18, and in the attack test (rank 1 only).
- **Behaviour 9** (turning): the same code runs. For example, case 1 can
  switch a turning fighter to behaviour 10 (attack + turning). The turn then
  continues in turn(), and 0xdccc handles the attack. **Confirmed.**

### 0xdccc: attack, behaviour 2 (and 10)

```
if (e.rel != 1) { e.beh = 1;  return }             // clears the turn flag; +12 not cleared
if (ptf != 0 || P.mode == 1) {
    e.beh = 9                                       // turn
    e.t18 = (int16)e.dist / (int16)(e.speed / 100)
} else if (e.dist > 130) e.tspeed = pspeed + 50
else if (e.dist < 130)   e.tspeed = pspeed - 50     // 130 exactly: unchanged
e.talt = P.alt
da = P.alt - e.alt;  if (da < 0) da = -da
armed = (P.mode == 0 && e.beh == 2)
same  = (P.facing == e.facing)
dx    = e.x - P.x
if (armed && e.rank == 1 && da < 8 && e.frame == 0 && e.dist < 160
    && same && (int16)(dx ^ P.facing) < 0) {
    e.firing = 1                                    // flash and gun sound
    if (debugInvuln(-$408c) == 0 && e.alt == P.alt && tickParity(-$3cb8) != 0) {
        P.hits -= 1                                 // +10
        if (P.hits <= 0) {
            P.oil  -= 8                             // +12
            P.fuel -= rand(32)                      // +e, may go below 0
            P.hits  = rand(5) + 6                   // 6..10
        }
    }
} else e.firing = 0
```

- **Where +12 is cleared:** only here (the else) and in the fighter's case 1
  near branch. Spawning does not clear it. Three paths leave a stale 1:
  - a fighter that leaves the attack because its relation changed (the
    first line), or that goes to cases 2..4;
  - a plane shot down while firing;
  - a slot reused after one of those.

  The stale flag keeps the muzzle flash drawn and, for states 1..2, the
  enemy gun sound on. A falling plane shot while firing keeps flashing in
  the near view until the slot is freed. **Confirmed** (quirk).
- `e.beh = 1` on a relation change also clears a running turn. If that
  happens mid-turn (a behaviour-10 plane that flips at 14), the frame stays
  where it was, with the turn factor of that frame (0.05 at 15), until the
  fighter code sets the turn flag again, usually on the next tick
  (cases 2 or 4). **Confirmed** control flow.
- **Tick parity** `-$3cb8`: at 0x13c6 in every unpaused logic tick,
  `-$3cb8 = (-$3cb8 + 1) & 1`, before the input read and the flight
  handler. Damage lands only on ticks where it is 1.
- **Debug flag** `-$408c`: toggled by a debug key (0xd184, which also
  refills the oil), 0 in normal play.
- 0xde52 is the damage block above, not a separate routine.

### Launches: 0x1510 (carrier deck roll) and 0x1574 (ship lists)

The cooldown `-$3cb6` counts down at 0x143e: `-$3cb6 -= 1; if (< 0) = 0`.
This runs every tick after the gun-strike code and before 0x1622 and 0x1510.
A launch sets it to 100, so launches are at least 100 ticks apart. It is
shared by all ships and airstrips.

Plane list (64 bytes, built by 0x252c from per-map bytes and a template; see
item 7):
- +0 count;
- +2 max airborne;
- +4 lo and +6 hi, both in px;
- 7 entries of 8 bytes at +8: state (0x8000 parked, 1 rolling), x in px,
  altitude, direction.

0x252c receives Hoff = ship record +0, a map offset, and uses Hpx =
Hoff × 4. It writes lo = Hpx + tlo, hi = Hpx + thi and each entry's x =
Hpx + tx. The altitude and direction are copied as they are.

```
// 0x1510, every tick
L = list[JapCarrier]                                   // -$5e68
if (L.count != 0) {
    a = &L.entry[L.count - 1]
    if (a.state > 0) {                                 // rolling (1); 0x8000 is negative
        v = rollV(-$3cb4);  v = v + 8 - (v >> 4);  rollV = v      // lsr, unsigned
        a.x -= v >> 4
        if (JapCarrier.Hoff * 4 > a.x) {               // strict: x < Hpx
            L.count -= 1
            spawn(0, a.x, a.alt, -1)
        }
    }
}
if (cooldown != 0) return
// 0x1574
for (k = 0; k < 5; k++) {                              // destroyer, US carrier, battleship, cruiser, Jap. carrier
    s = ship[k];  L = list[k]                          // -$5aa4 order; lists -$5f68 + 64k
    if (s.present(+4) == 0 || s.bonus(+12) == 0 || s.hull(+c) <= 0) continue
    if (px(-$4194) < L.lo || px > L.hi) continue       // inclusive window
    if (airborne(-$5e28) >= L.max) continue            // the global count against this list's max
    if (L.count == 0) continue
    if (k == 4) {                                      // Japanese carrier: start the deck roll
        a = &L.entry[L.count - 1]
        a.state = 1;  rollV = 0
        a.x = s.Hoff * 4 + 380;  a.alt = 33
        cooldown = 100
        return
    }
    L.count -= 1
    a = &L.entry[L.count]
    spawn(0, a.x, a.alt, -1)                           // always heading left; a.dir is for drawing only
    cooldown = 100
}
```

- `-$4194` is the player's x copied from `-$5f84` at 0x1288 (in 0x1274,
  called earlier in the same tick), so it is this tick's x.
- The loop does not stop after a launch: two ships whose windows both
  contain the player can each launch in the same tick. The second compares
  against the count already raised by the first. **Confirmed.**
- The carrier roll takes about 63 ticks from H + 380 to the bow
  (v → 128, 8 px/tick); simulated from the formula. Below the 100-tick
  cooldown, so a roll is not restarted. **Inferred** (arithmetic).
- **Afloat test:** present ≠ 0, bonus ≠ 0 (this excludes the US carrier),
  hull +c > 0. The roll in 0x1510 has no afloat test. **Confirmed.**

**Parked planes (0x391e, render loop, using the render copy `-$60c6` of the
lists made at 0x102c):** for each present ship, entries 0 .. count − 1 with
state ≠ 0 are drawn. So a launched entry disappears, because the count
shrinks. A rolling carrier entry is still inside the count and is drawn
moving. **Confirmed.**

```
sink = s.renderSink(+1a)
if (!far) sink += bob(-$41a8)          // and for the Japanese carrier, clip bottom = min(clip, 0x8e + sink)
else clipBottom = 0x96
for (i = 0; i < L.count; i++) if (L.entry[i].state != 0)
    drawWorld(L.entry[i].x, L.entry[i].alt - sink,
              far ? (dir < 0 ? zpn0 : zpnn) : (dir < 0 ? jp21 : jp22))   // 0x5174
drawWorld(x, alt, s):                  // 0x5174
    sx = x - camX;  sy = base + 11 - alt
    if (far) { sx >>= 3;  sy >>= 3 }
    if (sx < -128 || sx > 448) return
    blit(s, sx - s.ox, sy - s.oy)
```

jp21 is 48 × 14 with origin (26, 13); jp22 is 48 × 14 with origin (22, 13).

### 0x1622 and 0x2c84: airstrips

Zone record (20 bytes, 4 zones at `-$5d04`): +0 start, +2 end (px), +4 max,
+6 count, +8 rolling x (0 = none), +c roll speed, +e direction, +10 / +12
render copies of +6 / +8. At each map load, 0x2adc first clears all 80
bytes (0x3554). Later 0x2d5a → 0x2c84 clears +0/+2 of every zone again and
fills the zones from the map, as in "Airstrips" above.

```
// 0x2c84 (per map): scan the map words in order; x = column * 8
n = 0;  z = 0
for each column c:
    id = (word >> 2) & 0x1ff
    if (id == 0x114 || id == 0x115) {
        n += 1
        if (n & 1) zone[z].start = x
        else {
            zone[z].end = x
            zone[z].dir = (id == 0x114) ? -1 : 1
            zone[z].count = tbl[map*4 + 2z];  zone[z].max = tbl[map*4 + 2z + 1]   // -$7b0a
            // +4/+6: the words are cleared, then the low bytes come from the table.
            // rollX etc. are 0 because 0x2adc cleared all 80 bytes (0x3554) before this.
            z += 1
        }
    }

// 0x1622, every tick (after the cooldown step)
for each zone z (0..3):                                 // the roll
    if (z.rollX == 0) continue
    z.rollV = min(z.rollV + 1, 56)
    step = z.rollV >> 3                                 // 0..7
    if (z.dir == -1) { z.rollX -= step;  if (z.rollX >= z.start) continue }
    else             { z.rollX += step;  if (z.rollX <= z.end)   continue }
    spawn(0, z.rollX, 0, z.dir)                         // altitude 0
    z.rollX = 0
if (cooldown != 0) return
for each zone z (0..3):                                 // a new roll
    if (px < z.start - 480 || px > z.end + 480) continue    // inclusive
    if (airborne >= z.max) return                       // NOTE: ends the scan
    if (z.count <= 0) return                            // NOTE: ends the scan
    z.count -= 1;  cooldown = 100
    off = z.count << 6                                  // 64 px per parking place
    z.rollX = (z.dir == -1) ? z.end - 32 - off : z.start + 32 + off
    z.rollV = 0
```

- The take-off is at the strip's far end (x < start heading west,
  x > end heading east), at altitude 0. The plane then climbs toward the
  33 floor at 1..3 px/tick.
- The roll on a 344 px strip from the nearest place (312 px) takes about
  76 ticks: no step for 7 ticks, then 1 px/tick, and so on, up to 7 px/tick
  from tick 56. That is less than the cooldown. **Inferred** (arithmetic).
- An unused zone has start = end = 0. If the player is within 480 px of x 0
  it reaches `airborne >= 0`, which returns. Unused zones come after the
  real ones, so this is harmless. **Confirmed.**
- A rolling plane is not counted as airborne until it takes off.

**Drawing (0x3a18):**

```
for each zone z with z.end != 0:
    n = z.renderCount;  y = base
    if (z.dir == -1) { s = jp21;  x = z.end;   d = 32 }
    else             { s = jp22;  x = z.start; d = -32 }
    x -= camX
    if (far) { x >>= 3;  d >>= 3;  y = (y >> 3) - 1;  s = (z.dir == -1) ? zpn0 : zpnn }
    x -= d;  d *= 2;  x -= s.ox;  y -= s.oy
    repeat n: { blit(s, x, y);  x -= d }        // places end-32, end-96, ... (west)
    if (z.renderRollX != 0) {
        rx = z.renderRollX - camX;  if (far) rx >>= 3
        blit(s, rx - s.ox, y)                    // y already origin-adjusted
    }
```

The parked planes stand at altitude 0 with the anchor exactly on the base
line (no +11 as in 0x5174). Places are 64 px apart (8 px far). The rolling
plane leaves place `count` (after the decrement), which is no longer drawn.
**Confirmed.**

### Muzzle flash (0x0e88, render loop, right after each plane is drawn)

```
// (sx, sy) = the plane's anchor: the code restores it after blitting the plane
if (e.firing == 0 || far) skip
e.flashCount(+2c) += 1                // only increment; never reset except at a new game (0xe608)
k = e.flashCount & 3
if ((k & 1) == 0) skip                // draws on k = 1 and 3
idx = 16 + (k >> 1)                   // 16 or 17
if (e.facing < 0) idx += 2            // 18 or 19
s = japplaneShapes(-$69b8)[idx]       // 16 fc10, 17 fd10, 18 fc1a, 19 fd1a
blit2(s, sx - s.ox, sy - s.oy)        // 0x10e24, another blit routine than the plane's
```

- The sequence per frame is off, fc, off, fd, …. The phase carries across
  frames and slots.

| Shape | Size | Origin | Relative to the anchor |
| --- | --- | --- | --- |
| fc10 | 16 × 3 | (−7, 0) | x + 7 .. x + 22, rows y .. y + 2 |
| fd10 | 16 × 4 | (−7, 1) | x + 7 .. x + 22, rows y − 1 .. y + 2 |
| fc1a | 32 × 3 | (25, 0) | x − 25 .. x + 6, rows y .. y + 2 |
| fd1a | 32 × 4 | (25, 1) | x − 25 .. x + 6, rows y − 1 .. y + 2 |

  For comparison, jp10 / jp1a span x − 25 .. x + 22 and rows y − 6 .. y + 4.
  **Confirmed** (code and header data). The visual reading is **inferred**.
- The drawing reads +12 for any state. The sound reads it only for states
  1..2.

### Enemy sounds (0x21c6 inside 0x2132, logic tick right after 0xe7d6)

0x2132 returns at once while paused (`-$5aa8`) or when `-$5b07` is set
(probably sound off).

```
nearest = 0xffff;  any = 0
for each slot e:
    if (e.state == 0 || e.state > 2) continue           // states 1..2 only
    d = |e.x - P.x| + |e.alt - P.alt|                    // word; P = -$5f84 / -$5f86
    if ((uint16)d < (uint16)nearest) nearest = d
    any |= e.firing
engineOn(-$3c4e) = 0
v = (uint16)nearest >> 4                                 // 0x22ce
vol = (v > 44) ? 0 : (v <= 5) ? 64 - 4*v : 64 - (v + 20)
if (vol != 0) { engineVol(-$3c42) = vol;  engineOn = 0xff }
gunOn(-$3c66) = any                                      // any nonzero = on
```

- Volume is 64, 60, 56, 52, 48, 44 for v = 0..5, then 38 at v = 6 down to
  1 at v = 43, and silent from v = 44 (d ≥ 704). It is the nearest plane
  only; the volume does not change while silent. **Confirmed.**
- **Channel set-up** (0x1f76..0x1ff4, at sound load):
  - Gun: record at `-$3c66`, sample `machinegun` (`-$4168`, length
    `-$5a8c`), period 160, volume 57, loop −1. Fixed volume, so it does not
    fall off with distance.
  - Engine: record at `-$3c4e`, sample `Engine` (`-$41a6` / `-$5a84`),
    period 330, loop −1. Its volume is set as above.
  - The player's gun uses `-$3c96` (period 200, volume 64), and the
    player's engine `-$3c7e`.

  How the interrupt-side mixer starts and stops a channel from these flag
  words was not traced. They are taken as "play while nonzero" (**inferred**).

### Map j's battleship list as the port will read it

Template `-$7a32` (words): lo −200, hi 620, then 5 entries
(state, x, altitude, direction):

| Entry | State | x (from Hpx) | Altitude | Direction |
| --- | --- | --- | --- | --- |
| 0 | 0x8000 | 233 | 56 | −1 |
| 1 | 0x8000 | 507 | 47 | +1 |
| 2 | 0x8000 | 746 | 32 | +1 |
| 3 | 0x8000 | 194 | 56 | +1 |
| 4 | 0x8000 | 546 | 47 | −1 |
| 5 (read past the end) | −200 (0xff38) | 320 | −32768 | 29 |

- The per-map bytes `-$7ab0`[map × 2]: map j (9) has count **6**, max **2**.
  The others: k 5/2, l 4/2, m 5/2, n 5/3, o 5/2.
- The template that follows is the cruiser's `-$7a0e`: lo −200, hi 320,
  then (0x8000, 29, 62, +1), …. So entry 5 is made of the cruiser's lo, hi,
  first state word and first x. **Confirmed** (data dump).
- On map j, Hoff = anchor offset − 0x20 for anchor column 911: Hpx =
  911 × 8 − 128 = 7160. The window is 6960..7780 px. The entries are at
  7393, 7667, 7906, 7354, 7706 and 7480 (the ghost). **Confirmed**
  arithmetic, matching docs/maps.md (battleship x 7160..7935).
- Order: launches take entry count − 1 first, so the ghost (entry 5)
  launches first, as a fighter at (7480, −32768) heading left. Then come
  entries 4, 3, 2, 1, 0.
- **Drawing before launch:** entry 5 has state −200 ≠ 0, so 0x391e draws
  it with jp22 (direction 29 > 0) at altitude −32768 − sink. That wraps
  (word arithmetic) to about +32764, far off screen. **Confirmed**
  arithmetic; invisible (**inferred**).
- To reproduce it, the port can append that entry to the j battleship
  list. To skip it, use count 5. The ghost's effects (above) are then lost:
  it holds one of the 2 airborne places for about 8 minutes and can take
  rank 1.

## Open questions

- The render-loop rate, as in the other notes: it sets how often the muzzle
  flash and the engine volume update. AI and damage are in the logic tick.
- The pilot window's size offsets 28 and 84 (above): a bug or intended.
- 0x46c6 called by a crashing plane passes the altitude as a second argument,
  which the routine does not read. Is the "rocket-type" impact on the column
  deliberate (planes destroying huts and AA guns, scoring for the player)?
- What happens on the screen to the ghost plane's drawing once 10ce2 clips
  the y wrap (−32768 + base). Assumed invisible.
- The torpedo plane that misses its drop point (arrives below 20 or turning)
  keeps turning over the carrier; the exact path was not simulated.
- How the mixer starts and stops the enemy `machinegun` and `Engine`
  channels from the flags `-$3c66` / `-$3c4e` was not traced.
- Kill counter at the end of the game: only the dashboard reads `-$5c7f`;
  the high-score screen was not checked for it.
