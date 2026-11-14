# Flight model (rebuilt from the original)

Implemented 2026-11-14. It replaces the P1 tuning model
([p1-flight.md](p1-flight.md), now historical). The rules come from the Amiga
executable; addresses and variables are in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md#flight-model-0xbff4-controls-0xbdfa-integration-0xc3780xabde-pose).

## Timing

The original runs its game logic, joystick read included, once every 4 PAL
VBlanks (12.5 Hz). Its flight handler (0xc660) is called from that tick. The
port keeps its 150 Hz simulation clock:

- `Flight_Tick` (banked, segment 21) runs the original's rules once every 12
  steps. It handles the controls, the angles and the per-tick motion in whole
  pixels.
- `Flight_StepWorldSample` (resident, hand-written Z80) spreads that tick's
  motion evenly over the next 12 steps. A tick therefore moves exactly the
  original's whole-pixel step, and contact checks still run every step.

## In the air

Speed runs from 1000 to 1400 (100 = 1 px per tick); angles are in hundredths
of a degree.

| Input | Effect per tick |
| --- | --- |
| Push the way you fly | speed +1, +2 … up to +8 per tick, to 1400 |
| No input | speed bleeds toward 1000; a climb flattens, **a dive holds** |
| Up or Down alone | **no change in speed** |
| Push the other way | starts a turn |
| Direction + Up | climb +6° (only +0.75°/+1.5° below speed 1000), to +30° |
| Direction + Down | dive −6° (−3° while turning), to −45° |
| Down alone | dive −12° |
| Up alone, facing left | the **stall flare**: nose settles at +6° while the plane sinks at about 8° |
| Up alone, facing right | the nose drops, settling near −12° |

The flight path follows the commanded climb a quarter of the way each tick,
so attitude changes are smooth. The plane shows ten pitch poses (`hc01`..`hc0a`),
picked from the commanded climb, so holding a direction with Up or Down steps
through the climb and dive angles.

**Turns** play the original 26 turn frames (`hc22`..`hc3f`), one per 2 ticks.
The heading flips at frame 14, and a full turn takes 52 ticks (4.2 s).
Horizontal speed follows the original turn factors (zero when edge-on), and
the nose drops 1.5° per tick unless Up is held. Pushing back early unwinds
the turn. Releasing after frame 19 mirrors the turn and finishes it quickly.

**Below flying speed**, just after leaving the deck, the plane sinks
(1000 − speed) / 100 px per tick, and the nose drops unless Up is held.
**Ceiling**: altitude 1100.

## On the deck

| Input | Effect per tick |
| --- | --- |
| Push the way you face | speed +1, +2 … +8 per tick |
| No input, or pushing back | brake 8 per tick |
| Pushing back at rest | turn round on the spot (6 frames, then the other way) |
| Above speed 600 without Up | tail up, on the wheels |

The roll moves (speed + 50) / 100 px per tick. **Takeoff** is rolling off
either end of the deck. From the elevator, the plane reaches the bow at
about speed 780, below flying speed, so it dips (10 px below deck level,
30 px above the sea, in the smoke run) before climbing away with Up held.

## Landing

- **Gear** comes down within 1280 px of the carrier, in either direction.
- **Touchdown:** facing left, holding Up alone (the stall flare), not turning,
  inside the deck, at most 4 px in. Anything else on the deck bounces, so
  landing left to right always bounces: the hook can't catch.
- **Arrest:** the plane lands at flying speed. Keep Up held: the hook, 24 px
  behind the plane, catches one of the four cables (+70, +126, +182 and +238 px
  from the elevator) when it passes within 8 px. The cable then brakes it 110
  per tick to a stop, about 50 px at speed 1100. Without Up, the plane rolls
  off the bow.

The contact rules are in [p2-landing.md](p2-landing.md).

## MSX choices

| Item | Choice |
| --- | --- |
| Directions tapped between two frames | Count for that frame's ticks, so a one-tick Down tap starts a held dive |
| Wheels on the flare and when tail up on deck | The atlas has wheels only on the level (`hc40`/`hc41`) and tail-down views. The original overlays wheels (`wh01`..`wh14`) on any pose: those shapes are not extracted yet |
| Deck-turn poses | The original's 6 deck frames map onto the existing 5-step taxi sequence |
| Leaving over a deck end | The plane may sink 4 px over the last 16 px without crashing. The original's bow and stern geometry is not mapped |
| Turn pause while a weapon is in flight (0xaa6e) | Not reproduced |
| Engine-out descent (mode 4) | Still a forced Down input; the original's crash routine is not mapped |
| Arithmetic | The original uses fast floating point; the port uses scaled integers (sin × 10000, turn × 100) with exact quotients. Results agree except where a value lands exactly on a whole pixel and the original's rounding differs |

## Cost

- `Flight_Tick`: about 0.35 ms per tick. A 16 × 16 multiply and exact
  repeated subtraction replace SDCC's 32-bit multiply and divide, which cost
  several milliseconds.
- Step: 744 T-states (0.21 ms), down from the old step's 0.475 ms.
- Simulation: 22 ms mean per NTSC frame.
- **Presentation:** at flying speed each page draws about six new terrain
  columns. Over the carrier those columns are the costliest, and the low pass
  measured 137–148 ms against the 133 ms deadline. Until the carrier render
  is reworked ([frame-budget.md](frame-budget.md)), frames with the carrier in
  the near view at speed 1000 or more get 2 extra VBlanks, as bomb frames
  already do: 6 fps there instead of 7.5 on NTSC. Game speed is unaffected.

## Verification

- `tests/test_flight_model.py` (28 tests) checks the model against the
  original's numbers:
  - tick cadence, deck acceleration (1, 3, 6, 10 …) and the takeoff dip;
  - speeds and steps;
  - airspeed held in the stall;
  - the climb and dive pose sequences, the flight-path lag and the flare;
  - nose-down with Up facing right;
  - the 52-tick turn, its shapes and its mirror and unwind;
  - gear range, cable catches, braking 882, 772, 662 …;
  - the deck turn, and the roll off the bow.
- `tests/test_flight_step_z80.py` runs the Z80 step against the C reference
  over 30,000 random steps on an emulated Z80.
- `tests/test_landing.py` covers the contact rules with the flare flag.
- The P0 smoke run flies everything with closed-loop scripts on the real
  state, pixel-checking each snapshot: deck turns, takeoff, turns, stall,
  dive tap, cannon in climb, level and dive both ways, and gear near the
  carrier. A circuit flown low, coasting downwind, ends in a flare landing
  with a cable arrest, a taxi onto the elevator, a powered bounce and a sea
  crash. 89 snapshots pass on NTSC, 86 on PAL.
