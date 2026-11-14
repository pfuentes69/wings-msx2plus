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

A crash holds the scene for one second, with a splash (sea) or an impact
(deck, island) at the plane. Then the plane is lost
([p2-engine.md](p2-engine.md)): the next one starts on deck, or GAME OVER.

The check runs only while the plane is below deck height, so it costs
nothing in normal flight. Without that guard, the per-step call added about
9 ms to the worst frame.

**Provisional:**

- The arrest after touchdown uses the existing ground braking (5 units per
  step). The original's mode-1 deceleration is not mapped.
- Islands are flat ground at sea level. The original reads per-object surface
  heights (0x5710), and the per-pose bottom offsets (0xaaea), from tables not
  yet extracted. Flying through the carrier's island superstructure does not
  collide yet.
- The crash visual reuses the strike splash/impact marks; the original's
  crash and explosion art is pending.

## Verification

- `tests/test_landing.py` covers: landing, the bounce variants, deck-height
  takeoff, the 16 px deck ends, the 4 px depth limit, the hull, a dead
  engine, and sea and open-air contact.
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
     splash hold, and the next plane appears on deck with one plane fewer.
- The oracle draws the plane in its on-deck pose from the dumped flight
  mode rather than from snapshot names.
- 98 snapshots pass on NTSC and on PAL.
