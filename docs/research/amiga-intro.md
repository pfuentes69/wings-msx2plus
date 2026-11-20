# Amiga intro, attract loop and music: executable findings

Recovered 2026-11-20 by static 68000 disassembly (Capstone) of
`reference_assets/original_files/Wings_of_Fury/wings`, the music player
`songplay` and the song file `wofsongs`, with the conventions of
[amiga-hiscores.md](amiga-hiscores.md) and
[amiga-player-crash.md](amiga-player-crash.md). Code addresses are CODE-hunk
offsets (file offset = 0x28 + address). Variables are A4-relative
(`-$xxxx(a4)` is DATA offset `0x7FFE - xxxx`), and `jsr -$xxxx(a4)` goes
through a `jmp abs.l` stub in the DATA hunk. Frame counts are VBlanks
(`WaitTOF`), so they are 50 Hz on PAL and 60 Hz on NTSC. Nothing was
observed running on an Amiga. Each claim is marked **confirmed** (read
from the code or data) or **inferred** (what the code implies).

The disk is a cracked release (`[a]`; `s/text` is a "Hysteria" crack
intro). That matters for the copy protection (section 6).

## Summary

- **The intro runs once per program start.** 0x8022 is called only from
  0x0062, before the main loop's label 0x0066. Game over and demo playback
  go back to 0x0066 (rank selection), never to the intro. **Confirmed.**
- **Order:** start-up loading → (copy protection, patched out of this
  binary) → **story scroll** "A Time of Fury" → **Brøderbund presents** →
  **title** (`wingstitle`) → **credits** (`creditscreen`) → rank selection.
  The story comes **first**, before the Brøderbund logo. **Confirmed.**
- **The story** is white `newarmyfont` text on black, in a 640-px hires,
  1-plane display. It scrolls **up 1 line every 4 frames** (12.5 lines/s
  PAL). A new text line enters at the bottom every 14 lines (56 frames). The
  copper fades the text in over the bottom 16 lines and out over the top 16.
  53 lines are printed, fully justified to 615 px. Unskipped, it lasts
  **939 steps = 3756 frames (75.1 s PAL, 62.6 s NTSC)**, then fades out in
  32 frames. **Confirmed.**
- **The pictures:** Brøderbund logo only (the "presents" bar stays black)
  for 60 frames, then the "presents" bar fades in. Then the next picture
  loads from disk, and the screen holds for 120 more frames. Title: 300
  frames. Credits: 600 frames. Each change is a fade to black, a page flip
  and a fade in. **Confirmed.**
- **Skipping:** only the **fire button or left mouse button** (CIA-A PRA
  bits 7/6). Keys do nothing. A press during the story ends the story only.
  A press on any of the three pictures ends the whole picture sequence (fade
  out, go to rank selection). **Confirmed.**
- **Music** (Kris Hatlelid replayer `songplay`, CIA-A timer A, independent
  of PAL/NTSC). Every song loops.

  | Subsong | Where it plays |
  | --- | --- |
  | 2 | Story |
  | 1 | Brøderbund, title and credits |
  | 4 | Rank selection |
  | 0 | Name entry and high-score table |
  | 3 | Never used. Same song as subsong 1 |

  Each change fades the old song out first, for about 2 s, and the game
  waits for the fade. Music **stops** (fade, then unloaded) when rank
  selection ends. The briefing, weapon selection, the game, mission
  complete and promotion have **no music**. **Confirmed.**
- **Attract mode:** no title loop. On rank selection, 1800 frames (36 s
  PAL) without input start a **demo playback** of the file `wofdemo`. The
  demo ends back on rank selection, without high scores. This disk has no
  `wofdemo`, so the timeout just starts a normal game at the highlighted
  rank. Confirmed for the control flow; that a missing file loads as 0 is
  inferred.
- **The "Brøderbund Presents ... Wings of Fury !" credits ticker** (DATA
  0x8dd) is **not referenced anywhere** in the code or data. It is never
  shown. **Confirmed** by scanning every A4 displacement, relocation and raw
  word.

