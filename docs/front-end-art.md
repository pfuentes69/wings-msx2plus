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
| Briefing | `rank.iff`'s frame, centred on black; the values in a light grey serif font | `world.shp` rank (256 × 95), newarmyfont | done: full screen on black |
| Rank selection | `selectrank` (320 × 200), a blue band behind the chosen rank | `shapes/selectrank` | not yet; "Return from R&R" is dropped (no saved games) |

`tools/convert_screens.py` decodes the shapes (`decode_shapes.py`, the
`wingspalette` colours), maps their colours to the port's palette, and
writes `src/generated/screens_art.c` (packed 4 bits a pixel, 0
transparent) with previews in `assets_msx/screens/`. The art and the code
that draws it live together: the weapon panel in segment 49
(`msx/screens.c`, `generated/screens_art.c`); "THE END" and the briefing in
segment 50 (`msx/screen_end.c`, `generated/screen_end_art.c`), the
briefing's frame in data banks 51..52.

## The end

The plate's greys map onto the play palette's (6..11; black to the dark
navy, 1, since 0 is the sky and transparent). When the game ends
(`GAME_OVER`), `Screens_DrawEnd` streams it into the shown page's spare
rows (212.., the aircraft backups, unused once the game is over) and
copies it over the view without its transparent pixels (LMMM, TIMP),
centred in the view: the page is a ring scrolled by the camera, so the copy
splits at the ring's seam when it has to. The view stays as it was: the
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
- **Drawing** (`Screens_Briefing`): the frame's rows stream from banks
  51..52 (packed, 128 bytes a row, `Scenery_Read`), centred at row 58; the
  values' glyphs (1 bit a pixel, in segment 50) are set into each row before
  it is written, so the frame stays whole.
- The verification (`verify_p0`) expects colour 0 black and the dashboard's
  rows black on the briefing.
