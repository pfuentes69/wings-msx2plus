# Hand-written Z80 flight step

Added 2026-11-14. Applies to SDCC builds of the P1 flight model
(`mission-flight`). The debug profile and host builds use the C code.

## Why

At 150 Hz, `Flight_StepWorldSample` runs 20 (NTSC) or 24 (PAL) times per
presented frame. SDCC 4.6.0 compiled the C version, `StepControls` plus the
world step, into IX-frame code. Every field access reloaded the state pointer
and spilled locals. These measurements are from `tools/profile_p0.py` on the
release ROM:

| Version | Cost per step (MSX) |
| --- | --- |
| Original C | 1.16 ms |
| C working on a file-static copy | 1.09 ms |
| SDCC `--max-allocs-per-node 200000` | ~1.1 ms (build time 1 min to 8 min 41 s; rejected) |
| **Hand-written Z80** | **0.475 ms** |

That saves about 12 ms per NTSC presented frame. The time pays for the
[sound budget](sound-budget.md) and removes the gunfire presentation
reservation.

## Structure

- `src/core/flight.c` keeps the C reference. When `__SDCC` and
  `WINGS_P1_FLIGHT` are defined and `WINGS_FLIGHT_C` is not, it includes
  `src/core/flight_z80.inc` instead of the P1 C step.
- `flight_z80.inc` uses the same sdcccall(1) interface: HL = state,
  DE = x, two argument bytes on the stack that the callee removes. It keeps
  IX and IY. SDCC itself treats IY as caller-saved.
- Constants hard-coded in the assembly (deck limits, launch zone, takeoff
  speed, turn lengths, acceleration period, flight ceiling, mode and input
  values) have compile-time checks. If the C definitions drift, the build
  fails. The world width is read from `g_FlightWorldMax` because it comes
  from the mission manifest.

## Verification

`tests/test_flight_z80.py` (needs SDCC and the `z80` package from
`requirements.txt`) builds `flight.c` twice with SDCC: once with the assembly
and once with the C reference (`WINGS_FLIGHT_C`). It runs both on an emulated
Z80 and compares every field and the world x with the native C build after
each step:

- 150,000 random steps by default (states, positions near the deck and world
  limits, held and changing inputs). Set `WINGS_FLIGHT_Z80_STEPS` for longer
  runs; 5,000,000 passed on 2026-11-14.
- The SDCC-compiled C against native C, which catches miscompiles like the one
  in [sdcc-pitfalls.md](sdcc-pitfalls.md).
- A scripted deck takeoff, climb into the ceiling, stall, dive into the sea
  limit and reversals, covering all four flight modes.
- Return-stack and register contract, and a speed bound: about 1,600 plain
  Z80 T-states per step against about 3,700 for SDCC-compiled C.

Changing the flight rules means changing both versions. The test fails until
they agree.