## Routines and variables

| Address | Role | Confidence |
| --- | --- | --- |
| 0x0000..0x0062 | Start-up: libraries/display (0x2570, 0x2910, 0x6670), loading (0x34bc: font 0x2794, shapes 0x29dc…), then `move.w #1,d0; tst.w d0; beq quit` at 0x0058, then the intro | Confirmed |
| 0x8022 (stub `-$7e5a`) | The intro sequence. Only caller: 0x0062 | Confirmed |
| 0x7e80 | Story scroll | Confirmed |
| 0x7d4e | Builds the story's user copper list: colour 1 gradients and the plane-pointer wrap | Confirmed |
| 0x5a8c → 0x5956 | Render a string in `newarmyfont` into a 640-px line buffer, optionally justified, then `BltTemplate` it at the RastPort pen | Confirmed |
| 0x6a60 | Story display: both buffers 640×200, 1 plane; field +0xa6 = 5, +0xa2 = 230 | Confirmed values; field meaning inferred |
| 0x6ad8 | Picture display: both buffers 320×200, 5 planes, palettes black | Confirmed |
| 0x7422 | Load an ILBM into the **back** buffer, copy its CMAP to a caller buffer, black the buffer's palette | Confirmed |
| 0x6fc4 | Flip: show the back buffer (0x6f20, swap pointers and set `COP1LC`), then wait one VBlank (0xaa3e) | Confirmed |
| 0x7084 | Fade the shown palette to a target in 16 steps (step/15 interpolation, 0x6ff6). Its second argument is never read | Confirmed |
| 0x73b0 | Fade to black (0x7084 with an all-zero palette) | Confirmed |
| 0x6eee | Wait N frames (`WaitTOF`), or less if a button is down; returns the button state | Confirmed |
| 0x1044c (stub `-$7d40`) | Button: 1 if CIA-A PRA bit 6 (left mouse) or bit 7 (joystick port 2 fire) is low | Confirmed |
| 0x23dc | `play_song(name, n)`: songplay commands 6/5 (fade old, wait), 1, 2 | Confirmed |
| 0x2470 | `stop_music()`: fade, wait, close timer, `UnLoadSeg` both files | Confirmed |
| 0x8262 | Rank selection (music 4, idle timeout → demo) | Confirmed |
| 0x8194 | Menu input: up/down/Return/fire; with a non-zero argument, returns 1000 after 1800 idle frames | Confirmed |
| 0xf41a (stub `-$7d6a`, no caller) | Copy-protection prompt | Confirmed (routine); its removed call site inferred |
| `-$5672` / `-$566e` | Pointers to the story text (CODE 0x7494) and to an 80-space line (0x7cfc, used at 0x89e4) | Confirmed |
| `-$56b2` (DATA 0x294c) | Brøderbund "logo only" palette | Confirmed |
| `-$5b07` | Sound off (toggled by `s` in play at 0xcd5a, cleared at 0x006a before every rank selection) | Confirmed |
| `-$42b2` | Demo mode: 0 none, 1 playback, 2 record | Confirmed |

## 1. The start sequence

### Program start (0x0000..0x0066)

```
0x000e..0x0054  init: timers, libraries, display structures, file loading (0x34bc)
0x002c          argc > 1: -$4078 = "wofdemo"      ; enables demo recording later
0x0058          move.w #1,d0 ; tst.w d0 ; beq quit ; the copy-protection call site (section 6)
0x0062          intro()                           ; 0x8022, once
0x0066 loop:    ...; clr -$5b07 (sound on); rank_selection() 0x8262; briefing; game ...
0x020a          bra 0x0066                        ; after every game, demo or Ctrl-R
```

All confirmed. The intro is not reached again.

### The intro (0x8022)

