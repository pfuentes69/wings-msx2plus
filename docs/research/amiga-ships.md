# Amiga enemy ships: executable findings

Recovered 2026-11-17 by static 68000 disassembly of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-island-combat.md](amiga-island-combat.md): code addresses are
CODE-hunk offsets, variables A4-relative, a tick is one 12.5 Hz logic tick,
fixed point is 16.16, and "map offset" is a byte offset into the map words
(column × 2; px = offset × 4). Nothing was observed running on an Amiga.
Each claim is marked **confirmed** (read directly from the code or data) or
**inferred** (a reading of what the code implies).

Timing: torpedo flight (0x0a72), the sinking clock (0x1cae), ship plane
launches (0x1510) and the hull and gun hit handler (0x46dc) run in the logic
tick. Ship gunfire and gun smoke (0x4c3e, called from 0x38d2) run in the
render loop, like the island guns.

## Summary

- Ships are static map objects. They never move. Each map has at most one
  ship of each type, held in one fixed 30-byte record per type.
- A ship has 4 to 15 small guns (14-byte records). Rockets knock out a gun
  (+200). Bombs and the cannon do nothing to ships.
- Only a running torpedo damages the hull. A hit takes one point off +$0c.
  Hits needed: destroyer 1, cruiser 1, battleship 2, Japanese carrier 3.
  At 0 the ship sinks 1 px per step for 120 steps. The bonus and the
  "%s sunk" message come at step 10, about 13 s after the last hit.
- Nothing in the code rejects a torpedo because guns are alive. But every
  live gun throws shell splashes at the player's x ± 32. Each splash destroys
  any torpedo within 10 px. A torpedo dropped near a defended ship is almost
  always destroyed under the plane. This is the manual's "guns must be
  disabled" rule.
- Torpedo: it must reach the sea within 13 ticks of falling (vertical speed
  ≥ −5 px/tick at the surface). In level flight that means altitude ≤ 41.
  It then runs at 4.3125 px/tick for 199 moves (≈ 858 px, 16 s). It hits
  the first non-sea column it reaches. It is invisible while running; only
  its wake of splashes shows.
- Ships also carry Japanese planes on deck and launch them as fighters
  while the player is near.

## Ship records (built by 0x2de8, cleared at 0x2d72)

The column scan 0x2de8 (see the island note) handles four anchor ids. A
second anchor of a type already seen is ignored, because of the per-type
"present" flag. **Confirmed.**

| Anchor id | Ship | Record | Present flag | Plane list | Shapes base (+$1c) | Archive |
| --- | --- | --- | --- | --- | --- | --- |
| 0xe4 (dstb) | Destroyer | `-$5b9e` | `-$5c84` | `-$5f68` | 0xd0 | `shapes/destroyer.shp` |
| 0x10d (batf) | Battleship | `-$5b80` | `-$5c87` | `-$5ee8` | 0xf8 | `shapes/battleship.shp` |
| 0xcc (crus) | Cruiser | `-$5b62` | `-$5c83` | `-$5ea8` | 0xb8 | `shapes/cruiseship.shp` |
| 0xf2 (jcrf) | Japanese carrier | `-$5b44` | `-$5c86` | `-$5e68` | 0 | `shapes/japcarrier.shp` |
| 0x21 | Player's (US) carrier | `-$5b26` | `-$5c85` | (`-$5f28`, unused) | 0 | |

The five records are contiguous (30 bytes apart). The pointer list `-$5aa4`
holds them in the order destroyer, US carrier, battleship, cruiser,
Japanese carrier, then −1. Most ship loops walk this list. **Confirmed.**

Each enemy anchor adds one to `-$5c8e` (ships afloat, shown on the briefing
screen at 0x86b4) and one to `-$5c8d` (ships still to sink for the mission).
Both are cleared at 0x2ae8. **Confirmed.**

### Record layout (30 bytes)

