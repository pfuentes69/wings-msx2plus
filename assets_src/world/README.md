# Representative original world shapes

Nine indexed PNGs decoded from the preserved `world.shp` by
`tools/convert_terrain.py`: shoreline pairs, three palms, intact/ruined hut
candidates, a dugout and one wave candidate. The contact sheet uses the
expanded original 32-color palette. Raw inputs are unchanged.

The manifest records archive/palette/record SHA-256, offsets and observed
headers. Header drawing origins are applied to the authored scene. Nonzero
base-color OR and transparent zero retain the decoder's documented hypotheses;
the two base-14 shorelines are exact pixel reflections. Visual recognition
does not establish original mission placement, collision masks or wave timing.

Regenerate with `python tools/convert_terrain.py`; use `--check` to compare
all generated binary, JSON, C and PNG outputs. See `docs/tile-terrain.md`.
Original copyrights remain with their respective owners; these are derived
reference materials for this private port project.
