# Amiga player crash, wreck and sinking: executable findings

Recovered 2026-11-20 by static 68000 disassembly (Capstone) of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-fuel-oil.md](amiga-fuel-oil.md),
[amiga-island-combat.md](amiga-island-combat.md),
[amiga-ships.md](amiga-ships.md) and
[amiga-enemy-planes.md](amiga-enemy-planes.md). Code addresses are CODE-hunk
offsets (file offset = 0x28 + address). Variables are A4-relative. A tick is
one 12.5 Hz logic tick. Speeds are in hundredths of a px per tick. "Column"
means the map word under an x (0xc982: x / 8, clamped to the map). Class is
`word & 3`: 0 sea, 1 ship or carrier, 2/3 island. Nothing was observed
running on an Amiga. Each claim is marked **confirmed** (read directly from
the code or data) or **inferred** (a reading of what the code implies).

Player record `-$5f86` (`-$3212` points to it): +0 altitude, +2 x, +4 shape
pointer, +8 shape name (4CC), +$c mode, +$e fuel, +$12 oil, +$14 facing
(−1 left, +1 right), +$16 horizontal step, +$18 vertical step. Speed is
`-$5bea`, commanded climb `-$5bfc`, turn frame `-$5bf0`.

Timing: the flight handler 0xc660 and everything in it (0xafba, 0xaed8,
0xaf7c, 0xba80) runs in the logic tick. Explosions (0x06be), splashes
(0x52f8) and smoke puffs (0x0ee0) advance once per drawn frame in the render
loop (0x0228). The render rate is unconfirmed (probably 12.5 Hz, as noted in
the other research files).

## Summary

- **There is one crash mechanism.** Every loss goes through mode 4
  ("engine dead", 0xc74e). Mode 4 calls the crash routine 0xafba every tick.
  0xafba makes the plane fall, then slide on the surface, then picks the
  final mode: **6 (sinking)** or **8 (wreck)**. Modes 6 and 8 run for
  **150 ticks (12 s)**, or until fire is held after 30 ticks. Then 0x35ce
  blanks the playfield for 20 VBlanks (0.4 s) and puts a new plane on the
  lowered elevator. **Confirmed.**
- **How mode 4 starts.** There are two ways (**confirmed**):
  - Engine failure in the air (oil < 96 or fuel < 0, 0xc6a0). Gunfire never
    kills the plane directly; it only drains oil and fuel.
  - Any surface contact in mode 0 that is not a landing or a bounce
    (0xba80). That covers the sea, island ground, huts, trees, AA guns, any
    ship, and the carrier outside the landing rules.
- **In the air (mode 4)** there is no power and no control. Speed stays the
  same; there is no drag. The vertical step drops by 1 per tick, down to
  −10 px/tick. The nose goes down 6° per tick until −31° (`hc09`). There is
  no spin, fire or explosion in the air. Engine smoke continues only if the
  oil is damaged. **Confirmed.**
- **On the surface** the plane slides level (`hc05`, no wheels). Each tick
  x moves by speed / 100 and the speed drops by 85. It stops after 9..16
  ticks and 38..115 px. **Confirmed.**
  - **Sea:** two splashes per tick, ahead of the nose. No sound.
  - **Island:** each tick, a ground explosion with a boom on the plane's
    column, a white screen flash, a rocket-type impact on the column (huts,
    AA guns and manned dugouts are destroyed and score), and soldiers within
    8 px die.
  - **Deck:** silent, no explosion. The plane follows the deck's bob.
- **End state:**
  - Sea, or a ship deck lower than altitude 20 → **mode 6, sinking.**
    Altitude −1 every 3 ticks. The nose turns down `hc05` → `hc0a` over 17
    ticks. The plane goes behind the opaque wave strip, which is drawn over
    it. Silent water bursts (`spl0..spl5`) appear for the first 75 ticks.
  - Island or deck → **mode 8, wreck.** The shape is `hcr5` (facing right)
    or `hcrf` (facing left). A fire puff (`smk5`, which then fades into
    smoke) appears every 4 ticks. Land explosions with booms appear at
    random intervals (1..12 ticks) for the first 75 ticks.
- **Flames `flm0..flm3` are never used.** No code or data refers to the name
  `flm`. There is no bail-out, no parachute, no message and no score
  penalty. **Confirmed.**
