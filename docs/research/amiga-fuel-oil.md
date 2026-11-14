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

## Not yet recovered

Engine-out flight physics, crash and splash presentation, refill in the hold,
what crashes on contact with the sea or deck, and which attackers cause each
kind of damage.

## Landing and contact (0xba80, 0xb8c4, 0xc2ce)

Recovered 2026-11-14 with the same method.

| Evidence | Meaning | Confidence |
| --- | --- | --- |
| 0xaaea | The plane's bottom offset below its origin: a per-pose table (`-$5552`, indexed by pose `-$5a6c`), plus a gear-down table (`-$553c`) while gear `-$5bf4` is down; turn frames use `-$54fe` | Established control flow; table values not yet extracted |
| 0x5710 | Surface height from the map word's object id (`(word >> 2) & 0x1ff`) | Established; heights per id not extracted |
| 0xb8c4 | Contact when `altitude − bottom < surface` (strictly below) or ≤ 0. Resting exactly on the surface is not contact, so takeoff is safe | Established |
| 0xb7bc | Landing range = carrier map extents × 4, 16 px inward at each end | Established |
| 0xc2ce | While UP (input bit 0) is held facing left, horizontal speed approaches 600 and flag `-$5554` is set; facing right clears it | Established; bit-0 = UP inferred from the horizontal mask `$0c` |
| 0xba80, mode 0 contact | **Landed (mode 1)** when inside the landing range, at most 4 px into the deck, `-$5b22` set, facing left and `-$5554` set: altitude snaps onto the deck. Inside the range otherwise: **bounce** (vertical velocity negated, +6 px). Outside the range: **crash** (mode 4, explosion via 0xafba) | Established control flow; `-$5b22` is only read (probably "carrier present") |
| 0xc6de | Altitude ≤ −7 (into the sea) → mode 6, crash sound | Established |

There is no cable geometry in the capture rule. The manual's "four arresting
cables" are scenery as far as this code is concerned: a stall onto the deck,
facing left, is a landing.
