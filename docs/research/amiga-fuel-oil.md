# Amiga fuel, oil, damage and engine failure: executable findings

Recovered 2026-11-14 from `reference_assets/original_files/Wings_of_Fury/wings`
by static 68000 disassembly (Capstone). Nothing was observed running on an
Amiga. Code addresses are offsets into the CODE hunk (file offset = 0x28 +
address); data offsets are A4-relative (`d - 0x7FFE`), as in
[amiga-cannon.md](amiga-cannon.md).

## Clock

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| 0x2940: `AddIntServer(5, server 0x1754)` | The game's interrupt server runs on vertical blank (INTB_VERTB) | Established |
| 0x1778: counter `-$3c9c` reloads to 4; every 4th interrupt queues one joystick sample and increments `-$3caa` | One logic tick per 4 VBlanks | Established |
| 0x14f0: `jsr $1386` repeats while `-$3caa` > 0 | Logic catches up per queued tick | Established |

**One logic tick = 4 VBlanks = 12.5 Hz on a PAL Amiga (15 Hz NTSC).** At the
port's 150 Hz simulation clock, one original tick is 12 steps.

## Player state

The player record is at `-$5f86(a4)`; `-$3212(a4)` points to it.

| Offset | Field | New plane (0xb7ec) | Confidence |
| --- | --- | --- | --- |
| +0 | altitude | 0 | Established (also [amiga-cannon.md](amiga-cannon.md)) |
| +$0c | mode | 1 (on deck) | Established |
| +$0e | fuel | **192** (`$c0`) | Established |
| +$10 | hit counter | 6 + random(0..3) | Established |
| +$12 | oil | **128** (`$80`) | Established |

Fuel burn period `-$3e96` = **28 ticks** (0xb8b4). Debug key handlers reset
fuel or oil to 128 (0xcf50, 0xd17a); they are not the game's refill.

Mode dispatch (0xc94c, 12 entries): 0 flying (crash checks at 0xc6a0), 1 on
deck, 4 engine failure (0xc74e), 6 and 8 crash outcomes (0xb428/0xb434 also
clear oil), 7 another warning-enabled mode. Other modes are not yet mapped.

## Burn, leak and failure

Per logic tick, unpaused, in mode 0 only (0x1386):

- **Fuel** drops by 1 every 28 ticks: 192 × 28 ticks ≈ **7.2 minutes** of
  flight at 12.5 Hz.
- **Oil** stays at 128 until the engine is damaged. Below 128 it leaks 1 every
  80 ticks (6.4 s), so damage progresses until repaired. Established.
- **Failure** (0xc6a0, mode 0): `oil < 96 || fuel < 0` → mode 4, sound 3.
  Mode 4 clears the fire flag (no gunfire) and the throttle flag `-$3216`.
  Established.

## Damage

| Site | Effect | Confidence |
| --- | --- | --- |
| 0x4f9e, random and distance-scaled | Hit counter −1; at 0: oil −1, fuel −random(0..3), counter = 6 + random(0..7) | Established control flow; attacker identity not mapped |
| 0xde52 | Hit counter −1; at 0: oil −8, fuel −random(0..31) | Established control flow; attacker identity not mapped |
| 0x1c18 | Smoke level from `128 − oil`: none at 0; light levels for 1..19 (`(d<<3)&0xf0` + random(0..15)); a heavier path above 19 | Control flow established; smoke rendering not mapped |

## Instruments (0xee5e..0xf000)

Gauge face `gaug` (dash shape 115) at x 208 (OIL) and 431 (FUEL), y 18;
lamp `olof`/`olon` (shapes 3/4) at x 202/424, y 10; needle `ndl1 + frame`
(shapes 92..114).

| | OIL | FUEL |
| --- | --- | --- |
| Needle target frame | `(oil − 96) / 2`, 0 below 96; **+6 while throttle `-$3216` is set and mode ≤ 1** | `fuel / 8`, at most 22; at frame 0 (with warnings) it jitters randomly between frames 0 and 1 |
| Full reading | 128 → frame 16 (`ndlg`), 22 under throttle | 192 → frame 22 (`ndln`) |
| Lamp | blinks while `oil < 116` | blinks while `fuel ≤ 64` |
| Blink | counter 10: about 9 ticks on, 2 off | counter 8: about 7 on, 2 off |