- **Nothing remains.** The wreck is the player object itself. At the next
  plane, all 40 smoke effects and all 15 explosion slots are cleared (the
  explosion clear also cancels a running enemy torpedo). Parked spare planes
  on the deck = planes left − 1, so one fewer appears. Map damage the crash
  caused stays (wrecked huts, dead AA guns and soldiers, ship guns).
  **Confirmed.**
- **Last plane:** while the last plane's wreck burns or sinks, the "THE END"
  plate (`gmov`) is drawn. When the 150 ticks end, the game is over at once,
  with no black-out. **Confirmed.**

## Outcomes table

S = speed at impact = horizontal step × 100 (1000..1400 in level flight).
Slide = 9..16 ticks. "Wait" = 150 ticks in mode 6/8, or 31 with fire held.

| Case | How it is detected | Modes | What is shown | Sound | Ends in |
| --- | --- | --- | --- | --- | --- |
| Fly into the sea | 0xba80 contact (altitude − bottom ≤ 0 over class 0) → mode 4 | 0 → 4 (slide) → 6 | `hc05` slides; 2 splashes per tick at x + 8 × facing; then sinks nose-down behind the waves; water bursts | engine note 25/960 while sliding, then silence; no splash sound | slide + 150 |
| Engine dies in the air (oil < 96 or fuel < 0) | 0xc6a0 | 0 → 4 → (fall) → surface case below | nose to `hc09`, constant forward speed, accelerating descent; smoke puffs only if oil damaged | engine note 25/960 | fall + slide + 150 |
| Island ground | contact over class 2/3 (surface height 0 on bare ground) → mode 4 | 0 → 4 → 8 | explosion 16 px ahead at contact, then one per tick at the column under the plane; white flash every tick; then `hcr5`/`hcrf` burning | boom at contact and every slide tick; booms during the wreck | slide + 150 |
| Hut, dugout, AA gun, tree, camouflage | contact when altitude − bottom < object height (tree 36/35/35, `cama` 35, hut 13, AA gun 12, dugout 9, minus word bits 11..13) → mode 4 | 0 → 4 (falls through the object to the ground) → 8 | as island; the contact impact wrecks a hut (+150), kills an AA gun (+200) or empties a manned dugout (+200) | as island | fall + slide + 150 |
| Carrier deck, bad landing (turning, > 4 px into the deck, or carrier gone) or outside the landing range | 0xba80, not a landing candidate → mode 4 | 0 → 4 → 8 | explosion 16 px ahead + white flash (altitude ≥ 20); silent slide on deck; burning wreck bobbing with the deck | boom at contact, booms in the wreck | slide + 150 |
| Carrier or ship hull side (first ~40 px of the hull crossed from the sea) | 0xafba outcome 3, the column 5 behind is sea | 0 → 4 → 6 | pushed back, red flash (7 frames), explosion; falls straight down into the sea and sinks | boom | fall + 150 |
| Enemy ship deck | as the carrier deck | 0 → 4 → 8 (6 if deck + 2 < 20, the Japanese carrier at high bob) | as deck; the contact impact destroys the first live gun within 16 px (+200) | as deck | slide + 150 |
| Carrier tower or superstructure | no collision: tower columns (0x22) have the deck height | n/a | flies through | | |
| Roll off the deck end / overshoot | 0xc5f4 → mode 0 (take-off); if too slow, falls into the sea | 1 → 0 → sea case | | | |
| Gear "up" | not a cause: gear is automatic (0xb45a) | | | | |
| Carrier sinks with the player on deck | 0x1d7e at carrier sink step 33 | 1 → 6 | sinks; planes = 0; game over countdown 100 | | game over |

## Mode 4 entry points

### 0xc6a0, engine failure (mode 0)

```
if (oil < 96 || fuel < 0) {
    signalmen = 3                   // -$5c9f, see "Side effects"
    mode = 4
    speed = hstep * 100             // last horizontal step (px/tick) x 100
    crash()                         // 0xafba, same tick
}
```
**Confirmed.**

The check at 0xc6de (altitude ≤ −7 → mode 6 with the counters cleared) is
in practice unreachable. Contact (below) switches to mode 4 at altitude ≤
bottom (≥ 2), and the mode-0 integration floor is −4. **Inferred.**

### 0xba80, contact in mode 0

