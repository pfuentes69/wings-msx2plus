# Amiga music: the Kris Hatlelid replayer and the four songs

Recovered 2026-11-20 by static 68000 disassembly (Capstone) of
`reference_assets/original_files/Wings_of_Fury/songplay` (the replayer,
HUNK with symbols) and by walking the song data in `wofsongs`. Code
addresses are songplay CODE-hunk offsets (file offset = 0x28 + address);
songplay data addresses are DATA-hunk offsets (file 0xe84 + address);
`wofsongs` offsets are DATA-hunk offsets (file 0x1c4 + offset). Each claim
is marked **confirmed** (read from the code or data, or measured) or
**inferred** (a reading of what the code implies). Which subsong plays
where, the player commands and the fade are in
[amiga-intro.md](amiga-intro.md) §4; the instruments' 8SVX headers are in
[audio-extraction.md](../audio-extraction.md).

Decoder: `tools/decode_songs.py` replays the song data with the
replayer's own state machine, one timer tick at a time, and prints or
exports the events.

```sh
python3 tools/decode_songs.py --summary          # per song: tempo, loop, channels, ranges, data size
python3 tools/decode_songs.py --song 4           # event listing of one subsong
python3 tools/decode_songs.py --json OUT.json    # every event of every song
python3 tools/decode_songs.py --midi             # assets_src/audio/music/song{0,1,2,4}.mid
```

The MIDI files are for listening only: 24 MIDI ticks per quarter = one
replayer tick, General MIDI instruments (brass section, synth bass,
square lead; kick, snare and hand clap on channel 10), `loopStart` and
`loopEnd` markers.

## Summary

- **Four tracks, one per Paula channel**, each a list of patterns with a
  transpose. A pattern is a string of 2-byte entries: a note (pitch byte,
  duration index) or a command. **Confirmed.**
- **No effects are used.** The replayer supports arpeggio and vibrato
  per instrument, but every voice in `wofsongs` has both switched off. No
  portamento or slide exists in the replayer. **Confirmed.**
- **One tempo per song**, set by the CIA-A timer A high byte:
  **21.65 ms per tick** (46.18 Hz) for subsong 0, **20.21 ms** (49.48 Hz)
  for the others. 24 ticks are a quarter note: 115.5 and 123.7 bpm.
  **Confirmed** (the musical reading of 24 ticks as a quarter is inferred).
- **Every song loops from the start**; all four tracks have the same
  length. Subsong 0: 1536 ticks, 33.26 s. Subsong 1: 1152 ticks, 23.28 s.
  Subsong 2: 2688 ticks, 54.32 s. Subsong 4: 1344 ticks, 27.16 s.
  **Confirmed**, and UADE agrees to within its ~40 ms start/stop latency.