| Offset | Field | Battleship | Jap. carrier | Destroyer | Cruiser | US carrier | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| +0.w | Hull start H, map offset | anchor − 0x20 | anchor − 0x20 | anchor − 0x20 | anchor − 0x10 | anchor − 0xa0 | confirmed |
| +2.w | Hull end, map offset | H + 0xc0 | H + 0x9c | H + 0xa0 | H + 0x20 | H + 0xc0 | confirmed |
| +4.w | Present (−1). The US carrier's is cleared when it finishes sinking | −1 | −1 | −1 | −1 | −1 | confirmed |
| +6.l | Pointer to the gun array (14 bytes per gun, 0x350e, MEMF_CLEAR) | | | | | 0 | confirmed |
| +a.w | Gun count | 14 | 15 | 8 | 4 | 0 | confirmed |
| +c.w | Torpedo hits left. 0 = sinking, −1 = sunk and removed | 2 | 3 | 1 | 1 | 4 | confirmed |
| +e.w | Deck height (altitude) | 27 | 21 | 27 | 28 | 33 | confirmed (0x5866) |
| +10 | Not seen used | | | | | | inferred |
| +12.w | Bonus | 4500 | 6000 | 2500 | 1000 | 0 | confirmed |
| +14.w | Sink step 0..120 (also px sunk) | 0 | 0 | 0 | 0 | 0 | confirmed |
| +16.w | Countdown to the next sink step | not set (0) | 20 | 20 | 20 | 20 | confirmed |
| +18.w | Sink step interval; 20 at the fatal hit, then −1 per step | | | | | | confirmed |
| +1a.w | Render copy of +14 (0x101a, at the frame flip) | | | | | | confirmed |
| +1c.w | Base shape id of the ship's archive, for the cockpit 3-D view (0x4644) | 0xf8 | 0 | 0xd0 | 0xb8 | 0 | confirmed |

Hull start H in px is +0 × 4. With anchor column a (px A = 8a), H = A − 128
for the battleship, carrier and destroyer, and A − 64 for the cruiser.
Gun and plane positions below are relative to H. **Confirmed.**

### Footprint and hitbox

Every ship column has class 1 (word & 3), from an end marker id 0x111 to
an end marker id 0x112. The hull range +0..+2 (inclusive, 0x4a4e) covers the
same columns plus one. **Confirmed** from the maps and 0x4a4e.

| Ship | Class-1 columns | Length | Hull pieces (map id = archive shape) |
| --- | --- | --- | --- |
| Battleship | 96 | 768 px | 0x10d batf (bow, left), 0x10f btft, 0x10e batm, 0x110 btmt, 0x10c batb (stern, right): 3 × 256 px wide, 37..71 px tall |
| Japanese carrier | 74 | 592 px | 0xf2 jcrf (bow, left), 0xf3 jcrm, 0xf6 jrmt (island), 0xf1 jcrb |
| Destroyer | 80 | 640 px | 0xe4 dstb (stern, left), 0xe6 dstm, 0xe7 dtft, 0xe5 dstf (bow, right) |
| Cruiser | 16 | 128 px | 0xcc crus (128 × 106) |

The hit test is one-dimensional. A torpedo or rocket detonation over a
class-1 column (at the surface height, see below) is looked up by x alone in
0x4a4e. The order is destroyer, battleship, cruiser, Japanese carrier, and
the US carrier last and always. There is no vertical extent: the
superstructure is not a target. **Confirmed.**

The deck is a surface. 0x5714 returns +e − +14 − bob (`-$5c50`) for ship
ids. The US carrier also subtracts `-$5c68`. Ordnance detonates at deck + 11
over a ship column. The player's flight code (0xb0e2 and others) uses the
same deck height for touchdown and collision. **Confirmed** for ordnance;
the plane's deck behaviour is **inferred** (not fully traced).

### Where ships appear

Map index n is file letter a + n, as in the island note. Planes: number
carried / most airborne at once, from the per-map tables (0x252c).
**Confirmed.**

| Map | Ships (anchor column) | Planes |
| --- | --- | --- |
| f | cruiser 670 | 2 / 1 |
| g | cruiser 2346 | 3 / 1 |
| h | destroyer 2706 | 3 / 1 |
| i | destroyer 834; cruiser 2198 | 4 / 1; 2 / 1 |
| j | destroyer 17; battleship 911 | 4 / 2; **6** / 2 |
| k | battleship 774 | 5 / 2 |
| l | battleship 16; destroyer 1810 | 4 / 2; 3 / 2 |
| m | battleship 16; carrier 2766 | 5 / 2; 6 / 3 |
| n | battleship 16; destroyer 353 | 5 / 3; 4 / 2 |
| o | carrier 17; battleship 2591; destroyer 3399 | 7 / 3; 5 / 2; 4 / 2 |

