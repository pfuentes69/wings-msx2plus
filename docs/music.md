# Music

Updated 2026-11-20. This is the original's music, decoded from `wofsongs`
([research/amiga-music.md](research/amiga-music.md),
`tools/decode_songs.py`). It plays where the original plays it
([research/amiga-intro.md](research/amiga-intro.md)), on MSX-MUSIC when the
machine has it and on the PSG otherwise.

## Where

| Screen | Subsong | Loop |
| --- | --- | --- |
| Intro: title, credits | 1 (brass melody and harmony, synth bass, kick and snare; C major) | 23.3 s |
| Intro: the story | 2 (a C drone, then a brass fanfare), shortened | 23.3 s (the original's 54.3 s) |
| Rank selection | 4 (the C drone, a military snare) | 27.2 s |
| Briefing, weapon selection, play, "THE END" | none | — |

- **The story's song is shortened** (the user, 2026-11-20). The original
  holds its C drone alone for 38.8 s before the brass comes in at bar 21,
  over a 75 s scroll. The port's story is three pages, read sooner. So the
  converter cuts ticks 384..1920 from all four tracks (`CUTS`):
  - 4 bars of drone (7.8 s), then the original's bars 21..28;
  - the drones carry on across the cut;
  - the two hits come earlier with the fanfare;
  - the song loops every 23.3 s.
- Subsong 0 (high scores) is converted too, but nothing plays it: the
  high-score table is set aside.
- A change of song fades the old one out first: a 3 dB step every 8
  fields, about 2 s, as the original's (0x2470).
- Leaving rank selection fades the music out over the briefing. In play
  there is never music: a quick start cuts the fade.

## How it plays

**MSX-MUSIC** (rhythm mode). Each of the original's four tracks has its
FM channel (0..3), and the drums are rhythm hits:

| Song | Track 0 | Track 1 | Track 2 | Track 3 |
| --- | --- | --- | --- | --- |
| 0, 1 | trumpet | horn | synth bass (an octave up) | bass drum, snare |
| 2 | organ, C2 | organ, C1 | synthesizer, C0 an octave up; cymbal and tom hits | trumpet fanfare |
| 4 | organ, C2 | organ, C1 | synthesizer, C0 an octave up | snare |

The PSG stays quiet.

**PSG alone.** Three channels:

| Song | Channel A | Channel B | Channel C |
| --- | --- | --- | --- |
| 0, 1 | melody | bass (an octave up) | harmony; each drum hit takes it over while it sounds |
| 2 | drone C2 | drone C1 | fanfare, and the two hits |
| 4 | drone C2 | drone C1 | snare |

- **Drums:**
  - the kick is a tone falling over about 7 fields;
  - the snare is noise (period 7);
  - the metal hit is high noise (period 1).
- The C0 drone (16 Hz) is left out on the PSG.

The original's notes are cut hard at their gate (about 90% of their
length). That is kept: a note sounds for its gate, then its key is
released.

## The data

`tools/convert_music.py` writes `src/generated/music_data.c` (about 2.2
KB), in segment 47 with the player. Each track is a byte stream:

| Bytes | Meaning |
| --- | --- |
| `0x00..0x7F` | A note, its sounding MIDI pitch. Then its gate and the ticks to the next command, each 1..255, or 0 and a 16-bit value. |
| `0x80 + i` | The song's instrument *i*. |
| `0x90 + a` | Attenuation (3 dB steps). |
| `0xA0` | A rest. |
| `0xFF` | Loop. |

- An instrument names an FM preset or rhythm drum with an octave shift,
  and a PSG channel or drum kind.
- The tables give the PSG tone periods and the OPLL block and F-number for
  MIDI 12..107.
- `assets_msx/music/song<N>.txt` lists the streams.

## The player

`src/msx/music.c` (segment 47, about 2.8 KB of code).

- **The tick.** It runs each field from the line interrupt
  (`Sound_Field` in `src/msx/sound.c`). The interrupt maps segment 47 into
  window 3, calls `Music_Field`, and puts back the segment the shadow
  `g_Bank3Segment` names. Every window-3 switch now writes the shadow
  before the mapper (`msx/banking.c`, `msx/mission_streamer.c`), so the
  shadow never names an older segment than the mapper holds.
- **The tempo.** It adds 256ths of a tick each field, so the tempo is
  the original's on both field rates:

  | Field rate | Subsong 0 | Others |
  | --- | --- | --- |
  | PAL | 236 | 253 |
  | NTSC | 197 | 211 |

  A tick is 20.21 ms (21.65 ms for subsong 0), from the original's CIA
  timer.
- **Starting and stopping.** `Music_Update(phase, cursor)` runs once a
  frame from the main loop. It starts, fades and stops the songs.
  - While it sets the chips up, `g_Music` = 2 holds the interrupt off.
  - Stopping gives the FM chip back to the effects (`Sound_FMSetup`: the
    engine's instrument, the drums' pitches, the driver's state).
  - The effects' driver then writes every PSG register again.
- **Cost.** At most 4 OPLL writes a note (key off, F-number, instrument
  and volume, key on), with the chip's waits. A tick with all four tracks
  starting a note takes about 2,000 T-states. Only front-end screens play
  music, so the interrupt has time.

## Verification

- `tests/test_music.py`:
  - the streams, read back as the player reads them, give the decoded
    notes (start, pitch, gate, instrument, volume) and each track's loop;
  - the pitch tables are within 10 cents;
  - the tempo is within 0.5% on PAL and NTSC;
  - the generated files are current.
- `verify_p0`, also with `--no-fm`:
  - the intro and rank selection have the player running;
  - with MSX-MUSIC, the PSG is quiet;
  - play never has music;
  - elsewhere, once faded, silence.
- `tools/preview_music.py OUTPUT` records the music as the game plays it,
  on MSX-MUSIC and on the PSG alone. Against UADE renders of the original
  (2026-11-20):

  | Song | Chip | Pitch classes over time | Onsets |
  | --- | --- | --- | --- |
  | 1 | MSX-MUSIC | 0.79 | in step |
  | 1 | PSG | 0.91 | in step |
  | 2 | both | 0.95 | |
  | 4 | MSX-MUSIC | 0.87 | in step |
  | 4 | PSG | 0.89 | in step |

  The pitch-class figure is a similarity; the same music a semitone off
  scores about 0.15. "In step" means the drum onsets line up within 10 ms.

## Not done

- The instruments are a first choice, not yet tuned by ear.
- The intro's title shows during loading before the music starts. The
  line interrupt is enabled only at the end of boot.