- **Drums are samples on track 3**: the track switches between the
  bass-drum and snare voices (`$dc 4`, `$dc 5`) whenever the drum changes
  and plays every hit at note 27 (the sample's own rate). Kick and snare
  never sound together. Songs 2 and 4 have a three-octave drone of C on tracks 0..2.
- The pattern lists and patterns of all songs are **2,570 bytes**
  (wofsongs 0x20e..0xc17).
  Re-encoded for the MSX it is about **1.7 KB** for the four songs.

## 1. The data

### Song definition (wofsongs `songs`, `song1`..`song4`)

`songs` (offset 0) holds five pointers, one per subsong: song1, song2,
song3, song2, song4. A song definition is:

| Offset | Content |
| --- | --- |
| +0, +4, +8, +$c | Pattern lists of tracks 0..3 (Paula channels 0..3) |
| +$10 | Voice list: voice 0, voice 1, ... ending with a null pointer |

All four songs list the same voices (song1 has voices 0..5, the others
0..6). `_ReadInstruments` (0x946) starts at the **second** entry: voice 0
is never given a sample. **Confirmed.**

### Pattern list

Six bytes per entry: a pointer to a pattern (long) and a transpose
(signed word, in semitones). Used transposes: 0, 12 and 24. The list has
no terminator; the last pattern ends with the loop command. **Confirmed**
(0x656, 0x66a).

### Pattern entries (CODE 0x5d2..0x6fc)

Two bytes each, `c a`:

| c | a | Meaning | Used |
| --- | --- | --- | --- |
| $00..$d8 | duration index | **Note.** Pitch = (c & $7f) + transpose. Bit 7 = sustain/tie (below) | 268 entries |
| $d9 | – | End of pattern: next pattern-list entry | 64 |
| $da | – | Stop this track | No |
| $db | – | Restart at the first pattern-list entry (the song loop) | 1 (a shared pattern at 0xc14) |
| $dc | n | Voice n of the song's voice list | 39 |
| $dd | n | CIA-A timer A high byte = n, force load, start continuous | 4 patterns of track 0, always the song's one value |
| $de | n | CIA-A timer A low byte = n | No |
| $df | n | Track volume n (0..64), also written to AUDxVOL at once; ignored during a fade | 2 (30 on track 3 of songs 0/1) |
| $e0 | n | Hold: n = 1 suppresses the gate release | No |
| $e1..$ff | – | Ignored (skipped) | No |

Commands take no time: the track keeps reading until it reaches a note.
**Confirmed.**

### Durations (songplay DATA $254)

20 byte pairs (length in ticks, gate in ticks). The note lasts *length*
ticks; *gate* ticks after its start the channel is released (volume 0,
period $7c, DMA off): a hard cut, no release envelope. **Confirmed**
(0x704, 0x598).

| Index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Length | 96 | 48 | 32 | 64 | 24 | 72 | 12 | 84 | 60 | 36 | 6 | 90 | 78 | 66 | 54 | 42 | 30 | 18 | 8 | 16 |
| Gate | 86 | 43 | 28 | 58 | 21 | 64 | 10 | 75 | 54 | 32 | 5 | 81 | 70 | 59 | 48 | 38 | 27 | 16 | 7 | 14 |

Used: 0, 1, 2, 4, 5, 6, 9, 10, 18, 19 (whole, half, half triplet,
quarter, dotted half, eighth, dotted quarter, sixteenth, eighth triplet,
quarter triplet). The gate is about 90 % of the length.

### Voices (wofsongs `voice0`..`voice6`, $2e bytes each)

| Offset | Field |
| --- | --- |
| +0, +4 | VHDR and BODY pointers (filled by `_ReadInstruments`) |
| +8 | Notes per octave, 83 / ctOctave (filled) |
| +$a | Pointer to the 8SVX FORM (0 = no sample) |
| +$12, +$14, +$16 | Vibrato upper bound, lower bound, step (in period units) |
| +$18, +$1a, +$1c | Vibrato speed (ticks per step), delay, counter |
| +$1e | Vibrato on |
| +$22 | Arpeggio on |
| +$24..+$2b | Four arpeggio offsets (semitones), +$2c the step counter |

| Voice | Instrument | Role |
| --- | --- | --- |
| 0 | none | Rest |
| 1 | SyntheBass | Bass |
| 2 | omlead | Drone |
| 3 | RoomBrass2 | Melody, harmony |
| 4 | BassDrum3 | Kick |
| 5 | sdrum1 | Snare |
| 6 | Mechanic1 | A metallic swell, once in song3 |

Vibrato-on and arpeggio-on are 0 in every voice (voices 1, 4, 5, 6 carry
an unused 4, 7, 0, 12 major-chord table). **Confirmed.**

## 2. The replayer

### Timing (confirmed)

- One tick per CIA-A timer A underflow (`SongInt`, 0x2a6, installed with
  `ciaa.resource` at 0x9bc). Tick = (hi × 256 + lo) / E clock, with the E
  clock 709,379 Hz (PAL) or 715,909 Hz (NTSC).
- The songs write only the high byte (60 for subsong 0, 56 for the rest).
  The low byte is never written. UADE plays the songs with low byte 0, and
  the decoded timing matches its render only with that value (section 4).
  On a real Amiga the low latch's prior value is unknown (at most +1.8 %
  if it were $ff).
- Tracks are processed in order 0..3 within a tick. The first notes sound
  on the first tick after `_PlaySong`.
- NTSC: the same timer counts give ticks 0.9 % shorter.

### Pitch (confirmed)

