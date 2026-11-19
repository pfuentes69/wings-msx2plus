# Amiga game over and high scores: executable findings

Recovered 2026-11-19 by static 68000 disassembly of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-cannon.md](amiga-cannon.md): code addresses are CODE-hunk offsets
(file offset = 0x28 + address), variables are A4-relative (`-$xxxx(a4)` is
DATA offset `0x7FFE - xxxx`), and `jsr -$xxxx(a4)` goes through a `jmp abs.l`
stub at the start of the DATA hunk. Nothing was observed running on an Amiga.

**Confirmed** means the behaviour was read in the code (control flow,
constants, strings). **Inferred** means it is a reading of the evidence that
was not proven, for example what an OS call or a hardware bit means.

## Routines and variables

| Address | Role | Confidence |
| --- | --- | --- |
| 0x0112, 0x01c6..0x020a | Main loop: game-over branch that leads to the high-score sequence | Confirmed |
| 0x9856 (stub `-$7e30`) | High-score sequence. Its only caller is 0x0206 | Confirmed (raw scan for callers) |
| 0x9472 | Qualify, enter the name, insert, sort, save | Confirmed |
| 0x967e | Draw the table on the slab | Confirmed |
| 0x93cc | Load the table from the file `highscore`, or blank it | Confirmed |
| 0x9320 | Bubble sort, descending by score | Confirmed |
| 0x9288 | Save the 360-byte table to `highscore` | Confirmed |
| 0x92ae | Fill all ten slots with 5000 / Midshipman / "Colin was here!" and save. **No caller anywhere** (dead debug code) | Confirmed (raw scan for `jsr`/`bsr`/stub/data pointers) |
| 0x6086 (stub `-$7e78`) | Generic one-line text editor. Also used at 0x8ef4 (save/load game) and 0xf600 (copy-protection word) | Confirmed |
| 0x8570 → 0x5910 | Print a string at the RastPort pen position in the `newarmyfont` proportional font | Confirmed |
| 0xfe50 | `save_file(name, buffer, length)`: `Open(MODE_NEWFILE)`, `Write`, `Close` | Confirmed (dos.library LVOs) |
| 0x6eee | Wait N frames (`WaitTOF`) or until a button is pressed | Confirmed |
| 0x23dc | Play subsong N of `wofsongs` through `songplay` | Confirmed |
| `-$5cb2` (D234c) | Score, signed 32-bit long | Confirmed |
| `-$5c40` (D23be) | Rank 0..6 | Confirmed |
| `-$5ca2` (D235c) | Planes left (3 at a new game, 0x3578) | Confirmed |
| `-$5c3c` (D23c2) | Game-over flag | Confirmed |
| `-$5c9c` (D2362) | "Show THE END plate" flag | Confirmed |
| `-$5a3c` (D25c2) | Game-over countdown in frames (carrier lost) | Confirmed |
| `-$3224` (D4dda) | Pointer to the high-score table (a 538-byte stack buffer inside 0x9856) | Confirmed |

## 1. Game over and the sequence that follows

### What ends a game

| Trigger | Code | Effect | Confidence |
| --- | --- | --- | --- |
| Last plane lost | 0xaf7c runs every frame while the player's plane is wrecked (callers 0xc7be, 0xc87a, which set the crash shapes `hcr5`/`hcrf`). If planes left is 1 or 0, it sets `-$5c9c`. After 150 frames, or after more than 30 frames once input bits `-$42bc & 0x30` are set, it calls 0x35ce. 0x35ce decrements the planes. If planes ≤ 0, or the carrier's +0xc field (`-$5b26` record) ≤ 0, it sets `-$5c9c` and the game-over flag. | Control flow confirmed. The `0x30` bits being the fire button is inferred |
| Own carrier sunk | 0x1d7e (sinking-ship logic): planes = 0 and countdown `-$5a3c` = 100. While `-$5c9c` is set, 0x1110 decrements the countdown each frame and raises game over at 0 | Confirmed control flow. That this is the player's carrier is inferred (ship with no score value) |
| Ctrl-R (restart) | Key handler 0xcd2c: fade out, set `-$5a3e` and game over | Confirmed |
| `q` in a menu state (`-$50e6` = 5) | Sets quit `-$407e` and game over; the program exits at 0x020e without high scores | Confirmed |
| Demo record buffer full / playback end | 0x17c8, 0x183a | Confirmed |

