# Hand-written Z80 flight step

Rewritten 2026-11-14 for the [rebuilt flight model](flight-model.md). Applies
to SDCC builds of the release profile (`mission-flight`); host builds and
SDCC builds with `WINGS_FLIGHT_C` use the C reference in `src/core/flight.c`.

## What it does

`Flight_StepWorldSample` runs 150 times a second (20 calls per NTSC frame, 24
per PAL frame). The original's rules run in the banked `Flight_Tick` once
every 12 steps. The step itself:

1. On step 0, calls `Flight_Tick(state, world, input)` through
   `___sdcc_bcall_ehl`, with the arguments on the stack as SDCC passes them
   to banked functions.
2. Adds `vx` to the world x and `vy` to y. For the first |`xrem`| / |`yrem`|
   steps of the tick it adds one more Q8 unit in the remainder's direction,
   so the 12 steps add up to the tick's whole-pixel motion exactly.
3. Advances the step counter (0..11).

It needs no clamping: `Flight_Tick` limits each tick's motion to the world
and the sky.

Interface: sdcccall(1), HL = state, DE = pointer to the world x (Q8, 32-bit),
two argument bytes on the stack that the callee removes. IX and IY are
preserved. Compile-time checks cover the state layout (31 bytes) and the 12
steps per tick.

## Cost

| Version | Cost per step |
| --- | --- |
| Old P1 model, C | 1.16 ms |
| Old P1 model, hand-written Z80 | 0.475 ms |
| Rebuilt model, C (`int32` motion and clamps) | ~0.73 ms |
| **Rebuilt model, hand-written Z80** | **744 T-states (0.21 ms)** |

## Verification

`tests/test_flight_step_z80.py` (needs SDCC and the `z80` package from
`requirements.txt`) builds `flight.c` with SDCC, links it with a stub
`Flight_Tick` that records its arguments, and runs it on an emulated Z80
against the native C reference. Each step compares every state field, the
world x and the tick-call arguments. The default is 30,000 random steps; set
`WINGS_FLIGHT_STEP_Z80_STEPS` for longer runs. `tests/test_flight_model.py`
covers `Flight_Tick` itself.