Contact (0xb8c4): `alt − bottom < surface(column)` or `alt − bottom ≤ 0`.
Surface 0x5710: 0 for sea, bare island, beaches, wrecked huts (id 5),
balloons and the ship end markers 0x111/0x112. Static heights from
`-$583c`, minus word bits 11..13: tre1 36, tre2 35, tre3 35, cama (11) 35,
dugo (3) 9, huta (4) 13, pila..pilp (15..30) 12. Every carrier and ship
column (including the tower 0x22) returns the live deck height: record +e −
sink − bob, minus heave for the US carrier. **Confirmed.**

A "landing candidate" needs all of:
- x inside the landing range (carrier extents inset 16 px);
- turn frame 0;
- altitude ≥ deck + bottom − 4;
- `-$5b22` set (the US carrier record +4: "present").

Then:

| Contact | Result | Confidence |
| --- | --- | --- |
| Candidate, facing left, landing flag `-$5554` | land (mode 1), sound 0x2380 | confirmed |
| Candidate otherwise | bounce: vertical step and climb negated, altitude + 6, sound 0x2380 | confirmed |
| Not a candidate | **crash**: mode 4, speed = hstep × 100. Unless the column is sea, or a ship column with altitude < 20: explosion 0x0820(column of x + 16 × facing, altitude, land) and rocket-type impact 0x46c6(column of x). Then 0xafba in the same tick | confirmed |

So inside the landing range the plane also crashes when it is turning,
when it ends the tick more than 4 px under the deck (a steep sink), or when
the carrier is gone. Speed is not checked at touchdown. This corrects
"inside the range otherwise: bounce" in
[amiga-fuel-oil.md](amiga-fuel-oil.md). **Confirmed.**

The 0x46c6 call on a ship column at altitude ≥ 20 reaches the ship handler
0x4986 → 0x49dc. That is a white flash, plus the first live gun with
|x − gun x| < 16: destroyed, +200, red flash. The US carrier has no guns
(flash only). This corrects the "no gun is lost" row in
[amiga-ships.md](amiga-ships.md). That row is right only about the
per-tick impact at 0xb326. **Confirmed.**

## Mode 4 handler (0xc74e) and the crash routine (0xafba)

0xc74e, every tick: engine target volume 25 and base pitch 960
(`-$5bd6`/`-$5bd4`); throttle, fire flag and `-$5bf6` cleared; signalmen
state 3; `-$5560` = −1; then 0xafba. The controls (0xbff4) are not called,
so input is ignored. **Confirmed.**

0xafba (locals: bottom = 0xaaea, `col` = column under x):

```
outcome = isSeaOrOffMap(col) ? SEA : isShip(col) ? DECK : LAND   // 0xcb74 class 0 / 0xcb34 class 1
onSurface = falling = 0
switch (outcome) {
case SEA:                                             // 0xb01a
    if (alt <= bottom) { clearPose(); alt = bottom()   // pose idx 0 -> bottom 2
                         onSurface = 1
                         splash(x + 8*facing) }       // 0x52ac
case LAND:                                            // 0xb070, object heights ignored
    if (alt - bottom <= 0 && turn == 0) {
        clearPose(); alt = bottom(); setPose(); onSurface = 1
        explode(col, alt - 1, LAND)                   // 0x0820: boom
    } else falling = 1
case DECK:                                            // 0xb0e2
    step = speed/100 * facing
    deck = surface(col) + bottom
    if (alt <= deck) {
        if (isSeaOrOffMap(col - 5*facing)) {          // 40 px behind: the hull side
            x -= step + 4                             // +4 not multiplied by facing (quirk)
            speed = 0
            flash(7, red)                             // 0xcab4(7, 0xf00)
            deck = 2                                  // the final-mode test now uses 2
            explode(col, alt, LAND)
        } else { onSurface = 1; clearPose(); alt = surface(col) + bottom() }
    }
}
// 0xb1bc: an unfinished turn steps 2 frames a tick (below 14 back to 0; from 14 on to the end, facing flips at 14)
if (turn != 0 && alt <= deck_or_bottom) {
    if (outcome != LAND) alt = surface(col) + turnBottom(turn)     // 11, or -$54fe
    x += speed/100 * facing
    -> skip to FALL
} else if (onSurface) {                               // 0xb2aa: the slide
    x += speed/100 * facing
    speed -= 85; if (speed < 100) speed = 0
    if (outcome == SEA) splash(x + 8*facing)
    else {
        explodeBuggy()                                // 0xb304, see quirk
        if (outcome == LAND) { impact(col)            // 0x46c6: rocket-type, white flash
                               killSoldiers(x, 8) }   // 0x1a84
    }
} else {                                              // 0xb340: in the air
    climb -= 600; if (climb < -3100) climb = -3100
    falling = 1
}
FALL: if (falling) {                                  // 0xb35c
    vstep -= 1; if (vstep < -10) vstep = -10
    alt += vstep
    if (alt - bottom() <= 0) { alt = bottom(); explode(col, alt - 1, LAND) }   // ground at 0, any class
    x += speed/100 * facing
}
// 0xb3e6: final mode
if (speed == 0 && turn == 0 && alt <= deck_or_bottom) {
    mode = (isSeaOrOffMap(col) || (isShip(col) && alt < 20)) ? 6 : 8
    oil = 0; rec[+$1a] = 0
    crashClock = nextBoom = sinkDiv = 0               // -$5558, -$5556, -$555a
}
```
**Confirmed** control flow.

