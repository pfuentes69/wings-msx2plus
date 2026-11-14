# P2 part 2: carrier landing, bounce and crashes

Implemented 2026-11-14. The evidence is in
[research/amiga-fuel-oil.md](research/amiga-fuel-oil.md#landing-and-contact-0xba80-0xb8c4-0xc2ce).

## Rules

`src/core/landing.c` applies the original's contact rules every simulation
step in which the plane is below deck height:

| Situation | Result | Original |
| --- | --- | --- |
| Touching the deck from above (at most 4 px in), more than 16 px from both ends, **stalling while facing left** | **Landed**: on deck, facing left; the ground model brakes it to a stop | 0xba80 → mode 1 |
| The same deck contact any other way (powered, diving, facing right) | **Bounce**: vertical speed reversed, 6 px lift | 0xba80 |
| Deck ends, below deck level (the hull), or any contact with a dead engine | **Crash** | 0xba80 → mode 4 |
| Reaching the sea or an island | **Crash** | 0xc6de (sea) |
| Resting exactly at deck height | No contact, so takeoff works | 0xb8c4 |

As the manual says, you approach from the right toward the carrier and stall
onto the deck. The original has no cable geometry in its capture rule, so the
four cables are scenery.

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

- The arrest after touchdown uses the existing ground braking (5 units per
  step). The original's mode-1 deceleration is not mapped.
- One original altitude unit is taken as one pixel (altitude = 1200 − y).
- After engine failure the plane noses down. The original hands the descent
  to its crash routine; its arithmetic is not mapped yet.
- The crash art frame timing (spread evenly over the 1-second hold) is an
  MSX choice.

## Verification

- `tests/test_landing.py` covers: landing, the bounce variants, deck-height
  takeoff, the 16 px deck ends, the 4 px depth limit, the hull, a dead
  engine, the sea at the bottom offset, scenery height, the original bottom
  tables, and earlier deck contact when the nose is up.
- The P0 smoke run flies a closed-loop autopilot from the real flight state
  (`s_World`; `g_LastContact` records each contact):
  1. Take off, turn, pass the carrier, turn back and stabilise at y 1150
     over the deck.
  2. Stall: it must land, facing left at deck height, and stop.
  3. Taxi, releasing at the braking distance, and stop on the elevator
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
- 99 snapshots pass on NTSC and on PAL.
