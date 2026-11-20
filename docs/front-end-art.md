# The front end's artwork

Started 2026-11-19. The screens around the game take the original's
artwork, from the disk and checked against captures of the running
original (the user's, 2026-11-19). Order agreed: "THE END", weapon
selection, the briefing, rank selection. The high-score table is set aside
([mission-flow.md](mission-flow.md)); music comes after the artwork.

| Screen | Original | Source on the disk | In the port |
| --- | --- | --- | --- |
| The end | a winged plate over the play view, which keeps moving | `world.shp` gmov, 192 × 22 | done: over the view, frozen |
| Weapon selection | a panel over the carrier view, top right; a blue band behind the chosen weapon (Rockets, Bombs, Torpedo; Bombs first) | `world.shp` selt (96 × 72), rock, bomb, torp (96 × 11..12) | done: over the carrier view, frozen |
| Briefing | `rank.iff`'s frame, centred on black; the values in a light grey serif font | `world.shp` rank (256 × 95), newarmyfont | the port's own compact panel (160 × 85, small letters), 2026-11-19 |
| Rank selection | `selectrank` (320 × 200), a blue band behind the chosen rank | `shapes/selectrank`, `selectrank.shp` rnk0..rnk6 | done: full screen, 256 wide; "Return from R&R" dropped (no saved games) |
| The intro | story scroll, Brøderbund, title, credits ([research](research/amiga-intro.md)) | `shapes/wingstitle`, `creditscreen`, the executable's story | done 2026-11-20: title, credits, story pages ([intro.md](intro.md)) |

`tools/convert_screens.py` decodes the shapes (`decode_shapes.py`, the
`wingspalette` colours), maps their colours to the port's palette, and
writes `src/generated/screens_art.c` (packed 4 bits a pixel, 0
transparent) with previews in `assets_msx/screens/`. The art and the code
that draws it live together: the weapon panel in segment 49
(`msx/screens.c`, `generated/screens_art.c`); "THE END", the briefing and
the palettes in segment 50 (`msx/screen_end.c`, `generated/screen_end_art.c`),
rank selection in banks 53..57.

## Colours

Each screen has its colours (`Screens_Palette`: the play's, the play's with
the weapon panel's lent, the briefing's, rank selection's), and they change
when the page with that screen is published, never before: the play area's
palette (which the line interrupt reloads each frame) and the VDP's at once,
the dashboard's, and the column mask. Switching them while a screen was
being drawn on the hidden page showed the old screen in the new colours
for the frames the drawing took (play-tested 2026-11-19: rank selection and
the briefing "going off in colour", the weapon panel greenish as it went).
The one screen drawn on the page shown, the weapon panel in the hold after
a landing, takes its colours just before it is drawn.

## The end

The plate's greys map onto the play palette's (6..11; black to the dark
navy, 1, since 0 is the sky and transparent). When the game ends
(`GAME_OVER`), `Screens_DrawEnd` streams it into the shown page's spare
rows (212.., the aircraft backups, unused once the game is over) and
copies it over the view without its transparent pixels (LMMM, TIMP),
centred in the view: the page is a ring scrolled by the camera, so the copy
splits at the ring's seam when it has to. Those rows also hold the wave strip's
frames (x 48 and 144, `Dashboard_LoadWaves`): the rank screen, which always
follows, loads them again (the user, 2026-11-19: the next game's sea showed
pieces of the plate). The view stays as it was: the
main loop republishes the same scroll, and the dashboard is redrawn with
the final state. After 150 frames, or a button after 30, the game goes back
to rank selection.

The original keeps the scene moving behind the plate (smoke rising, planes
flying); freezing it was agreed as good enough.

## Weapon selection

The panel (`selt`) and the three highlighted lines (`rock`, `bomb`, `torp`:
yellow letters on the blue band) are drawn over the carrier view, top
right (the original's right margin, 32 of 320 px, as 24 of 256; 20 rows
down), as in the original at game start and in the hold after a landing.

- **Colours.** Yellow, orange, red and the band's blue are not in the play
  palette. While the panel shows, colours 12..15 of the play palette (the
  island's greens, not in view at the carrier, and two browns used by ~100
  deck pixels) are lent to it (`Screens_WeaponColours`, through the play
  area's palette the line interrupt loads each frame), and given back when
  it goes. The panel's 14 colours: greys onto the play greys; yellow 10 to
  12; yellow-orange 11 and orange 2 to 14; red 3 and dark red 4 to 13; the
  band 5 to 15; the sky's blue 1 to the sky.
- **Drawing.** The panel is opaque: its rows are written into the shown page
  (VDP_WriteVRAM), at an even ring column (whole bytes) following the view's
  camera, split at the ring's seam. A cursor move rewrites the old line from
  the panel, then the new one highlighted (neighbouring lines share a row).
  The view behind is frozen; leaving rebuilds both pages.
- **At game start** the briefing leads into the loadout: a new plane is set
  up in the hold (the carrier at its lowest), the carrier view is rendered,
  then the panel. In the hold after a landing the view is on screen already.
- **Order.** The original lists Rockets, Bombs, Torpedo, Bombs chosen first.
  The cursor stays the weapon (0 bombs, 1 rockets, 2 torpedo:
  `GAME_WEAPON_LINE` gives its line) and moves in the panel's order, wrapping
  round.

## The briefing

**The port's own layout** (2026-11-19, the user: the original's frame was
too big for its contents): a 160 × 85 panel centred on black, in the
original's arrangement and colours: a grey bevelled frame (fills), three
black compartments (rank and mission; "MISSION OBJECTIVES:" in red;
islands and ships), blue labels and light grey values, in the menu's 5 × 7
letters (`g_SmallFont`, taken from `msx/menu.c` by the generator). The red
and blue are lifted a little for letters this small. Banks 51..52 (the
original's frame) are free again. The original's, for the record:

The original (0x8590) shows `rank.iff`: a 640-pixel high-resolution picture,
its frame at (198, 54), and prints into it in `newarmyfont`, the font the
frame's own labels are drawn in: the rank's short name at (296, 61), the
mission at (340, 73), the islands at (340, 119), the ships at (340, 131),
each on its label's rows. `world.shp` holds the same frame as a 256 × 95
low-resolution shape (`rank`), pixel for pixel (matched on all 24,320
pixels), so on the MSX it fills the screen's width with the font at its
own size.

- **Full screen on black** (the captures): the page is cleared with colour
  0, set to black for it (the line interrupt never rewrites colour 0, so
  the dashboard's rows are black too), and the play area's colours become
  the briefing's (`Screens_BriefingColours`): rank.iff's black, red, blue
  and four greys, and the values' light grey. Leaving gives back the play
  palette and the sky; a page whose dashboard rows were drawn over gets them
  back (`Dashboard_Restore`) before it is drawn on again.
- **Drawing** (first version, replaced): the frame's rows streamed from
  banks 51..52, centred at row 58, the values' newarmyfont glyphs set into
  each row before it was written.
- The verification (`verify_p0`) expects colour 0 black and the dashboard's
  rows black on the briefing.

## Rank selection

The original's picture (`shapes/selectrank`, 320 × 200, 32 colours) fills
the screen: a riveted frame, the winged logo, "SELECT RANK" and the ranks;
the chosen rank sits on a blue band (`selectrank.shp` rnk0..rnk7, 192 × 9
at x 64, 10 rows apart: the band with the letters as holes, the picture's
gold showing through).

- **256 wide.** The picture's content (logo, title, ranks) spans columns
  70..247, so the middle rows keep the frame's 36-column sides and the
  inner columns 68..251 (the band loses 4 plain columns at each end); the
  top and bottom bars, which carry rivets every 21 columns, lose one 64-px
  block from their flat middle instead (one rivet gap 1 px shorter). It is
  drawn at row 6 of the 212.
- **Colours.** Rounded to the MSX's 8 levels a channel the picture has 19
  colours; the three rarest (6, 11 and 28 pixels) go to their nearest, so 16.
  The palette covers the whole screen (play and dashboard areas, colour 0
  black) and the column mask is off, so all 256 columns show; leaving gives
  back the play's and the dashboard's palettes and the mask.
- **The band.** Each line highlighted (the strip over the picture's line) is
  stored ready (bank 57); a cursor move rewrites the old line from the
  picture and the new one from the strips, on the page shown.
- **"Return from R&R"** (rnk7) is left out: neither the manual nor the port
  has saved games. The cursor has seven ranks, wrapping round.
- RAM is not cleared at boot: the front-end screens' flags are zeroed in
  `main` (a garbage "rank screen up" flag left the old menu at boot).