Notes:
- The falling branch tests only `alt − bottom ≤ 0` (ground 0). Over a ship,
  the next tick's DECK case catches the deck. Over island objects, the plane
  falls through them to the ground. **Confirmed.**
- Explosion `explode(col, h, flag)` (0x0820) takes a free player-ordnance
  slot (15 slots; it gives up silently if none is free). It sets x =
  column × 8, world altitude h + 12, state 8, type 1, frame 1. With flag 0:
  land art and the boom 0x2324(x). With flag ≠ 0: sea art and no sound. It
  does not run an impact. **Confirmed.**
- **Quirk (0xb304):** the slide explosion calls 0x0820 with (x.w, alt.w,
  0.l) instead of (column pointer.l, alt.w, flag.w). The "pointer" is
  (x << 16 | alt), so the explosion x becomes ((alt − map base) × 4) mod
  65536. That is a fixed garbage spot set by where the map was allocated,
  with altitude 12, land art and a boom. The boom is silent beyond 2047 px
  (0x22f6: volume 64 − d/32). **Confirmed** arguments; the visible and
  audible effect is **inferred** (usually off-screen and silent). The port
  should leave it out.
- The impact at 0xb326 runs **every slide tick on land**. Its white flash
  (`-$5be8` = 5) is renewed each tick, so the background flickers white for
  the whole slide. A hut on the path is wrecked (+150) and an AA gun gets
  damage bits (+200 on the first). A manned dugout gives +200 once (the
  garrison leaves). Soldiers within 8 px die (+25 each, scream). Island-clear
  bonuses can follow. **Confirmed** calls; effects as in
  [amiga-island-combat.md](amiga-island-combat.md).
- On the deck, the slide re-reads the surface each tick, so the plane rides
  the bob and heave. **Confirmed.**

### Slide length

Integer speed / 100 per tick, −85, zeroed below 100 (the first surface tick
also moves):

| Horizontal step at impact (px/tick) | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Slide ticks until mode 6/8 | 9 | 10 | 11 | 12 | 13 | 15 | 16 |
| Slide distance (px) | 38 | 48 | 59 | 71 | 84 | 99 | 115 |

**Confirmed** (computed from the rule). An unfinished turn delays the end by
up to 7 ticks (the turn must reach frame 0).

### Fall after engine failure

The vertical step keeps its value at failure, then drops 1 per tick to −10.
From level flight that is a drop of n(n+1)/2 px after n ≤ 10 ticks (55 px),
then 10 px/tick. Forward speed is constant (speed / 100 px/tick). Climb
drops 600 per tick from its value to −3100, so the pose goes toward `hc09`.
Gear is off (0xb45a: gear only in mode 0 near the carrier, and in modes 1,
7, 11), so bottom = 2 in level poses. **Confirmed.** Above altitude 186 the
far view (`lpn` shapes) is used until the plane drops below. **Confirmed**
(0xc966).

## Mode 6: sinking (0xc78c)

Each tick:

```
engineVolume = 0
if (++sinkDiv > 2) { sinkDiv = 0; alt -= 1 }      // 1 px every 3 ticks
climb -= 250; if (climb < -4500) climb = -4500
crashEffects()                                     // 0xaed8
crashClock()                                       // 0xaf7c
```

- **Pose.** 0xc378 → 0xabde (default branch): shape = `-$521e`[(climb +
  5000) / 500], mirrored by facing (0x5b58). Climb starts at 0 (cleared on
  the surface). The poses run: ticks 1–2 `hc05`, 3–4 `hc06`, 5–8 `hc07`,
  9–12 `hc08`, 13–16 `hc09`, then `hc0a` from tick 17 onward. No wheels.
  **Confirmed.**