```
play_song("wofsongs", 2)
story()                                   ; 0x7e80, section 2
play_song("wofsongs", 1)                  ; fades subsong 2 out first (~2 s, blocking)
picture_display()                         ; 0x6ad8: 320x200x5, black
load "shapes/broderbund" → pal            ; back buffer
flip(); fade_to(-$56b2)                   ; logo only
if wait(60):  goto out
fade_to(pal)                              ; "presents" bar appears
load "shapes/wingstitle" → pal            ; into the hidden buffer, disk time
if wait(120): goto out
fade_to_black(); flip(); fade_to(pal)     ; title
load "shapes/creditscreen" → pal
if wait(300): goto out
fade_to_black(); flip(); fade_to(pal)     ; credits
wait(600)
out: fade_to_black()
```

Confirmed. Details:

- **Brøderbund, two stages.** The `broderbund` ILBM is 320×200, 4 planes.
  The logo (crown and "Brøderbund", colours 3..8, y 33..117) uses the same
  colours in both palettes. The grey "presents" bar (colours 9..15,
  y 121..142) is black in the first palette (`-$56b2`: `000 ECA 730 026 038
  02B 03D 07E 05F` then black) and grey in the picture's CMAP (`555 666 777
  888 999 AAA CCC`). So the logo fades in alone, holds for 60 frames, then
  "presents" fades in. Confirmed from the palette data and the decoded
  bitmap.
- **Load time is part of each hold.** Each next picture is decoded into the
  hidden buffer **before** the current screen's wait. The Brøderbund screen
  stays up for the `wingstitle` load (30 KB from floppy) plus 120 frames,
  the title for the `creditscreen` load plus 300 frames. Confirmed order;
  the disk time is unmeasured.
- **Fades** have **16 steps**, interpolating each RGB nibble by step/15.
  The routine does **not wait for a frame** between steps. It rebuilds and
  installs the copper list each step, so its speed is the CPU's: about 32
  colours × 3 divisions plus a copper-list build per step. Estimated a few
  frames per fade (about 0.1 s on an A500), not measured. The flip itself
  waits one VBlank. Confirmed structure, inferred duration.
- **No colour cycling.** `broderbund` and `wingstitle` carry CRNG chunks,
  but the ILBM reader only knows BMHD, CMAP and BODY. Confirmed (no CRNG
  constant in the code).
- **Skip.** `wait()` (0x6eee) polls the button every frame. A press on the
  Brøderbund, title or credits screen jumps to `out`, so one press skips
  everything left, straight to rank selection. The credits' wait result is
  ignored, since the next step is `out` anyway. If the button is still held
  from the story, the first `wait(60)` sees it at once. That is unlikely,
  because the story's fade and the music fade take more than 2 s. Confirmed
  control flow.

### After the intro: rank selection and the attract loop

0x8262 plays subsong 4, shows `selectrank` (fade in) and reads input
through 0x8194 with the timeout on:

| Input (0x8194) | Result |
| --- | --- |
| Cursor up (raw 0x4c), joystick up | Previous rank (wraps 0 ↔ 7) |
| Cursor down (0x4d), joystick down | Next rank |
| Return (0x44), keypad Enter (0x43), fire, left mouse | Choose |
| Nothing for **1800 frames** since the last call | Returns 1000: demo playback (`-$42b2` = 1), as if chosen |

The idle counter is local to 0x8194 and counts one `WaitTOF` per loop
(0x8206), so the timeout is measured from the last move. Confirmed.

With demo playback, 0x845e loads `wofdemo`. Its first byte gives the rank,
and the game runs from recorded input. If the file is missing, the loader
returns 0 (inferred: the `Lock` failure branch at 0xff4a, with DOS
requesters off via `pr_WindowPtr = -1` at 0x25dc). The mode is then cleared
(0x8476) and an ordinary game starts at the highlighted rank. The recovered
disk has no `wofdemo`. A started demo ends on the game-over branch, which
skips the high scores for playback (amiga-hiscores.md) and returns to 0x0066.

Rank 7 ("Return from R&R") calls 0x8b96, read as loading a saved game
(inferred from the "Loading game..." path at 0x9136). Every exit from rank
selection goes through `stop_music()` at 0x84d6. Confirmed.

## 2. The story scroll (0x7e80)

### Display

- 0x6a60 sets both display buffers to **640×200, 1 plane** (hires, two
  colours). It writes 5 to field +0xa6, read as the viewport's first line,
  and 230 to field +0xa2 (meaning not traced). The front buffer is shown.
  Palettes start black. Confirmed values; the meaning of the two fields is
  inferred.
- **No background picture.** Colour 0 stays black. Text is drawn in pen 1.
  Confirmed.
- **Colour 1 comes from a user copper list** (0x7d4e), rebuilt every step.
  Its waits are absolute display lines (0x9a9c adds 0x2c):

  | Screen line | COLOR01 |
  | --- | --- |
  | 5 + i, i = 0..15 | `i × 0x111` (black → `FFF`) |
  | 21..185 | `FFF` (the last value set) |
  | 201 − i, i = 15..0 | `i × 0x111` (`FFF` → black) |
  | from 201 down | black |

  So the text is a window over screen lines 5..201. Lines fade in over the
  bottom 16 lines and out over the top 16. Confirmed.

### Scrolling

- The bitmap is a **210-line ring** (15 text lines × 14). Each step adds 80
  bytes (one hires line) to the plane pointer (bitmap `-$41c6` +8). The
  copper resets `BPL1PT` to the bitmap's start at viewport line `d5` (210
  down to 1), which closes the ring. After 210 steps the pointer and `d5`
  are reset. Confirmed.
- **Direction: up**, 1 line per step. Confirmed.
- **Speed: 1 line per 4 frames.** One step is `wait(2)`, rebuild and
  install the copper list, `wait(2)`. That is 12.5 lines/s on PAL and 15 on
  NTSC. Confirmed (`WaitTOF` counts).
- **A new text line every 14 steps** (56 frames, 1.12 s PAL). The line
  slot is cleared with `SetAPen(0)` and `RectFill(0, y, 639, y + 11)`. Then
  pen 1, `Move(0, y)` and the printer. The slot is always viewport row 196
  (screen line 201, the bottom edge, still black). Each line reaches full
  white after 16 steps, crosses the window in about 196 steps (15.7 s PAL)
  and fades out at the top. About 14 lines are on screen at once.
  Confirmed.

### Text layout

- Font: the game's **`newarmyfont`** (12 px high, proportional, the
  font at `-$4094`). Each glyph advances its width + 1 px, and a space
  advances 10 + 1 px. The font is drawn at hires pixels, so it looks half as
  wide as in the low-res screens. Confirmed.
- **Line breaks are stored.** The text is a run of NUL-terminated strings
  (CODE 0x7494..0x7cfa). The walker steps `p += strlen(p) + 1`, one string
  per line. A doubled NUL is an empty string, which draws a blank line.
  Confirmed.
- **Justification.** If the byte after a line's terminator is non-zero (the
  line is not followed by an empty string), the line is spread to
  **615 px**. The extra pixels are divided over the gaps between all
  characters, not just spaces; the remainder goes one pixel each to the
  first characters. Paragraph-ending lines and the title are drawn at their
  natural width. Lines start at x = 0. The stored text also has
  hand-placed extra spaces: it was laid out for 48 columns. Natural widths
  are 552..615 px for the full lines, so justification adds 0..1.3 px per
  character. Confirmed.
- The title has 17 leading spaces: x 187..368, roughly centred in the
  615-px column. Confirmed by measurement with the font's widths.

### Length and end

- **53 strings are printed**: the title, 2 blanks, paragraph 1, blank, …,
  the last paragraph (the listing below). Confirmed.
- The loop ends **210 steps after the 53rd line was printed**: step 728 +
  210, 939 steps in total. By then the last line has left the top. That is
  **3756 frames: 75.1 s PAL, 62.6 s NTSC**. Confirmed.
- **Fire or the left mouse button** ends it early. The check runs once per
  step, after the second `wait(2)`, so it reacts within 4 frames. Keys don't
  end it. Confirmed.
- **The fade-out:** 16 more steps (`wait(2)` each, 32 frames). The
  gradient's peak drops from `F` to 0, and the scroll stops. Then
  `play_song(1)`. Confirmed.

### The text, verbatim

Stored at CODE 0x7494 (pointer `-$5672`). One line per stored string,
spaces exactly as stored. `[J]` marks lines drawn justified to 615 px;
unmarked lines are drawn at natural width. Empty lines are empty strings.
The original's spelling is kept ("it's opponents").

```
                 A Time of Fury


    It  is 1944 and the world is at war.  Europe    [J]
