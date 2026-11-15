# Amiga island combat: executable findings

Recovered 2026-11-14 by static disassembly of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-fuel-oil.md](amiga-fuel-oil.md): code addresses are CODE-hunk
offsets, variables A4-relative, a tick is one 12.5 Hz logic tick, and fixed
point is 16.16. Nothing was observed running on an Amiga.

Timing: projectiles (0x0a72), soldier spawning (0x1de4) and gun-hit soldier
kills (0x19bc) run in the logic tick. Soldier walking (0x3eee) and
dugout/AA fire (0x3d78/0x3de8, called from 0x3772) run in the render loop
(0x0228). The render rate is unconfirmed (probably 12.5 Hz).

## Ground targets

**Footprint.** Each island object takes 4 map columns (32 px), with the
anchor (bit 15) on the third. For anchor column x A = column × 8, it covers
[A − 16, A + 16). Words: dugo (id 3) 0x000e, huta (id 4) 0x0012, pila
(id 15) 0x003e. Mission A has dugouts at A = 1736 and 3224 and huts at 2392
and 2712. There are no AA guns.

**Runtime lists**, built by 0x2de8 (counts) and 0x310c (fill) from anchor
words:

| id | Object | Count | List | Record |
| --- | --- | --- | --- | --- |
| 4 | huta: barracks hut | `-$5c77` | `-$5b06` | 16 bytes |
| 3 | dugo: machine-gun dugout | `-$5c78` | `-$5b02` | 16 bytes |
| 15 | pila: large AA gun (pila..pilp, ids 15..30, are damage states) | `-$5c79` | `-$5afa` | 14 bytes |
| | soldiers | `-$5c3a` = (huts + dugouts) × 5 | `-$5afe` | 8 bytes |

**Hut and dugout record:**

| Offset | Field |
| --- | --- |
| +0.l | anchor's map offset (px = offset × 4) |
| +4 / +6 | soldier exit x: A / A for a hut; A − 44 / A + 16 for a dugout |
| +8.b | garrison, 5 |
| +9.b | island |
| +a.b | soldiers waiting to come out |
| +b.b | release timer |
| +c.w | hut: smoke puffs; dugout: fire delay |
| +e.w | hut: smoke timer; dugout: reinforcement timer |

**AA gun record:** +0.w map offset, +6.w island, +8 destroyed (−1), +a
smoke count, +c smoke timer.

**Islands** (up to 4; the index advances at each bchr, id 2):

