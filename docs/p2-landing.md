# P2 part 2: carrier landing, bounce and crashes

Implemented 2026-11-14. The evidence is in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md#landing-and-contact-0xba80-0xb8c4-0xc2ce).

## Rules

`src/core/landing.c` applies the original's contact rules every simulation
step in which the plane is below deck height:

| Situation | Result | Original |
| --- | --- | --- |
| Touching the deck from above (at most 4 px in), more than 16 px from both ends, **in the stall flare (Up alone) facing left, not turning** | **Landed**: on deck at flying speed. Keep Up held and the hook catches a cable, which stops the plane ([flight-model.md](flight-model.md#landing)) | 0xba80 → mode 1, 0xb92e → mode 7 |
| The same deck contact any other way (powered, diving, facing right, turning) | **Bounce**: climb reversed, 6 px lift | 0xba80 |
| Deck ends (flying in), below deck level (the hull), or any contact with a dead engine | **Crash** | 0xba80 → mode 4 |
| Leaving over a deck end, at most 4 px below the deck | No contact (MSX choice: a takeoff below flying speed sinks a little) | |
| Reaching the sea or an island | **Crash** | 0xc6de (sea) |
| Resting exactly at deck height | No contact, so takeoff works | 0xb8c4 |

As the manual says, you approach from the right toward the carrier and stall
onto the deck. The touchdown rule has no cable geometry. The cables come into
play afterwards: the hook catches one only while Up is held. The gear comes
down in either direction, but a left-to-right touchdown always bounces.

A crash holds the scene for one second while the original crash art plays
at the plane: the sea splash `spl0`..`spl6` over water, and the explosion
`exp0`..`exp5` on the deck or an island (world.shp). The original picks the
outcome by surface (0xafba). The frames stream into the atlas slot of a large
static aircraft frame, which is reloaded when the next plane launches. Then the plane is lost
([p2-engine.md](p2-engine.md)): the next one starts on deck, or GAME OVER.

**Heights.** Contact uses the plane's bottom, not its origin, as the original
does (0xb8c4): altitude − bottom offset is compared with the surface.

- **Bottom offsets:** per pose 2, 12, 10, 6, 4, 2, 5, 7, 9, 12, 14, plus
  5, 4, 3, 3, 3, 5, 3, 2, 1, 0, 0 with gear down (0xaaea).
- **Static scenery heights:** 36, 35, 35, 9, 13, 12 by object class, minus
  map-word bits 11..13 (0x5710). `tools/convert_mission.py` emits them as 74
  runs for mission A (`src/generated/mission_heights.h`).
- **Carrier:** every carrier id has one deck height (33 px), so the original
  does not collide with the carrier's tower, and neither does the port.

**Cost.** `Landing_Prepare` computes the bottom offset and the surface height
once per frame. A cheap resident compare gates each step, and only a likely
hit calls the banked `Landing_Contact`. Unguarded per-step checks cost 9–17 ms
in frames over the carrier.

**Provisional:**

- One original altitude unit is taken as one pixel (altitude = 1200 − y).
- After engine failure the plane noses down (forced Down input). The
  original hands the descent to its crash routine; its arithmetic is not
  mapped yet.
- The crash art frame timing (spread evenly over the 1-second hold) is an
  MSX choice.

## Verification

- `tests/test_landing.py` covers: landing, the bounce variants, deck-height
  takeoff, the 16 px deck ends, the 4 px depth limit, the hull, a dead
  engine, the sea at the bottom offset, scenery height, the original bottom
  tables, and earlier deck contact when the nose is up.
- The P0 smoke run flies a closed-loop autopilot from the real flight state
  (`s_World`; `g_LastContact` records each contact):
  1. Take off, fly out low, turn, coast past the carrier, and turn onto final
     just inside the map's right end, 5 px above deck contact.
  2. Flare (Up alone): it must land facing left at deck height, catch a cable
     and stop short of the elevator.
  3. Taxi, cutting power at the braking distance, and stop on the elevator
     (7032 ± 6).
  4. Fire to go down to the hold (service menu), confirm, return to the
     deck and launch again.
  5. A powered touchdown must bounce.
  6. A powered dive must crash; the scene is pixel-checked during the
     crash hold, and the next plane appears on deck with one plane fewer.
  7. The engine-failure crash over open sea must show the splash art,
     pixel-checked.
- The oracle draws the plane in its on-deck pose from the dumped flight
  mode rather than from snapshot names.
- 89 snapshots pass on NTSC and 86 on PAL (PAL captures fewer intermediate deck-turn poses).
