# The front end's artwork

Started 2026-11-19. The screens around the game take the original's
artwork, from the disk and checked against captures of the running
original (the user's, 2026-11-19). Order agreed: "THE END", weapon
selection, the briefing, rank selection. The high-score table is set aside
([mission-flow.md](mission-flow.md)); music comes after the artwork.

| Screen | Original | Source on the disk | In the port |
| --- | --- | --- | --- |
| The end | a winged plate over the play view, which keeps moving | `world.shp` gmov, 192 × 22 | done: over the view, frozen |
| Weapon selection | a panel over the carrier view, top right; a blue band behind the chosen weapon (Rockets, Bombs, Torpedo; Bombs first) | `world.shp` selt (96 × 72), rock, bomb, torp (96 × 11..12) | not yet |
| Briefing | `rank.iff`'s frame, centred on black; the values in a light grey serif font | `world.shp` rank (256 × 95) | not yet |
| Rank selection | `selectrank` (320 × 200), a blue band behind the chosen rank | `shapes/selectrank` | not yet; "Return from R&R" is dropped (no saved games) |

`tools/convert_screens.py` decodes the shapes (`decode_shapes.py`, the
`wingspalette` colours), maps their colours to the port's palette, and
writes `src/generated/screens_art.c` (packed 4 bits a pixel, 0
transparent) with previews in `assets_msx/screens/`. The art and the code
that draws it live together in segment 49 (`msx/screens.c`).

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
