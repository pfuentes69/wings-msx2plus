# Audio extraction assessment

Inspected and extracted 2026-11-10, before further gameplay work.
The original ADF itself is absent from this repository. Its recovered files
already include the audio; no second disk traversal is needed for this step.
The unchanged source manifest still verifies all recovered bytes.

## Outcome

| Material | Result | Confidence / limit |
| --- | --- | --- |
| Eight files in `sounds/` | Eight sample-preserving WAV previews | Raw signed 8-bit mono interpretation supported; preview rate is assumed |
| Six embedded `FORM 8SVX` instruments | Exact standalone 8SVX files and six WAV previews | Headers, sample rates, sample counts and loop lengths recovered |
| `wofsongs` + `songplay` | Original two-file Kris Hatlelid module preserved | Recognized and successfully replayed by UADE |
| Five song slots | Four unique song definitions | Slots 1 and 3 reference the same definition |
| Music previews | Four valid, non-silent, 10-second stereo WAVs | Bounded previews, not complete tracks or a transcription |

Files are under `assets_src/audio/`. Both extraction and replay manifests
record source hashes. Original inputs are unchanged. No audio was added to
the MSX ROM and the viewer's code was left untouched.

## Effects

Source files: `boom`, `engine`, `grind.1`, `machinegun`, `metal.clang.1`,
`scream`, `screech`, `splash`, totaling 51,832 bytes.
They have no IFF/WAV rate header. Their byte distributions and waveform
continuity fit signed 8-bit samples. The game's sample-start helper takes a
raw address and length; minimal relevant disassembly supports headerless
sample playback. The host `file` utility's identification of `splash` as an
X11 font is a false-positive signature match.

The WAV conversion preserves every byte by changing signed Amiga PCM to
unsigned 8-bit WAV offset binary (`byte XOR 0x80`). No resampling,
normalization, clipping or trimming is applied. Round-trip tests recover the
original bytes exactly, including odd-length files.

**All eight effect WAVs use an explicitly assumed 8,363 Hz audition rate.**
This is a convenient preview setting, not an extracted per-effect truth.
Original playback changes pitch through Paula periods; some effects are
reused at different rates and the engine's pitch changes during gameplay.
For another audition rate, rerun `extract_audio.py --sfx-rate RATE` into a new
output directory. Rate assumptions are recorded for every effect.

Relevant static evidence in the original `wings` executable (file offsets):

| Setup offset | Sample association | Initial period word |
| --- | --- | ---: |
| `0x1faa` | machinegun | 200 |
| `0x1fcc` | engine | 380 |
| `0x1fee` | machinegun | 160 |
| `0x2010` | engine | 330 |
| `0x2032` | boom | 500 |
| `0x2054` | splash | 350 |
| `0x2076` | machinegun | 320 |

Associations come from the file-loading block at `0x3390–0x3474` and the
sample-control setup at `0x1f9e–0x208c`. The raw-play helper begins at
`0xea50`; the interrupt handler begins at `0xebd2`. These are observations
from a limited disassembly. At `0xecfe`, it copies the stored period into
the channel's Paula `AUDxPER` register (offset 6 from its audio-register base).
This is not a complete runtime trace or complete effect
parameter inventory. In particular, don't assign one fixed sample rate to
each filename from this partial table.

## Instruments

`wofsongs` is an Amiga HUNK object with 276 bytes of code, a 39,020-byte
chip-memory data segment starting at file offset `0x1c4`, and four BSS bytes.
The extractor bounds-checks its segments, relocations and symbols; it does
not execute or relocate the object. Six complete, consecutive IFF containers
are embedded inside its data segment:

| Instrument NAME | File offset | Rate Hz | One-shot samples | Repeat samples |
| --- | --- | ---: | ---: | ---: |
| BassDrum3 | `0x0ddc` | 8363 | 3400 | 0 |
| sdrum1.iff | `0x1b8c` | 8363 | 1642 | 0 |
| RoomBrass2.iff | `0x225e` | 8363 | 1768 | 6548 |
| SyntheBass.iff | `0x4342` | 8363 | 7644 | 384 |
| omlead.iff | `0x6306` | 4181 | 3434 | 3042 |
| Mechanic1.iff | `0x7cba` | 8363 | 7374 | 64 |