## Drawing

- **Hull:** the map column renderer (0x3842) draws the anchor pieces from
  the global shape table `-$40aa`. 0x535a fills that table with the loaded
  archives: base ids 0..0xb7, cruiser 0xb8..0xcf, destroyer 0xd0..0xea,
  Japanese carrier 0xeb..0xf7, battleship 0xf8..0x110. Name lists:
  `-$732e`, `-$739e`, `-$73d6`, `-$743e`. For class-1 columns, 0x4eac adds
  the sink depth +1a and the wave bob to y. **Confirmed.**
- **Bob:** `-$5c50` = 1 + `-$63ba`[i] = 2, 3, 4, 3, 2, 3, 4, 3. Every ship
  and its deck bob together. **Confirmed.**
- **No damage art.** The archives hold only the intact pieces. Sinking draws
  the same pieces lower by +1a px. They are probably clipped at the
  playfield bottom (`-$46a0` = 0xa1). **Confirmed** (no other frames
  referenced); clipping **inferred**.
- **Cockpit 3-D view:** bb1..bba / bs1..bsa (battleship), db/ds
  (destroyer) and cl/cr (cruiser) are 10 distance sizes of the ship. The
  first set is used when the player faces right, the second when facing
  left (0x4610..0x4678). The carrier has none (+1c = 0) and uses a generic
  shape. **Confirmed.**
- **Flags:** the archives contain flg0..flg7. No code or map reference to
  them was found. **Open.**
- **Parked planes:** 0x391e draws every plane still in a ship's plane list:
  japplane jp21 (entry direction < 0) or jp22, at (x, altitude − sink).
  **Confirmed.**

## Guns

### Gun record (14 bytes, array at +6)

| Offset | Field | Confidence |
| --- | --- | --- |
| +4.w | x px (H + table) | confirmed (0x350e) |
| +6.w | altitude offset (0, but 5 for cruiser guns 2 and 3, set at 0x3312) | confirmed |
| +8.w | destroyed (−1) | confirmed |
| +a.w | smoke puffs left (50 on destruction) | confirmed |
| +c.w | smoke timer | confirmed |

The layout is the island AA gun record.

Positions, px from H (tables `-$59fc`, `-$59ec`, `-$59d0`, `-$59b2`):

| Ship | Guns | x |
| --- | --- | --- |
| Destroyer | 8 | 78, 88, 108, 118, 558, 568, 588, 598 |
| Battleship | 14 | 43, 53, 74, 84, 106, 116, 603, 613, 635, 645, 666, 676, 698, 708 |
| Japanese carrier | 15 | 63, 79, 102, 119, 144, 154, 181, 199, 424, 455, 486, 517, 548, 577, 601 |
| Cruiser | 4 | 24, 35, 89, 103 |

Most guns come in pairs 10 px apart, grouped at the two ends of the hull.

### Firing (0x4c3e, each render update)

Runs only while the player flies (mode 0). It skips the US carrier, absent
ships, and ships with +c ≤ 0 (sinking or sunk: their guns stop firing and
smoking). Each live gun, in list order, does the following. **Confirmed.**

1. **Shell splash (0x4efc).** d = |gun x − player x (`-$5f84`)|. It
   continues only if (rand & 511) > d, so beyond 511 px there is no splash.
   It then sets `-$42b4` (never read). If the player's altitude is ≤ 200,
   with probability 6/16 it makes a sea splash (0x52b0, the Splashes list)
   at player x + rand(−32..31). It then calls 0x1ae2(x, 10): every player
   torpedo, and the enemy torpedo `-$5a6a`, within 10 px of x explodes
   (state 8, no sound, no hull damage). So a live gun splashes with
   probability (1 − d/512) × 6/16 per update.