**The "THE END" plate.** While `-$5c9c` is set, 0x10c2 draws the world-shape
record `gmov` each frame. Its anchor is placed at (160, 81), and with its
origin (99, 11) the 192×22 plate covers x 61..252, y 70..91. The plate is a
winged silver bar with the words **THE END**
(`reference_assets/unpacked_shapes/world/048_gmov.bin`). The game has no
"GAME OVER" text string. The draw is confirmed; the reading of the text comes
from rendering the record.

**There is no victory end.** 0x5694 (mission complete) increments the
mission. Past the rank's mission count (table `-$5ab6`: 3,3,2,2,1,1,3), it
resets the mission to 1, increments the rank (capped at 6), grants a bonus
plane and queues the ticker text "Congratulations! You have completed your
mission!! You are instructed to return to carrier for victory ceremony!!".
The game then continues; that path never sets the game-over flag. This is
confirmed for 0x5694. That nothing else ends a game at Captain is inferred,
because no other route to 0x9856 exists.

### Main-loop sequence after the flag (0x01c6)

```
0x01c6  call 0x1f4e; call 0x6bbc          ; not identified (shutdown of the playfield)
        fade_to_black(1)                  ; 0x73e6
        demo_playback = (demo_mode == 1)  ; -$4072
        finish_demo()                     ; 0x852a: if recording, saves "wofdemo"
        if quit_flag: exit program        ; 0x020e
        if !demo_playback:
            call 0x1234
            highscore_sequence()          ; 0x9856
        goto 0x0066                       ; new game: score 0, 3 planes, rank selection (0x8262)
```

So the high-score screens are reached after **every** real game, including
Ctrl-R restarts. They are skipped only for demo playback and for quit.
Afterwards the game goes straight back to rank selection, not to the title.
All of this is confirmed control flow.

### High-score sequence (0x9856)

```
table = local[538]                        ; -$3224
play_song("wofsongs", 0)                  ; subsong 0: used only here
enter_highscore()                         ; 0x9472: name screen, only if the score qualifies
build split display                       ; 0x6d7a (see section 5)
select lower viewport; load "shapes/hiscoreslab" (palette kept aside)
draw_table()                              ; 0x967e
select upper viewport; load "shapes/hiscore.iff" (palette kept aside)
fade both viewports in to their palettes  ; 0x71f2(banner_pal, slab_pal, 1)
wait(1800)                                ; 0x6eee: 1800 frames or a button
fade both to black                        ; 0x73e6(1)
```

Confirmed. The table screen is shown even when the score does not qualify.

## 2. The table in memory and on disk

**Ten entries of 36 (0x24) bytes = 360 (0x168) bytes**, big-endian:

| Offset | Size | Field | Confidence |
| --- | --- | --- | --- |
| +0x00 | long | Score, signed (`cmp.l`/`bge`) | Confirmed |
| +0x04 | word | Rank 0..6, index into the rank-name table `-$56ee` | Confirmed |
| +0x06 | 30 bytes | Name, NUL-terminated. Entry writes at most 16 characters + NUL (`strncpy` of 17 bytes). The other 13 bytes keep whatever was there | Confirmed |

The table only exists while 0x9856 runs, in a stack buffer. It is
**loaded from disk at every game over** (0x93cc at the top of 0x9472) and
saved again after every new entry.

**Default contents.** No table is built into the executable. If
`Open("highscore", MODE_OLDFILE)` fails, 0x93cc blanks every entry:
score 0, rank 0 (Midshipman), name `"            "` (12 spaces). The
drawer skips entries whose score is 0, so **the default table is empty**:
the slab shows no rows. The extracted disk (`[a]` release, 73 files in
`reference_assets/MANIFEST.json`) has no `highscore` file, and none of its
strings look like a saved table. Whether an original retail disk shipped
with one is unknown.

The only "defaults" in the code are in the dead routine 0x92ae: all ten slots
set to **5000, Midshipman, "Colin was here!"** (Colin Fox did the Amiga
version), then saved. Nothing calls it.

## 3. Qualifying and insertion (0x9472)

```
load table; sort descending
if score <= table[9].score: return        ; strict ">" against the 10th
... name entry (section 4) ...
table[9].score = score
strncpy(table[9].name, name, 17)
table[9].rank  = rank                     ; current -$5c40, recorded automatically
fade name screen to black                 ; 0x73b0(1)
sort; save
```

Sort (0x9320): a bubble sort that repeats passes until no swap happens. It
swaps neighbours only when `entry[i].score < entry[i+1].score`.

- A score **equal** to the 10th does **not** qualify. With an empty table,
  any score above 0 qualifies, and a score of 0 never does.
- The sort is stable, and the new entry starts at the bottom. On a **tie**,
  the new entry goes **below** the older equal scores.
- The evicted 10th entry is overwritten, not shifted out.