- **Position.** x does not change. Altitude starts at 2 (bottom), so after
  150 ticks it is −48. Screen y of the plane's origin = camera base −
  altitude, with base 151 at low altitude. **Confirmed.**
- **How it disappears.** The plane is drawn in the scene pass (0x03a6). The
  wave strip (0x3e6c, `wava`..`wavl` 96×11, origin y 10) is drawn after it,
  at rows base..base+10. Rows base+2 and below are fully opaque; rows base
  and base+1 are crests with gaps. So the sea hides the plane from row 153
  down. The player's bottom clip `-$46a0` = 161 (the playfield bottom) does
  not matter here. `hc0a` (origin y 18) is gone completely at altitude ≤
  −20, about tick 66 (5.3 s). **Confirmed** draw order and opacity; the
  timing is computed.
- **Water bursts.** See "Crash effects" (sea art, silent).
- No smoke or puffs: engine smoke is skipped in modes 6/8 (0x1bfc), and
  mode 6 spawns none. No splash list entries. **Confirmed.**
- **Quirk:** if the torpedo is still selected and loaded, the renderer
  (0x0520) keeps drawing the torpedo overlay from `torpedo.shp` under the
  sinking `hc05..hc0a`. **Confirmed** control flow.

## Mode 8: wreck (0xc7c6)

Each tick:

```
name = (facing == -1) ? 'hcrf' : 'hcr5'            // +8; 0xc378 skips the pose code for mode 8
poseIdx(-$5a6c) = 0                                // bottom = 2
alt = isShip(col) ? surface(col) + bottom : bottom // rides the deck bob, heave and sink
if ((++puffClock(-$437a) & 3) == 0)                // free-running: every 4 ticks
    smoke(x + 8*facing + rand(0..7), max(16, alt + 17), type 6)   // 0xcae0 -> 0x54cc
crashEffects()                                     // 0xaed8
crashClock()                                       // 0xaf7c
```

- `hcr5` and `hcrf` are mirror copies of a crumpled `hc05`: belly down,
  bent propeller, no wheels. `hcr5` has the propeller on the right (facing
  right, the stored orientation of `hc05`); `hcrf` faces left. **Confirmed**
  (pixels and origins 25 / 23 of 48).
- The renderer draws modes 1, 7, 8 and 11 at the record altitude directly
  (0x03ae..0x045c). **Confirmed.**
- **Fire puff, type 6:** shape `smk5` (fire colours) for 7 drawn frames,
  then `smk4`, `smk3`, `smk2`, `smk1`, `smk0` for 7 frames each (42 frames
  in all). It drifts right and up by 1.0..2.0 px per frame (random per
  puff). It is drawn 6 px above the plane's origin. That is a column of
  smoke drifting downwind with a flicker of fire at its base. **Confirmed.**
- **Quirk:** with the torpedo selected and loaded, the overlay lookup of
  `hcr5` in `torpedo.shp` fails (0x10560 returns 0). The renderer then draws
  through a null shape pointer. **Inferred** (the port must not draw an
  overlay in mode 8).

## Crash effects (0xaed8), modes 6 and 8

```
h = alt - bottom();  sea = (mode == 6);  if (sea) h = 0
engineVolume = 0
if (crashClock < 75 && crashClock >= nextBoom) {
    nextBoom = crashClock + (rand & 12)            // 0, 4, 8 or 12
    explode(column(x + (rand & 15) - 8), h, sea)   // sea: silent water burst; else land burst + boom
}
```

- The first burst comes on the first tick of mode 6/8. A draw of 0 fires
  again on the next tick, so the gaps are 1, 4, 8 or 12 ticks (6.25 on
  average). That is about 12 bursts in 6 s, x within −8..+7 px snapped down
  to the 8-px column. **Confirmed.**
- World altitude h + 12. On land and in the sea that is ground level; on a
  deck it is the deck. **Confirmed.**
- Explosion frames (0x0702): one per drawn frame, frames 2..7, then the
  slot is freed. Land: world shapes 0x59 + f = `exp0..exp5`. Sea: 0x65 + f
  = `spl0..spl5`. 6 frames in all. The screen y of the origin is base + 11
  − (h + 12). **Confirmed.**

## Crash clock and the next plane (0xaf7c, 0x35ce)