2. **Barrel:** frame from 0x4db8 (the island table: |dx| ≤ 512 in the
   near view; always frame 0 in the far view). Shape gun0 + frame (129..135),
   or gnf0 + frame (136..142, muzzle flash) when rand bit 15 is set (1/2;
   islands use 6/16). Drawn at altitude +e − +1a − bob + gun +6 + 13.
   In the far view (`-$60c8` = 1), shape 0x5a, drawn half the time.
3. **Hit-scan at the plane (0x4f5c):** the island routine, run whenever 0x4db8
   gave a frame. No hit beyond |dx| > 448. d = max(dx, alt) + min(dx,
   alt) / 4; a hit when (rand & 511) ≥ d and (rand & 2047) ≤ 409. A hit
   makes sparks, then hit counter −1; at 0, oil −1, fuel − rand(0..3),
   counter 6 + rand(0..7). It also sets `-$3baa` / `-$3ba8`, so the
   "under fire" sound plays with volume by the nearest gun's distance (0x38ea).

Guns are hit-scan. There are no shell objects. Splashes are effects that
only threaten torpedoes.

### Suppression

| Weapon | Effect on a ship | Confidence |
| --- | --- | --- |
| Rocket | Detonates at deck + 11 over the hull. 0x4986 → 0x49dc: white flash; the **first live gun in list order with \|x − gun x\| < 16** is destroyed: +8 = −1, +a = 50, +c = 1, score +200, red flash. One gun per rocket. | confirmed |
| Torpedo landing on the deck, or exploding while not running (frame ≠ 10) | Same as a rocket: kills one gun. | confirmed |
| Bomb | Explosion and sound only. 0x4992 returns for type 1: no gun or hull effect and no flash. | confirmed |
| Cannon | None. The surface strike 0x19bc only kills soldiers and torpedoes near the impact (0x1a8c) and makes a splash. | confirmed |
| Player crash on a deck | Crash outcome 3 (class 1). The rocket-type impact at 0xb326 runs only for outcome 1 (land), so no gun is lost. | confirmed |

A destroyed gun smokes like an AA gun. Each update the timer drops by 1;
at 0 the puff count drops by 1, and if puffs remain the timer becomes 50 −
count and a smoke effect (type 5) appears at (gun x, deck height). That is
up to 49 puffs, further apart each time. **Confirmed.**

Rocket auto-aim (0x099a → 0x11a6) re-aims at any gun of a ship with
+12.l ≠ 0. It does not check +8, so destroyed guns also attract rockets.
**Confirmed.**

Quirk: sinking never clears the gun records. After a ship is removed, a
rocket fired over the empty sea where a live gun stood still finds the ship
by range (0x4a4e). It "destroys" that gun for +200. **Inferred** from the
code paths.

## Hull, sinking and scoring

### Hull hits (0x4986..0x49d8)

Only a running torpedo (type 2 with frame +1e = 10) damages the hull. It
gives a white flash (`-$5be8` = 5), then red (0xf00). If +c > 0, then
+c −= 1. When +c reaches 0, +18 = 20 and sinking begins. No points are
scored for the hit itself. The guns are not checked. **Confirmed.**

Hit points: destroyer 1, cruiser 1, battleship 2, Japanese carrier 3, US
carrier 4. One torpedo per sortie (stock in the island note), so the
battleship needs 2 sorties and the carrier 3. The record is not rebuilt
when the player rearms. **Confirmed** (hits); multi-sortie **inferred**.

### Sinking clock (0x1cae → 0x1cd8, every logic tick)

For each record with +4 ≠ 0 and +c = 0:

- +16 −= 1; when it is ≤ 0: +14 += 1, +16 = +18, and +18 −= 1 unless it is
  already 0. The step intervals are I0, 20, 19, …, 1, then 1 tick each.
  I0 is the initial +16: 20, or 0 for the battleship, whose +16 is never
  initialised, so its first step comes 1 tick after the hit.
  **Confirmed.**
- Each step lowers the deck height (0x5714) and the drawing (+1a) by 1 px.
  There are no frames and no sound. **Confirmed.**
