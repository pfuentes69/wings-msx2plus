# Sound effects (PSG)

The original plays 8-bit samples on the Amiga's four Paula channels. The
MSX can't afford sample playback during gameplay
([sound-budget.md](sound-budget.md)), so each effect is resynthesized on the
PSG from what the executable does with it. Music is a later step.

## What the original plays

The sound update (0x2066, fed by 0x2132 each frame) gives each Paula
channel two candidate slots (0x18-byte records from `-$3c96`):

| Channel | Slot | Sample, period | When |
| --- | --- | --- | --- |
| 0 | gun | machinegun, 200, looping | the player fires (`-$5c94`) |
| 0 | engine | engine, looping | always; see below |
| 1 | enemy gun / engine | machinegun 160, engine 330 | enemy planes (not in the port yet) |
| 2 | boom | boom, 500, once | bombs bursting on land or deck (0x0c9a, 0x0d8e), via 0x2324 |
| 2 | splash | splash, 350, once | bombs into the sea (0x0c90), via 0x233e |
| 3 | AA | machinegun, 320, looping | AA fire (`-$3e9a`, volume `-$3e98`) |
| 3 | one-shot | grind (450, looping) | the carrier's lift moving (`-$5c6a` 2, 3) |
| 3 | one-shot | metal.clang (450) | the lift reaching its stop (0x149e, 0x14ce), via 0x2354 |
| 3 | one-shot | screech (350) | the hook catching a cable, a bounce on deck (0xbb40, 0xbb7e), via 0x2380 |
| 3 | one-shot | scream (380) | a soldier hit (0x1ac6), via 0x23ac |

The samples were identified by their lengths (0x1646 = metal.clang.1, 0x1a5a
= screech, 0x19ac = scream).

**Engine (0x2132).** Its target volume and base period depend on the mode:

| Mode | Volume / 64 | Base period |
| --- | --- | --- |
| Throttle on (0xc144, 0xc528) | 64 | 335 |
| Flying, no throttle (0xc0e2) | 49 | 385 |
| On deck, no throttle (0xc566) | 40 | 808 |
| Engine failed (0xc74e) | 25 | 960 |

The period follows base + climb / 128 + altitude / 16. Each tick it moves
at most 10 down or 20 up. The volume moves 1 up or 2 down. Distant sounds
are quieter: 0x2306 gives volume 64 − distance / 32, where the distance is
|dx| + |dy| from the plane.

## The MSX driver

`src/msx/sound.c` (resident, Z80) runs once per field at the end of the
dashboard line interrupt, in the 3,000 T-state budget, and writes PSG
registers 0..10:

- **A: the engine.** Tone period 2.24 × the original's Paula period. The
  engine sample's waveform repeats every 71 samples, so it sounds at
  49,956 / P Hz: about 150 Hz at full throttle, 62 Hz idling on deck. On
  odd fields the period is 1/32 higher, a slight throb. Volume is the
  original's × 11 / 64.
- **B: guns, or the lift.** The cannon gives a noise burst every 6 fields
  at volume 12 (12 → 9 → 5 → quiet). The dugout guns in range use one
  every 10 fields, quieter with distance. While the lift moves, B grinds
  instead: tone 1200 AND noise 20, pulsing about 7.5 times a second like
  the grind sample.
- **C: one-shot effects.** Each is a short list of steps (fields, volume
  4.4, its slide, tone or noise, the tone's slide), shaped after the sample
  at its original period:

| Effect | Priority | Shape |
| --- | --- | --- |
| boom | 4 | a 62 Hz thump, then 0.75 s of the lowest noise, fading |
| splash | 3 | 0.67 s of hiss at a rising noise period, quieter |
| clang | 2 | a sharp tone-and-noise strike, then a 1.07 kHz ring fading over 0.7 s |
| screech | 2 | ~1.7 kHz tone with noise, wobbling, fading over 0.67 s |
| scream | 1 | a tone wavering between ~450 and 900 Hz and falling, 0.7 s |

  A higher or equal priority replaces the effect playing. Volume drops one
  step per 128 px from the plane.

The noise generator is shared: an effect's noise period wins over the guns'
while it plays. Register 7 keeps port A as input (bit 6 = 0, the joysticks)
and port B as output.

The steps live in segment 22 (`src/msx/sound_update.c`) and are copied
into RAM at boot, because the interrupt can't map a bank. Resident space
is short: 147 bytes are left.

**Game side.** `Sound_Update` (segment 22) runs once per presented frame.
It sets the engine from the flight mode, the throttle, the climb and the
altitude, with the original's ramps. It sets the guns from the cannon's
flash or the dugout guns drawn, and the grind from the lift's stage. It
plays the clang when the lift stops and the screech when the hook catches
a cable. The rest are hooked where they happen:
- bomb bursts (`Sound_Bursts`, after a weapon tick with new impacts);
- the crash (`StartCrash`: splash at sea, else boom);
- a bounce on deck;
- a soldier hit (`Island_Kill`).

Everything is silent outside a sortie.

## Listening

`python3 tools/preview_sound.py OUTPUT_DIR` renders each effect, the
engine's four modes, both gun rattles and the grind to WAV files. It uses
a model of the driver and of the AY-3-8910. To compare, the original
samples are in `assets_src/audio`
([audio-extraction.md](audio-extraction.md)).

## Verification

- `verify_p0` dumps the PSG registers at every snapshot and logs each
  effect the driver starts:
  - port bits 0x80 in register 7 everywhere;
  - no engine or guns outside a sortie;
  - in the cannon snapshots, the engine at volume 6 or more with a tone
    of 700..2600 and the cannon's noise on;
  - in the moving-lift snapshots, the grind;
  - over the run, at least one boom, splash, clang and screech.
- `tests/test_island.py` checks that each soldier hit asks for a scream
  from where he is.
- The first NTSC run found the engine period starting from uninitialized
  RAM (the FS-A1WX doesn't clear it; C-BIOS does). The driver and its state
  are now set at the start of `main`.

Not yet:
- the effects' exact cost in the interrupt (estimated well under the 3,000
  T-state budget, which was a busy loop until now);
- tuning by ear against the original;
- PAL-specific durations (the steps count 60 Hz fields, so effects play 20%
  longer at 50 Hz);
- music.