```
if (planesLeft == 1 || planesLeft == 0) theEnd = 1          // -$5ca2, -$5c9c: 0x10c2 draws gmov each frame
crashClock++                                                // -$5558
if (crashClock == 150 || (crashClock > 30 && (input & 0x30)))
    nextPlane()                                             // 0x35ce
```

0x35ce:

```
blackFrames = 20; planesLeft -= 1
x = carrierX; turn = 0; facingCopy = -1                     // 0x35d8
clear all 40 smoke effects
if (planesLeft <= 0 || usCarrier.hull <= 0) { theEnd = 1; gameOver = 1; planesLeft = 0; return }
signalmen = 3
newPlaneInit()                                              // 0x3684: clears all 15 ordnance slots AND the enemy torpedo -$5a6a,
                                                            // weapon = bombs, stock refilled, flash off, speed 0,
                                                            // elevator state -$5c6a = 1, heave 32, camera base 151,
                                                            // flight frozen (-$5c9a), new record 0xb7ec (mode 1, fuel 192, oil 128)
fill playfield rows 0..161 with colour 0; present; WaitTOF x 20  // 0.4 s PAL black-out, crash only
```

**Confirmed.** The `0x30` input bits are the two fire bits: bit 5 releases
weapons and bit 4 fires the gun in 0xb5b0. **Inferred** from 0xb5b0. Fire
does nothing else in modes 4/6/8 (0xb5b0 acts only in modes 0 and 1).

A mission start (0x35a8 → 0x35d8) skips the decrement and the black-out.
After the black-out, the elevator sequence is the same as at a mission
start ([carrier-elevator.md](../carrier-elevator.md)). **Confirmed.**

### Timings from impact

| Case | To mode 6/8 | Mode 6/8 | Then | Total (12.5 Hz) |
| --- | --- | --- | --- | --- |
| Sea / land / deck at step 10..14 | 11..16 ticks | 150 ticks (31 with fire) | 0.4 s black | 13.0..13.4 s (3.4..3.9 s with fire) |
| Hull side | fall time (vertical step −1 per tick from the impact value) | 150 | 0.4 s | ≈ 12.5 s + fall |
| Engine failure at altitude A | fall (55 px in 10 ticks, then 10 px/tick) + slide | 150 | 0.4 s | |
| Last plane | as above, "THE END" plate from the first mode-6/8 tick | 150 (31) | game over at once, no black-out | |

The camera keeps following the plane: camera x = x − 160, base = 151 +
max(0, altitude − 131). At the black-out it jumps to the carrier with the
new plane. **Confirmed.** Dashboard warnings (lamps, fuel jitter) are off in
modes 4/6/8 (0xee38). The oil needle falls to 0 (oil = 0 at mode 6/8
entry). **Confirmed.**

## Side effects and sounds

| Item | Detail | Confidence |
| --- | --- | --- |
| Engine | Mode 4: target volume 25, base pitch 960 every tick. Modes 6/8: volume 0 | confirmed |
| Boom 0x2324 | Every 0x0820 with flag 0: contact on land or deck (altitude ≥ 20), the land touchdown after a fall, every land slide tick, the hull hit, the mode-8 bursts. Volume 64 − (\|x − player x\| + \|20 − alt\|) / 32, 0 beyond 2047 | confirmed |
| Splash sound 0x233e | Never called by the crash code | confirmed |
| Touchdown 0x2380 | Landing and bounce only | confirmed |
| Scream 0x23ac | Each soldier killed by the slide | confirmed |
| White flash | Contact impact on land or ship; every land slide tick | confirmed |
| Red flash | Hull hit (7 frames); impact on a target | confirmed |
| Signalmen `-$5c9f` = 3 | Earlier notes read this as "sound 3". It is the deck signalmen's state: 0x3bce draws `fgy` shapes (0x8f + frame), and state 3 moves both to frame 0 (`fgy0`, `fgy8`), the same as flying above altitude 80 | confirmed data; visual meaning inferred |
| Enemy fighters | Target speed 1700 while the player is in mode 4/6/8 (see the enemy note) | confirmed |
| Score | No penalty. Only the crash's impacts score (hut 150, AA gun 200, manned dugout 200, ship gun 200, soldier 25, island bonus) | confirmed |
| Spare planes | 0x3abc draws planes left − 1 `Cpln` on the deck (at most 8), so one fewer after 0x35ce | confirmed |
| Map | Wrecked huts, AA guns, dugouts emptied, dead soldiers and ship guns stay. No player wreck is stored | confirmed |
| Carrier | A crash does not damage the US carrier hull | confirmed |
| Bail-out, parachute, messages | None: no shapes (all archive names listed), no strings | confirmed |