- **Step 10:** score += +12. 0x5640 formats ". . . %s sunk . . . BONUS %ld
  points . . ." into `-$3e94`. The name comes from table `-$7456`, chosen
  by the bonus value: 4500 Battleship, 6000 Carrier, 2500 Destroyer,
  anything else Cruiser. Then `-$5c8d` −= 1. If ships remain, or islands
  remain (`-$5c7b`), the message is queued (0x555a: only if no message is
  already pending, `-$5848` = 0). Otherwise 0x5694 appends "Good work ! …
  next mission" or "Congratulations! … mission!!" to the same buffer and
  advances the mission. Step 10 comes 164 ticks (13.1 s) after the fatal
  hit, or 145 ticks for the battleship. **Confirmed** (the queue-drop
  reading is **inferred**).
- **Step 120** (329 ticks, 26.3 s; battleship 310): `-$5c8e` −= 1, +c = −1,
  and every map word from +0 to +2 is cleared. The whole ship disappears
  from the map and those columns become sea. **Confirmed.**
- Guns, smoke and plane launches stop from the moment +c = 0 (0x4c3e and
  0x1574 test +c > 0). The carrier's deck roll (0x1510) has no such test.
  **Confirmed.**

The island check (0x3f82) also needs `-$5c8d` = 0 before it completes the
mission. So the mission ends when the last island or the last ship (at step
10) is done. **Confirmed.**

### The US carrier (bonus 0)

It sinks on the same clock after 4 torpedo hits: enemy torpedo planes
(`-$5a6a`), or the player's own torpedoes, since 0x4a4e always includes it.
- With `-$5c6a` = 1 it sets player mode 0xb. (Corrected 2026-11-17: the
  `move.w +12` after the step compare at 0x1cf6 sets the flags again, so the
  branch tests the bonus being 0, at any step, not step 1.)
- At step 33 a plane on deck (mode 1) goes to mode 6.
- At step 120 it clears +4 and sets `-$5a3d` (probably game over).
Enemy ships never attack the carrier. **Confirmed** control flow; meanings
**inferred**.

## Torpedo (type 2, ordnance record `-$6350`)

| Phase | Behaviour | Address | Confidence |
| --- | --- | --- | --- |
| Release | Same as any secondary weapon: in flight (mode 0), not in turn frames 6..16, stock `-$5c91` > 0. No altitude, speed, heading or range check at release. x = plane x; altitude = plane altitude + 11; v = the plane's velocity (vx × facing); frame 3/9; +1f = facing. | 0xb5b0, 0x088e | confirmed |
| Fall | Bomb physics: gravity 0.375 px/tick², vx −= trunc(vx/10). Drawn as Torpedo.shp tor2 (0x88, facing right) or tor7 (0x89), shape 9 in the far view. Only the integer altitude is kept (+6 is never written, so it stays 0). | 0x0b58, 0x0726 | confirmed |
| Surface | At altitude ≤ 12 over sea, or ≤ deck + 11 over a ship: splash sound 0x233e over sea, 0x2324 otherwise. Over a ship deck or land it explodes like a bomb, which on a ship kills a gun (see Suppression). Over sea it explodes if vy < −5 px/tick (high word < −5). Otherwise it runs: vx = ±0x45000 (4.3125 px/tick) by the sign of vx, frame 10, life +12 = 200. | 0x0bf0..0x0d32 | confirmed |
| Release envelope | It must reach the surface within 13 ticks of free fall: drop ≤ 40 px. In level flight, altitude ≤ 41; descending at 1 px/tick ≤ 36, at 2 px/tick ≤ 34. | simulated from 0x0b58/0x0d10 | inferred (arithmetic) |
| Run | Each tick: life −1, freed at 0 (199 moves, ≈ 858 px, 16 s). x += vx. Not drawn; a splash effect (0x52b0) at its x every tick is the wake. Constant speed, no depth or energy model. | 0x0d50..0x0d9e | confirmed |
| Hit | The first tick its x is over a non-sea column (class ≠ 0) it explodes: impact handler 0x46dc with frame 10, then sounds 0x2324 + 0x233e and the sea explosion (0x65 + frame). On a ship this is the hull hit above. On land it is a non-rocket impact (huts and dugouts react; AA guns do not). | 0x0d70..0x0d92 | confirmed |
| Miss | When life runs out it simply vanishes: no explosion and no sound. The path also calls 0x52b0 with a stale d4 (probably a harmless extra splash). | 0x0d58 | confirmed; d4 **inferred** |
| Destroyed | Any splash from a live ship gun within 10 px (above). Any bomb or rocket impact, or cannon strike, at x kills torpedoes in [x − 48, x + 16]: 0x1a8c calls 0x1ae2(x − r, 2r) with r = 16, an asymmetric window. | 0x1ae2, 0x1a8c | confirmed |