is  ablaze with a conflict that engulfs her like    [J]
the   flames   of   hell,   leaving  a  path  of    [J]
destruction  wherever  it  burns.  The Far East,    [J]
too, is being consumed by a furious struggle for    [J]
dominance.   In  the Pacific theater, the allies    [J]
face  an  enemy  possessed of  great skill and a    [J]
relentless determination.  As the tide begins to    [J]
turn in favor of the allies, the enemy struggles    [J]
ever  more desperately to maintain the footholds    [J]
it had gained earlier in the war.

    However, both on the sea and in the air, the    [J]
U.S.   Navy  proves  to be more than a match for    [J]
it's  opponents.   One  reason  for  this is the    [J]
incredible  striking  power  of  the  Navy's Air    [J]
Force.   It  is  instrumental  in  defeating the    [J]
enemy in battle after battle.  Within the Navy's    [J]
air  command,  one plane seems to be leading the    [J]
fight  for  an  allied  victory:  the mighty F6F    [J]
Hellcat!


     The  Hellcat  is  incredibly  powerful  and    [J]
durable,  a  real  work horse capable of bearing    [J]
bombs,   rockets   and   torpedoes.    Able   to    [J]
outmaneuver the enemy's best fighter planes, the    [J]
Hellcat   has   established   one  of  the  best    [J]
kill-to-loss ratios in the war.

    Now  you  have  the  opportunity to fly your    [J]