Warnings (lamps, jitter) are enabled only in modes 0, 1 and 7 (0xee38). The
displayed needle moves one frame per update toward its target, so it sweeps
smoothly. The throttle flag is set while horizontal input matches the heading
(0xc0f6..0xc10e) and cleared on engine failure.

These explain the reference panel: OIL at `ndlg` and FUEL at `ndln` is a new
plane at full oil and fuel, not two arbitrary needle positions.

## Engine failure (mode 4, 0xc74e) and crash outcome (0xafba)

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| 0xc74e sets `-$5bd6` = 25 and `-$5bd4` = 960, read only by the sound routine at 0x2132 | Engine sound: target volume and base pitch. Pitch rises with speed (`>>7`) and altitude (`>>4`); a failed engine changes the note. Other modes use 40/808, 49/385, 64/335 | Established |
| 0xc74e clears `-$3216` (throttle) and `-$5c94` (fire); runs 0xafba every tick | No power or guns; the descent and impact are handled by the crash routine, not by the mode-0 flight controls | Established control flow |
| 0xafba tests the surface under the plane (0xcb74, 0xcb34) | Three outcomes (sea, carrier, island). On impact it zeroes speed and pose, clamps altitude to the surface, and continues the sequence | Control flow established; descent arithmetic not mapped |

## Not yet recovered

Engine-out flight physics, crash and splash presentation, refill in the hold,
what crashes on contact with the sea or deck, and which attackers cause each
kind of damage.

## Landing and contact (0xba80, 0xb8c4, 0xc2ce)

Recovered 2026-11-14 with the same method.

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| 0xaaea | The plane's bottom offset below its origin: per pose (`-$5552`): 2, 12, 10, 6, 4, 2, 5, 7, 9, 12, 14; plus gear down (`-$553c`): 5, 4, 3, 3, 3, 5, 3, 2, 1, 0, 0; turn frames use `-$54fe` (2, 2, 4, 6, 10, 11) | Established (DATA values) |
| 0x5710 | Surface height from the map word's object id (`(word >> 2) & 0x1ff`): static classes ids 6 / 7 / 8, 11 / 3 / 4 / 15..30 have heights 36 / 35 / 35 / 9 / 13 / 12 (table `-$583c`), minus word bits 11..13. Carrier ids `$1f`..`$27` and `$9f`, and ships, read live object records (deck = record `$e` − `$14` − bob − heave). All other ids are 0 | Established |
| 0xb8c4 | Contact when `altitude − bottom < surface` (strictly below) or ≤ 0. Resting exactly on the surface is not contact, so takeoff is safe | Established |
| 0xb7bc | Landing range = carrier map extents × 4, 16 px inward at each end | Established |
| 0xc2ce | While UP alone (input bit 0) is held facing left, the commanded climb approaches +600 (6°) and flag `-$5554` is set; facing right clears it (corrected 2026-11-14: an earlier reading had horizontal speed) | Established |
| 0xba80, mode 0 contact | **Landed (mode 1)** when inside the landing range, at most 4 px into the deck, not turning (`-$5bf0` = 0), `-$5b22` set, facing left and `-$5554` set: altitude snaps onto the deck; speed is unchanged. Inside the range otherwise: **bounce** (vertical velocity negated, +6 px). Outside the range: **crash** (mode 4, explosion via 0xafba) | Established control flow; `-$5b22` is only read (probably "carrier present") |
| 0xc6de | Altitude ≤ −7 (into the sea) → mode 6, crash sound | Established |

There is no cable geometry in the touchdown rule itself, but the cables do
matter after it: see "On the deck" below (0xb92e).

## Flight model (0xbff4 controls, 0xbdfa integration, 0xc378/0xabde pose)