The period table (songplay DATA $44..$253, 132 longwords) holds
3,579,545 / *f*(MIDI *n*) for MIDI 0..131: NTSC Paula clock over the
equal-tempered frequency (A4 = 440). The replayer reads it at
$134 + 4 × (note − 27), so the entry is MIDI note + 33. The Paula period
is

    period = table[note + 33] / samplesPerHiCycle    (integer division, divu.w)

with *samplesPerHiCycle* from the instrument's VHDR (8 brass, 8 bass, 16
drone, 32 drums). An octave shift for multi-octave 8SVX exists (0x7ea),
but all six instruments have one octave, so it is always 0.

**The sounding pitch is lower than the table's note**, because the
samples' real cycles are longer than their VHDR says. Measured by
autocorrelation of the sample data (peaks at *k* × cycle, *k* = 1..6,
correlation 0.95–0.99):

| Instrument | VHDR cycle | Real cycle | Sounds | MIDI = note + |
| --- | --- | --- | --- | --- |
| RoomBrass2 | 8 | 31.85 | 2 octaves down, +7 cents | 9 |
| SyntheBass | 8 | 128.9 | 4 octaves down, −2 cents (strong 2nd harmonic) | −15 |
| omlead | 16 | 129.3 | 3 octaves down, −14 cents (strong 2nd harmonic) | −3 |
| BassDrum3, sdrum1, Mechanic1 | 32 | unpitched | note 27 = 8,384 Hz playback (NTSC), the sample's own rate | – |

Measured; the decoder's `TRUE_CYCLE`. On PAL, all pitches are another
16 cents flat (3,546,895 vs 3,579,545 Hz). The decoder reports the PAL
frequency.

### Notes, ties and rests (confirmed, 0x5ee..0x7e2)

- A plain note (bit 7 clear) restarts the sample and is released at its
  gate.
- **Bit 7 set: sustain.** The first such note starts normally but is not
  released. Each following bit-7 note **continues** it: no restart, and
  the pitch does **not** change. A plain note ends the run. Used for long
  notes across bar lines and for the drones (one note for the whole
  song, and through the loop: the tie state survives the restart).
- **Rest:** a note on voice 0. It plays nothing, but its gate still
  releases the channel, so a sustained note before a rest sounds until
  the rest's gate.
- **Restart without release:** when a note follows a sustained note, the
  channel's DMA is still on. The new period and volume apply at once, but
  Paula reaches the new sample's start only when it finishes its current
  block (the sample or its loop). The attack then comes up to one pass of
  the brass loop late (0.26–0.79 s, depending on the pitch). Ten cases in
  song1, three in song3.
  Confirmed from the code; the render comparison improves with it
  (section 4).
- Samples play once, then loop their repeat part (brass, bass, drone).
  Drums have no loop: the audio interrupt (0x8ae) stops the channel after
  one pass. Gates cut them earlier when shorter.
- Track volume starts at 32 of 64 (0x382) and is written to AUDxVOL at
  every note. Volume never changes inside a song apart from the two `$df`
  30 commands.

### Effects (confirmed in the code; none used)

On every tick except the one that reads a note:

- **Arpeggio** (voice +$22): note + offset[*i* & 3], *i*++ (per voice, not
  reset by notes): a 4-step chord at the tick rate.
- **Vibrato** (voice +$1e): after *delay* ticks, every *speed* ticks the
  period moves by *step*. The step's sign flips when the distance from
  the note's period passes the bounds (unsigned word compares).

No portamento, slide, volume envelope, tempo change or pattern jump other
than the song loop exists. A fade (command 6) lowers every track's volume
by 1 every *speed* + 1 ticks ([amiga-intro.md](amiga-intro.md)).

## 3. The songs

`--summary` output, PAL. Ranges are sounding pitches.

| Subsong | Def | Plays | Tick | Tempo | Loop | Data (stored / MSX) |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | song1 | Name entry, high scores | 21.65 ms | 115.5 bpm | 1536 ticks, 16 bars, **33.26 s** | 684 / 480 bytes |
| 1 | song2 | Brøderbund, title, credits | 20.21 ms | 123.7 bpm | 1152 ticks, 12 bars, **23.28 s** | 586 / 430 bytes |
| 2 | song3 | Story | 20.21 ms | 123.7 bpm | 2688 ticks, 28 bars, **54.32 s** | 792 / 444 bytes |
| 3 | song2 | Never | – | – | Same as 1 | – |
| 4 | song4 | Rank selection | 20.21 ms | 123.7 bpm | 1344 ticks, 14 bars, **27.16 s** | 476 / 296 bytes |