All confirmed.

## 4. Name entry

**Screen** (0x9472, confirmed except where marked):

- Display rebuilt by 0x69a4 as a single 320×200, 4-plane (16-colour)
  low-resolution viewport. The struct fields (width 0x140, height 0xc8,
  depth 4) are confirmed; whether the bitmap is cleared first was not
  determined.
- Palette: the 16 words at DATA 0x2a5c, faded in from black (0x7084):
  `000 ECA E00 A00 D80 FE0 8F0 080 0B6 0DD 0AF 07C 00F 70F C0E C08`
  (Amiga 12-bit RGB).
- Prompt, pen 8 (`0B6`), JAM1, drawn by graphics `Text()`, so y is the
  baseline:
  - `Move(52, 83)`, "Your name is to be entered"
  - `Move(91, 92)`, "in the hall of fame."
- Box, pen 2 (`E00` red): outline rectangle (80,100)–(225,113), drawn with
  `Move`/`Draw`.
- Input field: editor called as `edit(buf, maxlen 16, x 82, y 102, 10000)`.
  The fifth argument is never read by the editor.

**Editor** (0x6086), with x, y and the RastPort set by the caller:

- Text: pen 6 (`8F0`) on pen 0, JAM2, `Move(x, y + TxBaseline)` and
  `Text()`. The tail is blanked by writing spaces, so a shortened string
  leaves no ghosts.
- **Character cells are 8 px wide.** Positions are `x + 8 × index`. This
  points to the 8×8 system font (topaz 8) on that RastPort; the font itself
  was not traced (inferred).
- Cursor: an 8×8 filled block at `(x + 8 × cursor, y)`, drawn with
  `RectFill` in COMPLEMENT mode (XOR). It is drawn and erased around each
  redraw, so it does not blink.
- The buffer starts empty (17 bytes cleared). The cursor starts at 0.
- **Maximum length 16 characters.** At 16, further characters are ignored.

**Keys** (raw Amiga key codes, confirmed):

| Input | Action |
| --- | --- |
| Return (0x44), keypad Enter (0x43) | Finish |
| Cursor up (0x4c) / down (0x4d) | Finish (returns −1 / +1; the high-score caller ignores the value) |
| Cursor left (0x4f) / right (0x4e) | Move the cursor one place. With Shift (qualifier bits 0..1), jump to the start / end |
| Backspace (0x41) | Delete the character left of the cursor |
| Del (0x46) | Delete the character under the cursor |
| Right-Amiga + X | Clear the whole line |
| Any other key | Converted to one character through the system keymap (0x10700, an InputEvent of class RAWKEY). If the result is non-zero and fewer than 16 are typed, it is **inserted** at the cursor (the rest shift right) |
| Joystick or mouse fire (CIA-A PRA bit 7 / bit 6) | Finish |
| Joystick up / down (JOY1DAT decoded to direction 1 / 5) | Finish, after a short wait for release (0x8228, up to 9 frames) |

- **Allowed characters: anything the keymap produces.** There is no
  filtering, so lower case, digits, punctuation and space are all accepted.
  Control characters such as Tab or Esc are probably accepted too
  (inferred from the lack of a filter).
- There is **no joystick letter picking**: names are typed on the keyboard.
- An **empty name** is accepted.
- Finishing with fire does not wait for the button to be released, and
  0x6eee then checks the same button. Holding fire may therefore skip the
  table screen almost at once (inferred from the code; not observed).

## 5. The table screen

**Display** (0x6d7a, confirmed fields; the meaning of the custom display
struct is inferred):

| Viewport | Size | Depth | Content |
| --- | --- | --- | --- |
| Upper, lines 0..74 | 320×75 low-res | 5 planes (32 colours) | `shapes/hiscore.iff`: ILBM 320×75×5, the "WINGS OF FURY / ACES" winged badge with HONOR and VALOR medals |
| Lower, from line 76 (`+0xa6` = 0x4c) | 640×145 high-res | 4 planes (16 colours) | `shapes/hiscoreslab`: ILBM 640×200×4; the marble slab art occupies rows 0..130, the rest is black |

Each image is loaded at the top-left of its own viewport. Its palette goes
into a buffer, and the viewport stays black until the joint fade-in.

Slab palette (CMAP): `000 06C 001 223 334 445 556 667 778 889 99A AAB BBC CCD
DDE EEF`.

**Table text** (0x967e), drawn into the slab's RastPort in high-res pixels:

```
for pass in 0..2:                         ; offsets (-1,+1,0), pens (0,0,15)
    off = {-1, +1, 0}[pass]; pen = {0, 0, 15}[pass]   ; DATA 0x2a56 / 0x2a50
    SetAPen(pen); SetDrMd(JAM1)
    for i in 0..9:
        if table[i].score == 0: continue
        x = 13 + off; y = 6 + 12*i + off
        at (x,       y): sprintf("%d", i + 1)
        at (x + 40,  y): sprintf("%-6ld", score)
        at (x + 150, y): sprintf("%-12s", rank_name[rank])   ; full names
        at (x + 300, y): name                                 ; as stored
```

- Columns (top-left of the glyph cell, high-res px): **position at x 13,
  score at x 53, rank at x 163, name at x 313**. Row i is at **y 6 + 12i**
  (6, 18, … 114), so the last row ends at y 126, inside the slab's 131 rows.
  Confirmed.
- Look: each string is drawn in black (pen 0, `000`) shifted by (−1,−1) and
  by (+1,+1), then in pen 15 (`EEF`, near white) on top. The result is light
  lettering with a dark edge on the marble, like an engraving. Confirmed.
- Font: the game's **`newarmyfont`**, 12 px high and proportional. The
  printer 0x5910 uses the font loaded at 0x2794 (`-$4094`). It advances
  each glyph's width + 1 px, a space is 10 + 1 px, and the cell is
  `BltTemplate`d at the pen position (top-left, not baseline). Confirmed.
- Formatting: the position has no padding and no dot ("1".."10"). The score
  is plain decimal with no separators or leading zeros, left-aligned. The
  rank is the **full** name (Midshipman, Ensign, Lt. Jr. Gr., Lieutenant,
  Lt.Commd, Commander, Captain). Confirmed.
- No headings, no highlight of the new entry, no "press fire" text.
  Confirmed (nothing else is drawn).

**Duration.** The screen holds for **1800 frames** (36 s PAL / 30 s NTSC),
or until a fire button (joystick port 1 or the left mouse button) is
pressed. Keys do not dismiss it. Then both viewports fade to black. The wait
is confirmed; which device each CIA bit belongs to is inferred from Amiga
hardware.

**Music.** Subsong 0 of `wofsongs` starts when the sequence begins and plays
under the name entry and the table. It is the only place that subsong is
selected (title: 2 then 1; rank selection: 4). Confirmed.

**Not in the attract mode.** The drawer 0x967e is called only from 0x9856,
and 0x9856 only from the game-over branch. Demo playback skips it. The table
is therefore never shown in the title/demo loop. Confirmed.

## 6. Disk file

| Item | Value | Confidence |
| --- | --- | --- |
| File | `highscore`, relative to the current directory (the game drawer) | Confirmed |
| Format | Raw dump of the 360-byte table above, big-endian. No header, checksum or version | Confirmed |
| Load | 0x93cc: `Open(MODE_OLDFILE 1005)`, `Read(360)`, `Close`. The byte count read is not checked | Confirmed |
| Save | 0x9288 → 0xfe50: `Open(MODE_NEWFILE 1006)`, `Write(360)`, `Close`. On failure it returns `IoErr()`, which is ignored | Confirmed |
| When saved | After each qualifying entry | Confirmed |
| Reset | **Ctrl-C** during play calls dos `DeleteFile("highscore")` (LVO −0x48 on the DOS base `-$40e0`, the same base that `Open`/`Read`/`Close` use) | Confirmed |

## How the MSX port can use this

- Keep ten records of {score: u32, rank: u8, name: 16 chars + NUL} in RAM.
  Start empty (all scores 0, nothing drawn) to match the original's no-file
  case. The 5000 / "Colin was here!" set is optional flavour; the original
  never shows it.
- Show the end plate when the last plane is lost, then the sequence:
  optional name entry → table → back to rank selection. Run it after
  Ctrl-R as well, but not after demo playback.
- Qualify with a strict "greater than the 10th". Insert below equal scores.
- The original types names on the keyboard. The MSX has a keyboard, so the
  same editor (16 chars, insert mode, Return/fire to finish, Backspace/Del,
  cursor keys) maps directly. A joystick-only letter picker would be a port
  addition, not a reproduction.
- The table is laid out in 640 px high-res. Columns at 13/53/163/313 scale
  to about 6/26/81/156 at 320 px, or 5/21/65/125 on a 256-px SCREEN 5
  (×0.4). The 12-px font is the same `newarmyfont` that
  `tools/convert_font.py` already converts for the ticker.

The reproduction helpers used for this note are not committed. Repeat the
analysis by parsing the hunks (including HUNK_RELOC32, to resolve string and
stub pointers) and disassembling with Capstone (`CS_ARCH_M68K`).