Recovered 2026-11-14. All per 12.5 Hz logic tick. Input bits (`-$42bc`):
0 UP, 1 DOWN, 2 RIGHT, 3 LEFT. Facing `$14(player)`: −1 left, +1 right.
Acceleration step `-$50e8` = 600 (DATA; debug keys change it by 50).

**Airspeed `-$5bea`** (1000..1400):

- Pushing in the facing direction: counter `-$3214` += 1 (max 8), speed +=
  counter, at most 1400; throttle flag set.
- Pushing the other way starts a turn (0xab80).
- No horizontal input: counter −= 1 (min 4), speed −= counter while above
  1000.

**Commanded climb `-$5bfc`**, in hundredths of a degree (−4500..+3000):

| Input | Change per tick |
| --- | --- |
| Horizontal + UP | +600 above speed 1000; +150 facing right / +75 facing left below it; max +3000 |
| Horizontal + DOWN | −600 (−300 while turning); min −4500 |
| DOWN alone | −1200; min −4500 |
| Horizontal alone, or nothing | a positive climb decays by 600 to 0; a dive is kept. While turning: −150 per tick down to −2250. Small climbs (0..500) are cancelled out of the flight path (`-$5bf6`) |
| UP alone, facing left (stall) | approaches +600 by 600 per tick; landing flag `-$5554` set |
| UP alone, facing right | −600 per tick; below −600, climb −= (climb + 600) / 2, which converges on −1200 (nose down); landing flag cleared |

**Flight path `-$555c`** moves a quarter of the way to (climb + `-$5bf6`)
each tick. Stalling facing left at exactly +600 makes it approach −800
instead: the flare is nose up (pose) but sinking at 8°.

**Integration (0xbdfa)**, with angle a = |path| / 100 degrees:

- horizontal step (`$16`) = fix((speed × turn[t] × cos a + 50) / 100);
  x += step × facing;
- vertical step (`$18`) = fix(speed × sin a / 100), negative when the path is
  down; altitude += step.
- Below speed 1000 (mode 0): if UP is not held, climb −= 300 (min −4500), and
  the vertical step −= (1000 − speed) / 100.
- Ceiling: altitude 1100 (clamp; climb negated; vertical step −half).
  Floor: −4.
- sin/cos come from a 91-entry table by degree (`-$548a`). Entries 1..4 all
  equal sin 4° (0.0698), so the smallest nonzero angle acts like 4°; the rest
  is sin(degree) to four decimals.
- Turn factor `-$54f2` by turn frame 0..25: 1.0, 0.98, 0.95, 0.91, 0.86,
  0.81, 0.75, 0.70, 0.60, 0.50, 0.40, 0.30, 0.23, 0.20, 0.0, 0.05, 0.25,
  0.45, 0.60, 0.70, 0.75, 0.81, 0.86, 0.91, 0.95, 0.98.
- At speed 1000–1400 the horizontal step is 10–14 px per tick
  (125–175 px/s).

**Pose:** index = (climb + 5000) / 500 selects a pose from `-$5526`: 10, 10,
9, 9, 8, 8, 7, 7, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1. Pose 5 is level (`hc05`),
10 the steepest dive and 1 the steepest climb. A stall at +600 shows pose 4.

Vertical input alone (Up or Down without a direction) changes neither the
airspeed nor the acceleration counter; only the no-input branch bleeds speed.
Down alone sets the throttle flag (engine note).

**Landing direction:** the landing flag is set only facing left, and the
landing check (0xba80) requires facing left, so this executable lands right
to left only. The gear comes down either way (0xb45a), so a left-to-right
approach looks like a landing but bounces, as players of the DOS and Amiga
versions report.

### Clock (confirmed)

The logic tick 0x1386 reads the joystick (0x1714 → `-$42bc`) and calls the
A4 jump-table entry `-$7e00`, which is `jmp $c660`, the flight handler.
Flight therefore runs once per 4 VBlanks with the fuel and oil logic.

### Mode dispatch (0xc94c)