### Subsong 0 (song1): high scores, C minor, shuffle

| Track | Role | Instrument | Notes | Range | Rhythm |
| --- | --- | --- | --- | --- | --- |
| 0 | Melody (4 rests) | RoomBrass2 | 58 | G♯3..G4 (MIDI 56..67) | Eighth triplets to whole notes |
| 1 | Harmony | RoomBrass2 | 22 | G3..C4 (55..60) | Half and whole notes |
| 2 | Bass | SyntheBass | 128 | G♯1..D♯2 (32..39) | Triplet figures (8 + 8 + 8 / 24) |
| 3 | Drums, volume 30 | BassDrum3 ×28, sdrum1 ×52 | 80 | – | Kick on beats 1 and 3, snare on 2 and 4, snare fills in triplet eighths |

### Subsong 1 (song2): intro pictures, C major

| Track | Role | Instrument | Notes | Range |
| --- | --- | --- | --- | --- |
| 0 | Melody | RoomBrass2 | 44 | C4..G5 (60..79) |
| 1 | Harmony | RoomBrass2 | 28 | A3..C5 (57..72) |
| 2 | Bass | SyntheBass | 96 | F1..C2 (29..36) |
| 3 | Drums, volume 30 | BassDrum3 ×18, sdrum1 ×44 | 62 | – |

### Subsong 2 (song3): story

| Track | Role | Instrument | Notes | Range |
| --- | --- | --- | --- | --- |
| 0 | Drone | omlead | 1, sustained the whole song | C2 (36), 64 Hz |
| 1 | Drone | omlead | 1, sustained | C1 (24), 32 Hz |
| 2 | Drone, then accents | omlead ×5, Mechanic1 ×1, sdrum1 ×1 | 7 | C0 (12), 16 Hz; Mechanic1 at note 15 (half rate), sdrum1 at note 0 (a slow, low snare) |
| 3 | Brass fanfare from bar 21 (rests before) | RoomBrass2 | 18 | C4..C5 (60..72) |

### Subsong 4 (song4): rank selection

| Track | Role | Instrument | Notes | Range |
| --- | --- | --- | --- | --- |
| 0, 1, 2 | Drone, C2 + C1 + C0 | omlead | 1 each, sustained | 64, 32, 16 Hz |
| 3 | Military snare (rolls of sixteenths) | sdrum1 | 120 | – |

The drone's spectrum in the UADE render peaks at 16.4, 32.1, 64.1 and
128.4 Hz, matching the decoded 16.0, 32.1, 64.2 Hz fundamentals and the
128 Hz second harmonic. Confirmed.

## 4. Validation against UADE

UADE (the local libuade in `tools/.build/audio-research`, through
`render_music`) rendered each unique subsong until it reported the song
end. It stops at the loop: 33.300, 23.316, 54.366 and 27.189 s, each 28 to
44 ms longer than the decoded loops (start and end latency). Then a
Paula-style resynthesis of the decoded events (the real samples at the
decoded periods, PAL clock, volume / 64, gates, one-shot ends, loops,
delayed restarts) was compared with the renders (mono, after alignment).
Scripts in the session scratchpad (`resynth.py`, `scan.py`), not in the
repository.

| Subsong | Start offset | Waveform correlation | ±1 semitone | ±8 cents | Low byte $ff (+1.8 % tick) | Envelope correlation |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 23.5 ms | **0.576** | 0.04 / 0.01 | 0.28 / 0.25 | −0.04 | 0.947 |
| 1 | 21.8 ms | **0.513** | 0.02 / −0.02 | 0.31 / 0.28 | −0.03 | 0.953 |
| 2 | 21.2 ms | **0.847** | 0.01 / 0.00 | 0.04 / 0.02 | 0.74 | 0.929 |
| 4 | 21.2 ms | **0.842** | 0.07 / −0.03 | 0.17 / 0.15 | 0.72 | 0.927 |