very own Hellcat.  You'll be assigned to provide    [J]
air  support  for  the  USS Wasp.  This aircraft    [J]
carrier  has  been heavily damaged and must make    [J]
its   way safely back to port.  On this perilous    [J]
journey,  you  must  defend  the carrier against    [J]
torpedo  bombers,  rout  the  enemy  from  their    [J]
island  strongholds, sink enemy vessels that lie    [J]
en  route  to  home port and protect yourself by    [J]
shooting down enemy planes.

    Strapping  yourself  into  the  cockpit, you    [J]
face  a  tremendous responsibility.  The fate of    [J]
the  carrier  and  every  man  onboard  has been    [J]
placed in your experienced hands.  As the signal    [J]
officer gives you the go, you give your Cat full    [J]
throttle  and  take  off  into the unknown skies    [J]
before  you.   Just  minutes  off  the deck, you    [J]
sight  the  first  sign  of  trouble:  a pair of    [J]
enemy fighters bearing down on you from above...
```

The `[J]` tags and the column before them are annotations, not part of the
strings. Every full line is exactly 48 characters. The doubled blank lines
after the title and after "Hellcat!" are two empty strings each (the stored
bytes are `…Fury\0\0\0` and `Hellcat!\0\0\0`). Confirmed. The last empty
string before each paragraph also has the justify flag set (the next byte is
the paragraph's first character), but it draws nothing (length 0).

## 3. The "Brøderbund Presents …" ticker

```
 Brøderbund Presents ... Wings of Fury !      Produced by Unlimited Software Inc. Original design by Steve Waldo, Amiga version by Colin Fox, graphics by John Boechler, music by Kris Hatlelid.