| Mode | Handler | Meaning |
| --- | --- | --- |
| 0 | 0xc6a0 | Flying: engine checks, sea crash (altitude ≤ −7), then controls 0xbff4, integration 0xbdfa, contact 0xba80 |
| 1 | 0xc736 | On deck: 0xc4e8 controls, 0xbdba roll, 0xc5f4 deck ends, 0xb92e cables |
| 4 | 0xc74e | Engine failure: crash routine 0xafba |
| 6 | 0xc78c | Sinking: altitude −1 every 3 ticks, climb −250 per tick |
| 7 | 0xc882 | Cable arrest: speed −110 per tick; at 0, mode 1 |
| 8 | 0xc7c6 | Crashed on a surface (`hcr5`/`hcrf`) |
| 2, 3, 5, 10, 11 | 0xc8f0 | Altitude held on the surface; mode 1 when carrier record field 2 is 0 (probably the elevator) |
| 9 | 0xc8ee | Nothing |

### Turns (0xab80)

- **Turn frame `-$5bf0`** (0..25): advances one frame per 2 ticks (clock
  `-$555e`, DATA 2).
- The heading (`$14`) flips at frame 14; the turn ends after frame 25.
- Past frame 19, unless the new heading is held, the frame becomes
  26 − frame and unwinds one per tick.
- Called with the "forward" argument 1 when pushing the new heading, 0
  otherwise.
- Early in a turn (frame ≤ 6) any input other than pushing the other way
  unwinds it one frame per tick.
- 0xaa6e pauses turns while a particular object (record type 2/1/3,
  animation frame 13) is active; not identified.

0xb1bc is a second turn stepper (±2 frames per tick) inside the crash
routine 0xafba, not the player's controls.

### Pose and shapes (0xc378, 0xabde)

| Situation | Shape table |
| --- | --- |
| Flying | `-$521e[(climb + 5000) / 500]`: `hc0a` … `hc01` (bottom-offset pose from `-$5526`) |
| Turning, facing left | `-$52ee[frame]`: `hc28`..`hc32`, `hc32` ×2, `hc3b` ×2, `hc3c`..`hc3f`, `hc2d`..`hc28` |
| Turning, facing right | `-$5286[frame]`: `hc22`..`hc27`, `hc37`..`hc3b`, `hc3b` ×2, `hc32` ×2, `hc33`..`hc36`, `hc27`..`hc22` |
| On deck, `-$5562` set | `hc05` (level) |
| On deck otherwise | `-$531e[frame]`: `hc21` at rest, `hc20`..`hc1b` while turning |

The heading flips at frame 14, so a turn plays frames 1..13 of one table and
14..25 of the other. Wheels are a separate overlay: `-$51ac` (`wh0b`..`wh14`,
facing left) and `-$515c` (`wh01`..`wh0a`) by pose index. A turning pose
reports bottom pose 0.

### On the deck (0xc4e8, 0xbdba, 0xc5f4, 0xb92e)

- **Pushing the way the plane faces:** throttle on; the counter `-$3214`
  rises 1 per tick to 8 (or a deck-turn frame unwinds instead); speed +=
  counter.
- **Pushing back:** counter 0; at speed 0 the deck-turn frame advances, and
  past 6 the heading flips with frame 5. Speed −8.
- **No input:** counter 0, speed −8. Speed is kept within 0..1400.
- **Tail up:** `-$5562` = speed > 600 and Up not held.
- **Roll (0xbdba):** (speed + 50) / 100 px per tick.
- **Deck ends (0xc5f4):** outside the landing range the plane is flying
  (mode 0): this is the takeoff. There is no separate lift-off rule.
- **Cables (0xb92e):** at speed ≥ 600 with `-$5562` clear (Up held),
  hook = x + 24 facing left (x − 24 facing right). The hook catches cable *k*
  when it is within 8 px of carrier x + 70 + 56*k* (*k* = 0..3). Then mode 7.
- **Carrier x** (`-$5c6c`, from the mission file × 4 − 8) is also where a new
  plane starts (0x35dc): the elevator.

### Gear (0xb45a)

Mode 0: gear 5 when |x − carrier x| < 1280 (`-$50fc`) and `-$5b22` is set;
modes 1, 7 and 11: gear on; otherwise off. No heading or altitude condition.