## Shapes

Sizes are stored width × height (width is a multiple of 16), with the inked
extent in brackets. Origins are given as (x, y).

| Shape | Archive | Size | Origin | Frames | Used for | Confidence |
| --- | --- | --- | --- | --- | --- | --- |
| `hcr5`, `hcrf` | hellcat.shp | 48×11 (41×11) | (25,8), (23,8) | 1 each (mirror pair) | mode-8 wreck | confirmed |
| `hc05`..`hc0a` | hellcat.shp | 48×13, 17, 23, 27, 32, 36 | (25, 8/8/11/13/16/18) | 6 | slide (`hc05`), sinking dive; mirrored at run time | confirmed (already in the port) |
| `exp0`..`exp5` | world.shp | 16×10, 32×13, 32×17, 32×18, 32×19, 32×18 (13..25 wide) | (9,9) (10,12) (15,16) (11,17) (14,18) (13,17) | 6 | land/deck bursts | confirmed |
| `spl0`..`spl5` | world.shp | 32×7, 32×7, 32×8, 32×13, 32×10, 32×8 (6..21 wide) | (15,2) (15,2) (16,3) (16,8) (16,5) (16,3) | 6 | sinking water bursts (0x0820 sea) | confirmed |
| `spl6`..`spl1` | world.shp | `spl6` 32×3 (19×3), origin (14,−2), then as above | | 6 (played `spl6`, `spl5` … `spl1`) | slide splashes (0x52ac, timer 6 → 1); drawn at world altitude 13 (row base − 2) | confirmed |
| `ric0` | world.shp | 16×5 | (8,7) | 1 × 4 frames | a slide splash whose x falls on land | confirmed |
| `smk5`, `smk4`..`smk0` | world.shp | 16×10, 16×10, 8, 6, 4, 3 | (8,5) (8,5) (9,4) (8,3) (2,2) (3,1) | 6 stages × 7 frames | wreck fire puffs (already in the port for smoke) | confirmed |
| `wava`..`wavl` | world.shp | 96×11 | (16,10) | 12 | the wave strip that covers the sinking plane (already in the port) | confirmed |
| `gmov` | world.shp | 192×22 (184×22) | (99,11) | 1 | "THE END", drawn at (160, 81) | confirmed |
| `Cpln` | world.shp | 32×15 | (14,47) | 1 | spare planes on the deck | confirmed |
| `fgy0`, `fgy8` | world.shp | | | | signalmen state 3 | confirmed |
| `flm0`..`flm3` | world.shp | 16×5, 16×8, 16×9, 16×12 | (8,2) (6,4) (8,5) (8,6) | 4 | **not referenced** | confirmed (no name in code or data) |
| `spl0`..`spl3` | hellcat.shp | 16×9, 16×8, 16×6, 16×10 | | 4 | in the hellcat name list (bank 0x6b..0x6e) but never drawn; not crash art | confirmed |
| `hc41`, `hcoc` | hellcat.shp | 48×16, 64×15 | | | not referenced (`hc40` is deck-turn frame 7) | confirmed |
| 8thscale `exp0..5`, `smk0/1` | 8thscale.shp | 16×2..3 | | | far view only (altitude > 186); a crash always ends in the near view | confirmed |

## Pseudo-code (for the port)