```

The string is at DATA 0x8dd (`-$7721`). It starts with a space, the `ø` is
byte 0xF8, and it is NUL-terminated. **Nothing refers to it.** No A4
displacement, relocation or raw longword points at or near it. It sits in a
cluster of other unreferenced DATA strings: `shapes/selectrank` and
`shapes/rank.iff` (the code uses its own PC-relative copies), and a
`TextAttr` for `army.font` 12 at `-$7446`, also unused. The in-game ticker
(pointer `-$5848`, fed character by character at 0x18d4) is only ever given
game messages (mission, island and sunk bonuses) and the debug
version/memory strings (0xce76, 0xcfe2).
**Confirmed: the credits ticker is dead data in this build.** It is probably
left over from an earlier version (inferred). The same credits appear on the
`creditscreen` picture.

## 4. Music

### The replayer

`songplay` is a separate HUNK program, the Kris Hatlelid replayer. Its
symbols survive. The game `LoadSeg`s it and `wofsongs` on the first
`play_song`, and calls the player's entry with a command in d0. Confirmed.

| Command | songplay routine | Used by the game |
| --- | --- | --- |
| 0 | `_OpenTimerInt`: `ciaa.resource`, interrupt on CIA-A timer A, starts the timer | First `play_song` |
| 1 | `_ReadInstruments` (d1 = subsong, d2 = module) | Every `play_song` |
| 2 | `_PlaySong` | `play_song`, unless sound is off (`-$5b07`) |
| 3 | `_StopSong` | No |
| 4 | `_CloseTimerInt` | `stop_music` |
| 5 | `_GetSongStat` (0 stopped, 2 playing, 4 fading…) | Polled until 0 after a fade |
| 6 | `_FadeSong` (d1 = speed) | Speed 2, before every change and in `stop_music` |
| 7..12 | Sound effects, pause, restart | No. The game plays its effects itself (`SoundFX_IntHandler`) |

- `play_song` with a song already loaded fades it (speed 2), **busy-waits**
  until it has stopped, then reads and starts the new subsong. `stop_music`
  also unloads both files, so the next `play_song` (at game over) reloads
  them from disk. Confirmed.
- **Fade length:** every 3 ticks each track's volume drops by 1. Track
  volumes start at 32 (song 0/1 track 3 is set to 30). So a fade takes
  about 99 ticks, **≈ 2.0 s**, during which the screen does not change.
  Confirmed (songplay 0x30a, initial volume `$20` at 0x382).
- **Tempo:** one tick per CIA-A timer A underflow. Songs set only the timer's
  high byte (command 0xdd: 60 for subsong 0, 56 for the others). The low
  byte is never written (its value is unknown; ≤ 1.8 % effect). A tick is
  hi × 256 / 709 379 s on PAL (715 909 on NTSC): **21.65 ms** (hi 60) or
  **20.21 ms** (hi 56). The rate is the same on PAL and NTSC within 1 %.
  Confirmed. Note durations come from songplay's table at data $254 (96,
  48, 32, 64, 24 … ticks). A quarter note of 24 ticks is ≈ 0.49 s (≈ 124
  bpm) at hi 56 and ≈ 0.52 s (≈ 115 bpm) at hi 60. Inferred musical
  reading.
- **Looping:** each track's pattern list ends with command 0xdb (restart
  the sequence), never 0xda (stop). **All songs loop forever** until faded.
  Confirmed by walking all four tracks of every song.

### Subsongs

`wofsongs` symbols: `songs` (5 pointers), `song1`..`song4`, `voice0..6`,
six 8SVX instruments ([audio-extraction.md](../audio-extraction.md)).

| Subsong | Definition | Loop length (ticks) | Loop length | Tracks: patterns | Played |
| --- | --- | --- | --- | --- | --- |
| 0 | song1 (0x14) | 1536 | **33.3 s** (hi 60) | 17 per track | High scores: name entry and table (0x9868) |
| 1 | song2 (0x40) | 1152 | **23.3 s** | 13 | Intro pictures: Brøderbund, title, credits (0x8040) |
| 2 | song3 (0x6c) | 2688 | **54.3 s** | 29 | Story scroll (0x802e) |
| 3 | song2 (0x40) | 1152 | 23.3 s | 13 | **Never** (no call with 3) |
| 4 | song4 (0x9c) | 1344 | **27.2 s** | 15 | Rank selection (0x8272) |

Lengths assume a low timer byte of 0 (add up to 1.8 %). All four tracks
of each song have the same length. Confirmed: the only `play_song`
calls are 0x802e, 0x8040, 0x8272 and 0x9868. The only `stop_music` calls
are 0x0216 (quit), 0x84d6 (end of rank selection) and 0x9146 (loading a
saved game).

### When music plays

| Screen | Music | Starts | Ends |
| --- | --- | --- | --- |
| Start-up loading | none | – | – |
| Story | subsong 2 | Before the story display. The first call also loads the two files from disk | Faded (2 s) after the story's own fade. An unskipped story (75 s PAL) hears it once and about 21 s of the repeat |
| Brøderbund → title → credits | subsong 1 | After the 2 s fade | Faded when rank selection starts. The pictures (≈ 21.6 s of waits plus loads) last about one loop |
| Rank selection | subsong 4 | At entry, after fading subsong 1 | `stop_music` on leaving (fade 2 s + unload) |
| Briefing, weapon selection, play, mission complete, promotion ticker, THE END | **none** | – | – |
| Name entry, high-score table | subsong 0 | At 0x9856's start (reloads both files) | Faded when the next rank selection starts |
| Demo playback | none | – | – |

Sound off: `s` during play toggles `-$5b07` (0xcd5a). While it is set,
`play_song` loads but does not start a song, and fades are not waited for.
It is cleared at 0x006a before every rank selection, so only the high-score
music can be silenced (if sound was off at game over). Confirmed.

## 5. Timeline (from program start, unskipped)

PAL frames; NTSC frames are the same counts at 60 Hz. "Disk" means floppy
load time, not measured.

| # | Screen | What happens | Duration | Skip |
| --- | --- | --- | --- | --- |
| 0 | (previous screen) | Init and loading (libraries, font, shapes; 0x34bc) | Disk | – |
| – | Copy protection | Removed in this binary (section 6) | – | – |
| 1 | (unchanged) | Load `wofsongs` + `songplay`; subsong 2 starts | Disk | – |
| 2 | Story | Scroll, 53 lines, white on black, 1 line / 4 frames | 3756 frames (75.1 s) | Fire / left mouse → step 3 |
| 3 | Story | Fade out | 32 frames | – |
| 4 | Black | Subsong 2 fades | ≈ 2.0 s | – |
| 5 | Black | Subsong 1 starts; load `broderbund` | Disk | – |
| 6 | Brøderbund | Fade in the logo only | Fade (~0.1 s, est.) | – |
| 7 | Brøderbund | Hold | 60 frames (1.2 s) | Fire → 14 |
| 8 | Brøderbund + presents | Fade in "presents"; load `wingstitle` behind | Fade + disk | – |
| 9 | Brøderbund + presents | Hold | 120 frames (2.4 s) | Fire → 14 |
| 10 | Title | Fade out, flip, fade in; load `creditscreen` behind | Fades + disk | – |
| 11 | Title | Hold | 300 frames (6 s) | Fire → 14 |
| 12 | Credits | Fade out, flip, fade in | Fades | – |
| 13 | Credits | Hold | 600 frames (12 s) | Fire → 14 (same) |
| 14 | Black | Fade out; return to the main loop | Fade | – |
| 15 | Black | Subsong 1 fades | ≈ 2.0 s | – |
| 16 | Rank selection | Subsong 4; idle 1800 frames → demo | Until a choice | Up/down, Return/fire |

## 6. Copy protection

- **Routine 0xf41a** (stub `-$7d6a`). It sets up a display (0x6b60), picks
  one of 33 entries of a 16-byte table at `-$4930` from the beam position
  (`VHPOSR` mod 33), and prints with the game's printer (0x8570):
  "   You are required to enter a / word from the manual, which is /
  specified below. /     Do not count the paragraph / headings,  and  do
  not  enter / punctuation. / Please enter the word at - / PAGE %d  LINE %d
  WORD %d". It reads up to 9 characters with the line editor 0x6086, then
  fades to black. It returns 1 if the input is `spaz` (a back door) or the
  entry's (decoded) word. Confirmed.
- **No caller.** Nothing calls the stub or the routine. At 0x0058 the start
  code has `move.w #1,d0; tst.w d0; beq quit`. That is a 4-byte
  `move.w #1,d0` exactly where a 4-byte `jsr -$7d6a(a4)` would sit, and a
  0 result quits the program. Inferred: the cracker replaced the call. In
  the original it ran **after the start-up loading and before the music
  and the story**.