All are uncompressed single-octave mono 8SVX, with unity volume. Each BODY
length equals its one-shot plus repeat counts. Standalone `.8svx` exports
match the original FORM bytes exactly. WAV exports play the stored waveform
once, using the header rate; they don't synthesize arbitrary musical notes
or sustain loops. Musical playback can choose different rates for notes.
The field interpretation follows the primary
[8SVX specification](https://wiki.amigaos.net/wiki/8SVX_IFF_8-Bit_Sampled_Voice).

## Music

[ExoticA's disk-rip inventory](https://www.exotica.org.uk/wiki/Wings_of_Fury)
identifies the format as Kris Hatlelid and lists a 41,328-byte
`kh.Wings_of_Fury` plus a 5,148-byte `songplay`, matching the recovered pair's
sizes. Independently, UADE identifies the local module as Kris Hatlelid,
reports subsongs `0..4`, loads the accompanying player, and produces valid
stereo PCM. Its replay documentation explicitly requires the matching
`songplay` beside two-file modules.

The extracted HUNK symbol table names four song definitions. The first five
32-bit data pointers are:

| Subsong | Data offset | Definition |
| --- | --- | --- |
| 0 | `0x14` | song1 |
| 1 | `0x40` | song2 |
| 2 | `0x6c` | song3 |
| 3 | `0x40` | song2 (shared) |
| 4 | `0x9c` | song4 |

Each definition begins with four track pointers and is followed by voice
references. The command format, timing and every note are decoded in
[research/amiga-music.md](research/amiga-music.md) (`tools/decode_songs.py`),
and which screen plays each slot is in
[research/amiga-intro.md](research/amiga-intro.md) §4.

`music/previews/subsong-{0,1,2,4}.wav` contain the first 10 seconds of each
unique definition. Slot 3 shares preview 1 because it references the same
source definition; it wasn't separately rendered. Previews use 44,100 Hz,
stereo, 16-bit PCM, with UADE's default playback/filter settings and the
one-subsong option. Their headers, frame counts, sample variation, nonzero
RMS and hashes are checked. They were not listening-validated against an
original-game recording. Full-track durations and looping remain unverified.

## Reproduce

The extractor uses Python's standard library only and refuses to overwrite
an output directory:

```sh
python3 tools/extract_audio.py reference_assets/original_files/Wings_of_Fury NEW_AUDIO_OUTPUT
python3 tools/extract_audio.py reference_assets/original_files/Wings_of_Fury NEW_OTHER_RATE_OUTPUT --sfx-rate 11025
```

Music rendering is an optional host research step using the GPL UADE replay
engine, not an MSX runtime dependency. Install UADE/libuade separately, then
build the small WAV front end (the Homebrew build can lack UADE's own WAV
writer; this front end consumes its public PCM API instead):

```sh
mkdir -p tools/.build
cc -Wall -Wextra tools/render_music.c $(pkg-config --cflags --libs libuade) -o tools/.build/render_music
tools/.build/render_music assets_src/audio/music/kh.Wings_of_Fury NEW_PREVIEW.wav 0 10
```

Arguments are module path, new output WAV, zero-based subsong, seconds limit.
The renderer refuses to overwrite a file. Keep the matching `songplay` next
to the module. It disables content-database updates and stops at the time
limit or song end, whichever occurs first. To investigate full songs, use a
larger limit; a limit hit is still not proof of complete duration.

For this session UADE 3.05 and its two libraries were built into the ignored
`tools/.build/audio-research/local/` prefix; no global package was installed.
The downloaded release SHA-256 values were checked against Homebrew's formula:

| Source | SHA-256 |
| --- | --- |
| UADE 3.05 | `1a2dd9fdf8cf47c4587dcc09df16f1bb49374a9e7f8f53cdb4816d50c87e4f4c` |
| libzakalwe 1.0.0 | `cb503c557b04f34069654083963a056deb85a6dea25ba4b69aaaa2bbf7290a98` |
| bencodetools 1.0.1 | `e41ae682525cf335b5f5ec0ba9b954abfe7b448e8ed13e2aa2a44e49fce2ca12` |

Sources: [UADE project/release](https://zakalwe.fi/uade/) and
[Homebrew formula](https://raw.githubusercontent.com/Homebrew/homebrew-core/HEAD/Formula/u/uade.rb).
Local compatibility adjustments matched the formula: omit the Linux soname
linker flag and allow the older libzakalwe's implicit function declarations.
The other two libraries and UADE were configured with the local prefix;
UADE's device front ends/write-audio feature were disabled. Rendering used
`DYLD_LIBRARY_PATH` pointing at the local library directory.
Capstone was used only for exploratory disassembly; it is not required by
the extractor, tests or game build.

Verification: `python -m unittest discover -s tests -v` in the project Pillow
environment: 29 tests pass, covering malformed audio containers, HUNK
truncation, exact waveform round trips, instrument fields, song slot mapping,
preview WAV integrity and the existing graphics/extraction checks.

## Consequence for the MSX port

Extraction is feasible and working; native playback is a separate task.
The effects alone contain 51.8 KiB of samples, while the current ROM target
is 32 KiB. The Amiga replay code and Paula sample channels cannot simply be
included in the Z80 game. The FS-A1WX's MSX-MUSIC is a sensible music target,
with PSG tone/noise effects as an initial baseline. That requires arranging
or transcribing the four song definitions and selecting FM instruments;
PCM previews are references, not an automatic FM conversion.

Before committing to sample-based effects, benchmark CPU cost alongside the
11.07 ms graphics redraw baseline. A practical next audio increment is one
PSG engine/explosion approximation and a short MSX-MUSIC phrase, compared
with these references. A complete event transcription or emulator capture
can follow if higher musical fidelity is needed. No sound driver was added
as part of this assessment.