During the fall vx is kept (below 10 px/tick), so the torpedo stays under
the plane. Then the shell splashes at plane x ± 32 cover it: a hit has
about a 21/64 chance per splash. With all guns down there are no splashes,
and the torpedo can only be lost by the player's own fire. **Inferred**
(probabilities from the code above).

## Ship-launched planes (plane lists, 0x252c, 0x1510, 0x1574)

Each list is 64 bytes. **Confirmed.**
- Header: +0 count, +2 most airborne at once, +4 / +6 player-x window
  (H + lo, H + hi).
- Up to 7 entries of 8 bytes: +0 state (0x8000 parked, 1 rolling), +2 x,
  +4 altitude, +6 direction (drawing only).

| Ship | Window (from H) | Parked planes (x, altitude, dir) |
| --- | --- | --- |
| Destroyer | −200..620 | (194, 51, +), (525, 40, −), (484, 40, +), (234, 51, −) |
| Battleship | −200..620 | (233, 56, −), (507, 47, +), (746, 32, +), (194, 56, +), (546, 47, −) |
| Cruiser | −200..320 | (29, 62, +), (115, 69, −), (76, 69, +) |
| Japanese carrier | −250..20 | (604..439 in steps of 33, 16, −) × 6, (459, 16, −) |

The per-map count takes the first n entries. Launches use the last one
first.

- **Launch (0x1574, logic tick):** when the shared cooldown `-$3cb6` is 0,
  for each ship with bonus ≠ 0 and +c > 0, if player x is in the window and
  airborne enemy planes (`-$5e28`) < the maximum and count > 0: count −1
  and launch a fighter (0xe4d0 kind 0) at the entry's (x, altitude),
  heading −1 (left). Cooldown 100. **Confirmed.**
- **Carrier deck roll:** instead of launching at once, the Japanese carrier
  marks its last entry rolling, at x = H + 380, altitude 33 (cooldown 100).
  0x1510 then moves it left each tick by v >> 4, with v = v − (v >> 4) + 8,
  so up to about 8 px/tick. Once x < H, count −1 and it takes off as a
  fighter. **Confirmed.**
- On map j the battleship launches 6 planes from a 5-entry table. The sixth
  (launched first) reads the cruiser table's header: x = H + 320, altitude
  −32768. **Confirmed** data; effect **open**.

## Sounds

| Event | Sound | Confidence |
| --- | --- | --- |
| Torpedo meets the sea | 0x233e splash | confirmed |
| Torpedo or rocket or bomb meets a deck | 0x2324 boom | confirmed |
| Running torpedo hits a ship or land | 0x2324 boom and 0x233e splash | confirmed |
| Ship guns firing | "Under fire" loop, volume 64 − dist/8 (`-$3e98`/`-$3e9a`) | confirmed |
| Gun destroyed, hull hit, sinking, torpedo destroyed by a splash | none found (flash only) | confirmed |

Both sound routines scale volume by distance from the plane
(0x2306: |dx| + |altitude − 20|).

## Open questions

- The render-loop rate, as in the island note. This sets the real splash
  and hit-scan rates of ship guns.
- What the plane does on and against an enemy deck (0xb0e2: rest on it, or
  pushed back with an explosion when the column 5 back is sea). Not traced
  to the final outcome.
- What the j-map battleship's sixth plane (altitude −32768) does in the
  enemy plane code.
- Whether the ship flag shapes (flg0..flg7) are drawn anywhere; and the role
  of `cmsk` (id 0xf7, drawn at H + 409 over the carrier, 0x39d6). It is
  named in the list but absent from japcarrier.shp, as are jrbf and jrbt.
- Record field +10 (no use found).
- `-$5c6a` states (carrier deck sequences) and `-$5a3d`, needed to describe
  the US carrier sinking precisely.
- Whether a message pending in `-$5848` really drops the "sunk" message.