- The port will not have it.

## Other strings asked about

- "User requested abort." (CODE 0x817e) is printed by 0x816c, the C
  library's Ctrl-C handler. Its callers are 0x12920 (a `SetSignal` break
  check) and 0x11d26 ("no math library"). It quits through 0x020e. It is
  not part of the intro. Confirmed.

## How the MSX port can use this

- Sequence: story → Brøderbund (logo, then "presents") → title → credits
  → rank selection, once per power-on. After game over, go to high scores →
  rank selection, never the intro. Fire skips the story alone, and fire on
  a picture skips the rest of the pictures.
- Holds in PAL frames: 60 + 120, 300, 600. NTSC uses the same counts, as
  the Amiga did, or ×6/5 to keep the seconds; the port's `Game_Wait`
  convention already handles this.
- Story: 1 px every 4 frames, a line every 14 px. The Amiga text is 615 px
  of hires: on SCREEN 5 (256 px) it needs a smaller font or re-wrapped
  lines, while SCREEN 6/7 (512 px) fits it at ×0.8. The fade bands are
  palette changes per line (a line interrupt on the MSX) or can be dropped.
  The 210-line ring scroll maps onto the VDP's vertical scroll (R#23) with
  one new line drawn every 14 steps.
- Music, if added: four songs (2 story, 1 pictures, 4 rank selection,
  0 high scores), all looping, about 2 s fades between them, silence from
  the briefing to game over.