| Table | Contents |
| --- | --- |
| `-$5bae` | 4 bytes per island: +0 soldiers left (5 per hut and per dugout), +2 AA guns left |
| `-$5bbe` | first and last dugout |
| `-$5bce` / `-$5bc6` | bchl / bchr offsets (the island's ends) |

**Hits.** Rockets, bombs and torpedoes detonate on reaching altitude
12 over land or sea (deck height + 11 over the carrier). There is no
height test against objects: the id-3/4 height path at 0x0c0a..0x0c2c is
unreachable. The impact handler 0x46dc takes the impact x, reads the column
(0x50c8), finds the anchor within columns −1..+2 (0x4ae4) and the record by
map offset (0x4b54). So the hitbox is exactly the object's 32 px.

- **Hut (id 4), any weapon, one hit:** all 4 columns become 0x16 (id 5, hutb,
  the wrecked hut), keeping bit 15. Score +150. Smoke: +c = 50, +e = 1;
  0x4e18 emits up to 49 puffs (effect type 5 at x + 16, altitude 17), the
  gap growing as 50 − count. 0x4b40 moves the garrison out: +a += +8, +8 = 0,
  +b = 60 (ticks to the first release).
- **Dugout (id 3), any weapon:** the map never changes; dugouts cannot be
  destroyed. If manned (+8 ≠ 0): score +200, +e = 200, and the garrison comes
  out (0x4b40). It scores again if soldiers re-man it.
- **AA gun (ids 15..29), rockets only (`$22` = 0):** a damage bit (1 − column
  offset from the anchor; bits 3..0 over the 4 columns) goes into the id
  (15 + bits), written to all 4 columns. The first hit destroys it: +8 = −1,
  +a = 50, +c = 1 (smoke at x + 8, altitude 17), score +200, island guns −1.
  Later hits only add damage art.
- **id 275 (0x113): the island flag.** Not a target (0x471a). Drawn by
  0x3b52 as a waving flag (flg0..flg2, ids 176..178) while the island has
  soldiers or guns left, then POST (id 179, a bare pole). It sits in the
  column after the first hut on every map.
- **Other ids above 183:** 0x10d / 0xf2 / 0xe4 / 0xcc are the enemy ships
  (0x5640: battleship 4500, carrier 6000, destroyer 2500, cruiser 1000
  points). 0x114 / 0x115 (276/277) bound a zone in `-$5d04` (4 × 20 bytes,
  parameters per map at `-$7b0a`) from which 0x1622 launches enemy planes
  (0xe4d0) when the player is within ±480 px, cooldown 100: probably an
  airstrip. In it, at altitude ≤ 30, bombs bounce (vy = −vy/2, at most 9;
  vx halved; removed when either reaches 0) and rockets vanish
  (0x0b88..0x0be8).

**Flash.** A rocket impact sets `-$5be8` = 5, `-$5be6` = 0xfff: a white
background flash on alternate frames (0x031a), red (0xf00) when it hit a
target.

## Soldiers (`-$5afe`, 8 bytes)

Fields: +0.w x, +2.b direction (sign), +3.b frame, +4.b death delay, +5.b
island, +6.w state (0 free, 1 walking, 2 dying, 3 dead).

- **Release (0x1de4, each tick):** for each hut or dugout with +b ≠ 0, +b
  counts down; at 0 one soldier comes out (0x1e82) and +a −1; if more wait,
  +b = (`-$5c34` >> 4) & 31, or 3 if 0. Position exit x + (dir & 7) × 4,
  frame dir & 3. Hut soldiers get a random direction. Dugout soldiers: from
  the island's leftmost dugout dir +1 (exit A + 16, walking right), from the
  rightmost dir −1 (exit A − 44, walking left), others random; 1/32 chance
  of flipping. Soldiers appear only when their building is hit.
- **Reinforcement:** an unmanned dugout counts +e down from 200; at 0, 0x4fee
  takes one soldier (+8 − 1) from the nearest hut on the island that still
  holds at least 2, and sends it toward the dugout.
- **Walking (0x3eee, render loop):** x ± 3 px per update; if the next x is
  sea (class 0) it turns round instead. Frames guy0..guy4 (ids 111..115)
  facing right, guy9..guyd facing left (near view); a 2-frame animation from
  `-$407c` in other views. A soldier reaching a dugout column re-mans it: if
  its +c = 0 and +8 = 0 then +c = 360 (fire delay); +8 + 1; the slot is
  freed (the island count is unchanged).
- **Death (0x1a8c(x, r)):** any walking soldier within r of x dies (state 2,
  frame 5, delay 2). r = 16 for bomb or rocket impacts (0x0cc0) and gun
  strikes on the ground (0x19f6), 8 for the player's crash (0xb338), 20 for an
  enemy crash (0xe318). Frames 5..8, 3 updates each, then state 3 (corpse
  guy8, or gy11 facing left), score +25, `-$42c2` + 1, island soldiers − 1,
  island check. Dead slots are not reused.
- Soldiers never shoot. Each building has its 5 and no more.
- Recovered 2026-11-15 (step 4):
  - Release order: dugouts, then huts, each tick (0x1de4).
  - A dugout soldier's direction: +1 if the dugout is the island's first
    (`-$5bbe`), −1 if its last, otherwise random; then flipped when
    rol(rand, 1) & 31 == 0.
  - The kill test (0x1a8c) is (x_s − (x − r)) ≤ 2r unsigned: both ends
    inclusive.
  - Each death calls 0x23ac: a sample (`-$4152`) with period 0x17c and
    a random pitch from 0x2306, probably the scream.
  - Walking re-mans any dugout the soldier ends inside (the column id is 3,
    and 0x4b54 finds the record within columns −1..+2); a manned one just
    gains a soldier.
  - Reinforcement (0x4fee → 0x5034): huts are scanned in order; the hut
    must be on the dugout's island with +8 ≥ 2. The distance is from the
    dugout's +4 exit, and a tie goes to the later hut. The soldier leaves
    the hut with direction ±1 toward the dugout.

## Ground fire (0x4d50, 0x4f5c)

Manned dugouts (+8 ≠ 0, after the +c delay) and live AA guns, once per
render-loop update, when the player flies (mode 0) within |dx| ≤ 512:

- **Barrel:** frame = `-$63e2`[((altitude >> 5) − 1) × 8 + dx / 40 + 3], read
  as a linear byte array (rows spill), from −8: `0,1,2,3,0,1,2,3 |
  0,0,0,3,3,6,6,6 | 0,1,1,3,3,5,5,6 | 1,1,2,3,3,4,5,5 | 1,2,2,3,3,4,4,5 |
  2,2,3,3,3,3,4,4 | 1,2,3,2,1,2,3,2`. Shape gun0 + frame (ids 129..135), or
  with probability 6/16 the muzzle flash gnf0 + frame (136..142), at
  altitude 20 (dugout) or 22 (AA gun). In the far view: 50% shape 0x5a.
- **Hit:** hit-scan. Miss beyond |dx| > 448. d = max(dx, alt) + min(dx,
  alt) / 4. Miss if `-$408c` (probably invulnerability). Hit if
  (rand & 511) ≥ d and (rand & 2047) ≤ 409: about 20% × (1 − d/512) per gun
  per update. A hit spawns sparks at the plane (0x54e0, effect 6) and runs
  damage site 0x4f9e: hit counter −1; at 0, oil −1, fuel − rand(0..3),
  counter 6 + rand(0..7).
- Side effects: `-$3baa` under fire, `-$3ba8` nearest gun distance.
- Recovered 2026-11-15 (step 3):
  - 0x4d50 returns no shape unless the player's mode (`-$5f7a`, record
    +$0c) is 0 (flying). The caller (0x3dca) skips the hit-scan whenever no
    shape is drawn. So in the far view the gun fires only on the half of
    the updates that show `expl`, and never beyond |dx| > 512 in the near
    view.
  - The far-view flag is `-$60ca` (3 when `-$60c8` = 1, above altitude
    186); the `-$60c8` = 1 branch in 0x4db8 is unreachable after it.
  - The barrel table is indexed from −17 (altitude < 32, dx −512) to 47
    (altitude 186, dx +512). Bytes −17..−1 are other constant tables
    (`-$63f6` is a 4-byte pattern read at 0x0662): `2, 2,3,3,3,1,2,3,3,
    0,1,2,3,0,1,2,3`.
  - The shape is drawn by 0x5174 (`-$7eea`) at x = gun anchor and
    y = 11 − 20 + base − origin, the same placement as the effects.
  - `-$408c` is toggled by a debug key (0xd184, which also refills the oil
    and clears the mode). It is not a game mechanic.
  - The spark (0x54e0 with d0 = 6) is an effect of type 6 at the plane's
    nose. Its shape 0x60 + 6 = 0x66 is `smk5`; after 7 updates the type
    drops to 5 and it continues as an ordinary smoke puff.
  - A new plane sets the hit counter to 6 + 0xcac8(4), i.e. 6 + rand(0..3)
    (0xb82c).
