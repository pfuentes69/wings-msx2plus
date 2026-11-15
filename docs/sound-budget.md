# Sound CPU budget

Decided 2026-11-14, ahead of the P7 audio work, so that every frame-deadline
measurement from now on already includes sound.

## Budget

**3,000 T-states once per video field** (about 0.84 ms; 5% of a 60 Hz field,
4% of a 50 Hz field). For the 8-field gameplay presentation this is about
6.7 ms per presented frame on NTSC and 6.7 ms on PAL.

Sizing:

| Part | Typical cost per field |
| --- | --- |
| PSG music replayer (pattern decode + 14 register writes) | 1,000–2,500 |
| PSG sound effects (one or two prioritised channels) | 200–500 |
| Headroom | rest |

Optional MSX-MUSIC (OPLL) playback must fit inside the same budget. If it
does, it replaces PSG music, and effects stay on the PSG. OPLL register writes
need waits between them, so its driver should spread note changes over fields
rather than burst them.

The original effects are 8-bit PCM samples (`assets_src/audio`). Playing PCM
through PSG volume needs the CPU continuously and cannot share a frame with
gameplay, so in-game effects must be resynthesised as PSG effects. PCM is only
possible on screens that do no rendering, such as a title screen.

## Where it runs

At the end of the dashboard line interrupt (`VDP_HBlankHandler`, final stage
at line ~170–174), in active display. It does **not** run in the VBlank
interrupt. Page publication must complete while the VDP still reports
vertical retrace. On NTSC that window is about 11,400 T-states from VBlank
interrupt entry, and publication normally needs about 4,500. A 3,000 T-state
VBlank load made the weapons scenario publish outside retrace. On the line
interrupt, the budget ends by about line 190, before VBlank at line 212.

The line interrupt fires once per field in gameplay and menus (verified:
8,881 runs for 8,881 VBlank interrupts across the P0 run).

PSG sharing: joystick input is read through PSG registers 14/15 in the VBlank
interrupt. The sound driver runs in another interrupt with interrupts
disabled, so the two never interleave. The driver must still preserve the
PSG register-7 I/O direction bits (7 = 1 for port B output, 6 = 0 for port A
input).

## The driver

Since 2026-11-15 the release build runs the PSG effects driver here
(`Sound_Field` in `src/msx/sound.c`, [sound-effects.md](sound-effects.md)).
The debug profile keeps the old placeholder: `SoundBudget()` in
`src/world_flight.c`, a busy loop calibrated at 2,976 T-states
(`WINGS_SOUND_TSTATES`, default 3000; 0 removes it). The driver's own cost
hasn't been measured yet. It is a few hundred T-states of Z80 plus 11
register writes, well under the budget, so release frames got slightly
faster. Music must fit in what is left.

Measured with the placeholder (2026-11-14):
- `verify_p0`: 89/89 snapshots on NTSC and on PAL.
- Weapons regressions: 66 snapshots on NTSC, 69 on PAL.
- Publication latency: typically 4,250–4,750 T-states, worst 8,000.