- The attract demo needs a recorded `wofdemo`, and none exists. Without
  one, the original's timeout just starts a game, so the port can omit it.

## Open questions

- **Fade speed on screen.** 0x7084 runs its 16 steps without waiting for
  a frame. The visible duration depends on CPU speed (estimated 0.1 s on an
  A500). A capture of the original would settle it.
- **Disk load times** between pictures (they lengthen the Brøderbund and
  title holds) are unknown.
- **CIA-A timer A low byte** (tempo ±1.8 %) is never set by songplay.
- **Fields +0xa2 = 230 and +0xa6 = 5** of the story's display structure
  are read as the viewport height and first line, but this is not traced
  through 0xa0d4.
- **The protection's call site** at 0x0058 is an inference from the patch
  pattern. An uncracked executable would confirm it.
- **The dead credits ticker**: whether another release (or the NTSC/early
  version) shows it is unknown.

## Reproduce

The helpers were not committed. Parse the HUNK files (including
HUNK_RELOC32 and HUNK_SYMBOL; `songplay` and `wofsongs` keep their
symbols). Disassemble with Capstone (`CS_ARCH_M68K`). Resolve `jsr -$x(a4)`
through the DATA-hunk stubs. To find song lengths, walk each `wofsongs` song
→ 4 tracks → 6-byte sequence entries (pattern pointer, transpose) → byte
pairs (note < 0xd9 with a duration index; 0xd9 next pattern, 0xdb loop,
0xda stop, 0xdc instrument, 0xdd/0xde timer high/low, 0xdf volume).