- Not island fire: 0xde52 is enemy fighter fire, 0x4efc ship flak.

## Scoring and objectives

Score `-$5cb2` (long), cleared at 0x3568.

| Event | Points | Address |
| --- | --- | --- |
| Soldier | 25 | 0x3f40 |
| Hut | 150 | 0x4824 |
| Dugout (manned) | 200 | 0x4758 |
| AA gun | 200 | 0x491a |
| Ship gun | 200 | 0x4a3a |
| Enemy plane (probably) | 350 | 0xb750 |
| Ship sunk | table above | 0x1d10 |

**Island cleared** (0x3f5e, 0x492a): soldiers left = 0 and AA guns left = 0,
so all 5 × (huts + dugouts) soldiers must die, including those still inside.
Bonus 0x5ae8(island) = `-$7b82`[map × 4 + island]. Map index =
`-$7b9f`[theatre × 4 + mission]; theatre `-$5c40` (0..6), mission `-$5c3e`
(from 1); missions per theatre `-$5ab6` = 3, 3, 2, 2, 1, 1, 3. Map index by
theatre: [_, 0, 1, 2], [_, 3, 4, 5], [_, 6, 7], [_, 8, 9], [_, 10], [_, 11],
[_, 12, 13, 14].

| Map | Island bonuses |
| --- | --- |
| 0 | 450 |
| 1 | 500, 700 |
| 2 | 1000, 600, 750 |
| 3 | 1500, 1100 |
| 4 | 1000, 900, 1500 |
| 5 | 900, 900 |
| 6 | 900, 1200, 1200 |
| 7 | 900, 1600, 1000 |
| 8 | 1500, 1300, 1300 |
| 9 | 0 |
| 10 | 1600, 1500, 2000 |
| 11 | 2400, 0, 2500 |
| 12 | 3000, 2000, 2200, 2800 |
| 13 | 2500, 3000, 3200 |
| 14 | 3000, 3000, 3500 |