Units: altitude in the player's scale (world shapes are drawn at world
altitude = player altitude + 11), x in px, speed in px/100 per tick, one
tick = 12.5 Hz (12 steps of the port's 150 Hz clock). `bottom` is 2 for
level poses with the gear up.

```c
// ---- entry (mode 0) ----
on engine failure (oil < 96 || fuel < 0):          enterCrash();
on contact && !landingCandidate:                   // see 0xba80
    if (!(sea(col) || (ship(col) && alt < 20))) {
        explode(colX(x + 16*facing), alt, LAND);   // boom, white flash on ship or land
        impactRocket(x);                           // hut/AA/dugout/ship gun, +score
    }
    enterCrash();

enterCrash(): mode = 4; speed = hstep*100; fire = 0; throttle = 0;
              engine(vol 25, pitch 960); signalmen = 3; crashTick();

// ---- mode 4, each tick ----
crashTick():
  out = sea(col) ? SEA : ship(col) ? DECK : LAND;
  floor = (out == DECK) ? deckHeight(col) + bottom : bottom;   // LAND ignores object heights
  onSurf = 0;
  if (alt <= floor && !(out == LAND && turn)) {
      if (out == DECK && sea(colBehind(5)))  {     // hull side
          x -= speed/100*facing + 4; speed = 0; flash(RED, 7);
          explode(col, alt, LAND); floor = 2;      // falls on into the sea
      } else {
          onSurf = 1; climb = 0; pose = LEVEL; alt = floor;
          if (out == SEA)  splash(x + 8*facing);
          if (out == LAND) explode(col, alt - 1, LAND);
      }
  }
  stepTurn(2);                                     // finish or unwind an open turn
  if (onSurf && turn == 0) {
      x += speed/100*facing;
      speed -= 85; if (speed < 100) speed = 0;
      if (out == SEA)  splash(x + 8*facing);
      if (out == LAND) { impactRocket(x); flash(WHITE, 5); killSoldiers(x, 8); }
      // omit the 0xb304 stray explosion
  } else if (!onSurf) {
      climb = max(climb - 600, -3100);
      vstep = max(vstep - 1, -10); alt += vstep;
      if (alt <= bottom) { alt = bottom; explode(col, alt - 1, LAND); }
      x += speed/100*facing;
  }
  if (speed == 0 && turn == 0 && alt <= floor) {
      mode = (sea(col) || (ship(col) && alt < 20)) ? SINKING : WRECK;
      oil = 0; clock = 0; nextBoom = 0; div = 0; engine(vol 0);
  }

// ---- mode 6, each tick ----
sinkingTick():
  if (++div > 2) { div = 0; alt--; }
  climb = max(climb - 250, -4500);
  pose = poseFromClimb(climb);                     // hc05 -> hc0a over 17 ticks, mirrored
  effects(SEA); crashClock();
  // draw the plane BEFORE the wave strip; the strip (rows base..base+10, opaque from base+2) hides it

// ---- mode 8, each tick ----
wreckTick():
  shape = facing < 0 ? hcrf : hcr5;
  alt = ship(col) ? deckHeight(col) + 2 : 2;       // rides the bob
  if ((++puffClk & 3) == 0)
      smoke(x + 8*facing + rand(8), max(16, alt + 17) /*world alt*/, FIRE /*smk5 then smk4..0*/);
  effects(LAND); crashClock();

effects(kind):
  if (clock < 75 && clock >= nextBoom) {
      nextBoom = clock + (rand() & 12);
      h = (kind == SEA) ? 0 : alt - 2;
      explode(colX(x + (rand() & 15) - 8), h, kind);   // SEA: spl0..5, silent; LAND: exp0..5 + boom
  }

crashClock():
  if (planesLeft <= 1) showTheEnd = 1;
  if (++clock == 150 || (clock > 30 && firePressed)) nextPlane();

nextPlane():
  planesLeft--;
  clearAllSmoke(); clearAllExplosions(); cancelEnemyTorpedo();
  if (planesLeft <= 0 || carrierHull <= 0) { gameOver(); return; }   // no black-out
  newPlaneOnLoweredElevator();                     // as at mission start, weapon = bombs
  blankPlayfield(20 VBlanks /* 0.4 s */);

explode(x, h, kind):  // x snapped to 8 px; world altitude h + 12; 6 frames, one per drawn frame
  if (kind == LAND) boom(volume = 64 - (|x - px| + |20 - alt|)/32);
```

## Corrections to earlier notes

- [amiga-fuel-oil.md](amiga-fuel-oil.md): "mode 4, sound 3" and "mode 6,
  crash sound" come from `-$5c9f` = 3, which is the deck signalmen state, not
  a sound. Contact inside the landing range also crashes when the plane is
  turning, more than 4 px into the deck, or the carrier is gone.
- [amiga-ships.md](amiga-ships.md): the first contact with a ship deck at
  altitude ≥ 20 runs the rocket-type impact (0xbbf0), so it can destroy a
  gun (+200).
- [amiga-hiscores.md](amiga-hiscores.md): 0xaf7c runs once per logic tick,
  not per frame, so 150 means 12 s and 30 means 2.4 s.

## Open

- The render-loop rate, which sets the duration of the 6-frame explosions
  and splashes and of the 42-frame puffs.
- What the stray slide explosion (0xb304) shows on real hardware. It depends
  on the map buffer's address.
- The null-pointer torpedo overlay in mode 8.
- Which fire bit is which (0x10 / 0x20) is only inferred.
