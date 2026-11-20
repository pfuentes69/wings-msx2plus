# The intro

Updated 2026-11-20. This is the port's own intro, shown at boot before
rank selection. It is built from the original's pictures and text. The
original's sequence and music are researched in
[research/amiga-intro.md](research/amiga-intro.md).

## Screens

| # | Screen | Source | Stays (PAL frames) |
| --- | --- | --- | --- |
| 0 | Title | `shapes/wingstitle` (320 × 200, 32 colours), box-scaled to 256 × 200, in its own 16 colours, at row 6 | 400 (8 s): the original's 300 plus the next picture's load |
| 1 | Credits | "ADAPTED FROM THE AMIGA VERSION"; the original's roles and names cut from `creditscreen` (its serif lettering and shades), each name under its role; the USI logo; "PORTED BY PFUENTES69 (& CLAUDE)" | 600 (12 s), as the original's credits |
| 2..4 | The story, "A Time of Fury" | The executable's text: the heading in `newarmyfont` (gold), the paragraphs rewrapped to 40 columns in the menu's 5 × 7 font (capitals). Three pages instead of the original's scroll | 1250 each (25 s): 75 s in all, as the original's scroll |

- **Advancing.** A button (fire, space or Return) goes to the next screen.
  Escape goes straight to rank selection. Each screen moves on by itself
  after its time. After the last screen comes rank selection.
- **Once per start.** As in the original, the intro is not shown again
  after a game over: the game goes back to rank selection.
- **Colours.** The title has its own palette. The credits and the story
  share one: black, the text's light grey, the original's four oranges,
  the heading's golds and the logo's blues. Each palette covers the whole
  screen and is set when its page is published (`SCREENS_TITLE`,
  `SCREENS_INTRO`).

## Boot

The title is the first thing on screen (the user, 2026-11-20: the carrier
showed first). Right after the screen mode is set, `Screens_BootTitle`
clears page 0's rows below the screen, draws the title there, sets its
palette, zeroes the scroll and turns the display on. The scroll matters:
the V-blank handler writes R27, R26 and R23 each field from
`g_ScrollFine`, `g_ScrollCoarse` and `g_VerticalOffset`, and RAM is not
cleared at boot. 0.1.1 left the first two unset until the main loop's
first publish, so the title showed displaced until loading ended (the
user, 2026-11-20: R26 = 63, R27 = 7 on the Panasonic). Boot now zeroes
them, and `verify_p0` checks R23, R26 and R27 at the first title. That is about 0.7 s after the game
starts, against 3.7 s before. Everything else loads behind it, out of
sight:

- the rest of VRAM is cleared;
- the dashboard is drawn on page 1 only (page 0's comes back with
  `Dashboard_Restore` before play);
- the atlas, the ship, the elevator and the terrain are loaded;
- the mission is set up.

That takes about 4.5 s on the Panasonic. With the intro, the carrier view
is not drawn at boot: rank selection and the briefing leave both pages to
be rebuilt before play. The title's 8 s count from the end of loading.
`verify_p0` checks that the first page held on screen for a whole frame
is the title.

## Differences from the original

| Original | Port | Why |
| --- | --- | --- |
| Story first, then Brøderbund, title, credits | Title, credits, story | The user's order. The original's is a constant swap away (`GAME_INTRO_*`). |
| Brøderbund presents | Left out | Not asked for. The original's picture (`shapes/broderbund`) could be added the same way. |
| The story scrolls up (1 line every 4 frames), justified to 615 px, `newarmyfont`, fading in and out at the edges | Three still pages in the menu's font, capitals | The user's choice: the text, not the scroll. |
| A press on a picture skips all of them | A press shows the next screen; Escape skips | So that each screen can be seen. |
| Fades through black between screens (16 steps) | A cut | Not done yet. |
| "Programming:" | "Programming:" (the original's lettering) | The user wrote "Development"; the picture says "Programming". |

## Music (for later)

To be done with the music. From the research:

| Subsong (`wofsongs`) | Original use | Port's plan |
| --- | --- | --- |
| 1 | Brøderbund, title, credits | The title and the credits |
| 2 | The story (about 54 s a loop) | The story's pages |
| 4 | Rank selection | Rank selection |
| 0 | Name entry, high scores | (The high scores are set aside) |
| 3 | Unused, same as 1 | — |

- Every song loops.
- A change of song fades the old one out first, for about 2 s, and the
  original waits for that.
- The music stops when rank selection ends. The briefing, weapon
  selection and play have no music.
- The replayer's tempo comes from a timer, so it is the same on PAL and
  NTSC.

## Code and data

- `tools/convert_screens.py` (`intro_title`, `intro_pages`):
  - the title in banks 59..62;
  - the credits' cut-outs and the heading in bank 63;
  - the USI logo and the story's lines (42-byte records) in bank 24;
  - the palettes and the pieces' and pages' tables in
    `generated/screen_end_art.c`;
  - previews in `assets_msx/screens/` (`title.png`, `intro-*.png`).
- The menu font gains `, ' ! - ( ) & ?` (`SMALL_FONT_EXTRA`); lower case
  prints as capitals.
- `src/msx/screen_end.c` `Screens_Intro` (segment 50) draws a screen on
  the hidden page: rows streamed from ROM, the text in the small font.
- `src/core/game.c`: the phase `GAME_INTRO` (the cursor is the screen),
  `Game_Intro` at boot, the screens' times in `Game_Wait`.
- `src/world_flight.c` draws each screen once, on the hidden page.

## Verification

- `verify_p0` captures each intro screen and compares it byte for byte
  with the converter's composition, palette included.
- The other scenarios press Return through the intro
  (`tools/smoke_lib.tcl`: `intro_skip`; a scenario may define
  `intro_screen` to capture each screen).