Message: "All enemy forces on island have been destroyed . . . Bonus %ld
points . . .". **Mission complete:** `-$5c7b` counts islands with at least
one hut, dugout or AA gun; each cleared island takes one off. At 0 with no
mission ships left (`-$5c8d`), 0x5694 advances the mission ("Good work! …
return to carrier…", or "Congratulations! You have completed your
mission!!").

## Player ordnance (`-$6350`: 15 × 42 bytes; one more at `-$5a6a`)

Fields: +0.l x, +4.l y, +8/+a screen position, +c.b state copy, +e.l vx,
+12.l vy (torpedo: life), +16.l ax, +1a.l ay, +1e.b frame, +1f.b surface at
impact, +20.b state (0 free, 0xff flying, 8 exploding), +21.b explosion
frame, +22.w type (0 rocket, 1 bomb, 2 torpedo), +24.w ignition delay,
+26.w angle, +28.w launch speed.

- **Stock** `-$6405` = 15 rockets, 30 bombs, 1 torpedo; one counter `-$5c91`
  refilled on selection (0xff infinite). Selected weapon `-$5c5a` (default
  1, bombs). Fire: 0xb5b0 (not while turn frame is 6..16) → 0x107c → 0x07f2,
  one per press.
- **Launch:** plane position (altitude + 11), plane velocity (vx negated
  facing left).
- **Rocket:** angle `-$5bfa` / 2 on the 1024-step sine table `-$6692`
  (Q15); acceleration ±2 cos a, 2 sin a (up to about 1 px/tick²); frame
  clamp(4 − (`-$5bfa` >> 5), 0..9) + 10 facing left. Ignition after 4, 8
  or 12 ticks (8 twice as likely): until then it falls 1 px/tick and drifts
  back 1 px/tick. Then vx += ax, vy += ay, x += vx, y += vy + ay; no gravity
  or drag. Removed beyond 1280 px from the player. Auto-aim at ignition
  (0x099a, probably), only when fired downward: if a ship or live AA gun lies
  between the ground points of angles a − 20 and a + 20, it is re-aimed
  (atan2, 0x5ca6) at speed `-$5bea` / 100.
- **Bomb (0x0b58):** each tick vx −= trunc(vx / 10) (only above 10 px/tick),
  x += vx, vy −= 0.375 (`-$5cae` = 0x6000), y += vy. Tumble frame from 3 or
  9, cycling 0..11 every other draw.
- **Detonation:** sound 0x2324 (land) / 0x233e (sea); 0x46dc on the impact
  column; explosion state 8: shapes 0x59 + frame on land, 0x65 + frame on
  sea, frames 2..7 (bank `-$41b4`). Soldiers within 16 px die; nearby
  torpedoes detonate (0x1ae2). No blast radius against buildings beyond the
  32-px footprint.
- **Torpedo:** over sea with vy ≥ −5 it runs at ±4.27 px/tick (0x45000) for
  200 ticks; over land it explodes like a bomb.

0x0820 places an explosion at a map position (crashes); crashes also run a
rocket-type impact (0x46c6 → 0x46dc) at the crash x.

## Open

Render-loop rate; the units of `-$5bfa` and `-$5bea`; `-$5a6a`; the
airstrip zone in full.