A sample-level waveform correlation is only possible if every onset,
period and loop is exact. It collapses with a pitch error of 8 cents or a
timing error of 0.5 %. Modelling the delayed restart raises subsong 0 from
0.548 to 0.576. Songs 0 and 1 stay lower because of UADE's A500 filter
and its 0.7 stereo panning over four busy channels. **Confidence: high**
for timing (tick = hi × 256 / 709,379 s), loop points, note onsets,
periods, gates and instrument choice. The sounding octaves rest on the
sample-cycle measurements (also high), and the drone's spectrum confirms
them for omlead.

## 5. For the MSX

Music plays only on front-end screens (intro, story, rank selection, high
scores; [amiga-intro.md](amiga-intro.md)), where no sound effects play. So
the whole PSG and all nine FM channels are free for it. Inferred from the
game's flow.

### What to emulate

- Notes with lengths in ticks and a **hard release at the gate** (about
  90 %): staccato is part of the sound.
- Sustain/tie runs (one long note), rests, the volume 30 on the drums.
- The restart after a sustained note can be a plain new note.
- **No** vibrato, arpeggio, portamento or tempo changes: none are used.
- Timing: run ticks from the field interrupt with a fractional
  accumulator (ticks per field, 8.8 fixed point). PAL 50 Hz: 236/256
  (subsong 0) or 253/256 (others). NTSC 60 Hz: 197/256 or 211/256. The
  jitter is at most one field (20 or 16.7 ms), below the shortest note
  (6 ticks, 121 ms).
- Amplitude shapes, for software envelopes: brass rises over ~0.3 s and
  swells in its loop; bass and drone attack fast and decay to ~60 %;
  kick ~0.4 s, snare ~0.2 s.

### MSX-MUSIC (YM2413) mapping: rhythm mode, 6 melodic channels

| Amiga track | Songs 0, 1 | Songs 2, 4 |
| --- | --- | --- |
| 0 | FM 0: Trumpet (7) or Horn (9), melody | FM 0: Organ (8) or Synthesizer (10), drone C2 |
| 1 | FM 1: Horn (9), harmony, a little quieter | FM 1: same, C1 (the OPLL plays 32 Hz; the timbre's harmonics carry it) |
| 2 | FM 2: Synth bass (13) or Acoustic bass (14) | FM 2: same drone at C1 instead of C0 (16 Hz is sub-audible), or leave it out |
| 3 | Rhythm: bass drum and snare drum | Song 2: FM 3, Trumpet (7), brass fanfare. Song 4: rhythm snare |
| Song 2 accents | – | Mechanic1: rhythm cymbal + tom (or a PSG noise swell). Low snare: rhythm tom |

FM 3..5 stay free for doubling (a second brass an octave up, as the
original's "room" sample suggests) or for a custom instrument. The PSG
can play along or stay silent. Inferred (an arranging choice).

### PSG only (AY-3-8910: 3 tones + noise)

Tone range at 1,789,773 Hz: 27.3 Hz (period 4095) and up. Every note of
the songs except the C0 drone fits.

| | A | B | C |
| --- | --- | --- | --- |
| Songs 0, 1 | Melody (track 0) | Bass (track 2) | Harmony (track 1), interrupted by drum hits: noise for the snare, a falling tone (or noise) for the kick, then the harmony resumes |
| Song 2 | Drone C2 | Drone C1, or the hardware envelope as a 16–32 Hz sawtooth (shape 8, period = 1,789,773 / 256 / *f*: 427 for C0) | Brass fanfare; accents as noise |
| Song 4 | Drone C2 | Drone C1 (or the envelope sawtooth) | Snare as noise with a short volume decay |

The harmony on songs 0/1 holds half and whole notes, so the drum hits
(at most 6 ticks of noise) take little from it. Inferred.

### Data size

Kept as patterns, with 3-byte pattern-list entries (a 16-bit pointer and
a transpose byte) and the 2-byte entries unchanged: 480 + 430 + 444 + 296
= **1,650 bytes** for the four unique songs (subsong 3 is subsong 1).
Unrolled to a flat list of 2-byte note events: 584, 460, 248 and 324 bytes
(1,616). Either way, the music and a replayer (well under 1 KB of Z80) fit
in one 8 KB ROM bank with room to spare. Confirmed (counted by
`--summary`; the replayer size is an estimate).
