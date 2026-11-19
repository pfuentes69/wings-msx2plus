# The cockpit window

Started 2026-11-19, after play-testing: the pilot's window in the middle of
the dashboard showed fixed pictures (sea, island, carrier by altitude),
where the original shows what is ahead: the island's targets coming
closer, the carrier growing on the approach, the deck sliding past on
landing. How the original draws it is in
[research/amiga-cockpit-view.md](research/amiga-cockpit-view.md); this is
the port's version.

![The window from the model, map a](cockpit/views.png)

## How the original does it

Not a 3-D projection. The ground ahead is cut into 11 depth bands (13..190
map columns ahead, a column being 8 px), drawn far to near, each one row
lower than the last. Each band draws a pre-drawn shape sized for that band
(`dash.shp`), at the window's centre column: a 1-px tan line where the band
holds island ground, a jungle strip where it holds trees, and one object
(hut or wrecked hut, dugout, AA gun, carrier or its tower). The horizon
sits at row `altitude / 16` (climbing lowers it). Over the carrier, the
bands leave it out and a deck view is drawn instead: the deck, the carrier
and its tower, a row lower for every 6 columns of deck behind the plane,
so the deck is at its fullest at the stern (touchdown) and slides out of
the window as the plane rolls on. The gunsight goes last, its row following
the altitude below 81. Above altitude 186 (the distant view) the window is
plain sky.

## The port

- **Art** (`tools/convert_cockpit.py`): the shapes used, decoded with
  their plane constants, scaled 3/8 across (the original's 122 hi-res
  columns to the port's 46) with rows kept, in the dashboard's colours.
  They fill 7 of the 24 pilot-window atlas slots in VRAM (loaded at boot
  from bank 52, `Cockpit_Load`); slot 0 is the compose buffer. Every shape
  is drawn about the centre column, so its columns are clipped to the window
  once, in the converter. The frame sets are the ones the original
  evidently meant: its arithmetic is off by one or two for the jungle, for
  the carrier facing left and for the tower (the research's anomalies).
- **The map's features** (`--map`, `src/generated/map_<map>/cockpit_map.h`):
  spans in columns, from the original's map words: land, jungle (runs
  merged across gaps under 8 columns: no band is narrower, so a band
  touches a merged run exactly when it holds a jungle column), and objects
  sorted by column (huts in the island records' order, their wrecked state
  from `g_Island`; dugouts; AA guns; the carrier and its tower). The
  original's scan lets any other non-empty map word in a band hide its
  object; the port does not: each band shows its farthest object.
- **Scene** (`msx/cockpit.c`, segment 51): from the plane's column,
  altitude, facing, the torpedo plane's arrow and the huts, 19 bytes: the
  horizon, the deck step, the sight's row, the land and jungle bands, each
  band's shape. Two 191-byte tables give the bands a span of distances
  falls in (`Bands`, in Z80); only objects within reach are looked at (a
  window over the sorted list moves with the plane).
- **Composing**: when the scene changes, it is drawn into the buffer (VDP
  fills and transparent copies), then each page copies the buffer (one
  HMMM) the next time it is rendered, the arrow on top. The work (about
  30,000 T-states) is done in the idle time before a VBlank, like the
  terrain prefetch (`Cockpit_Work`); a render costs about 2,700. Without
  idle time (the heaviest frames), renders that have waited two frames do
  it a step at a time: the scene, then the far half of the picture, then
  the near half. A page never copies a half-drawn buffer, and a change
  meanwhile waits for the picture under way, so a run of changes still
  shows.
- **Not yet**: the enemy planes (`zr1*`/`zr2*`, from 48 to 1280 px ahead,
  by their altitude) and the enemy ships (their own archives' views: the
  destroyer, battleship and cruiser). AA guns are drawn intact (no map
  played so far has any).

## Verification

- `tests/test_cockpit_z80.py`: the compiled code on an emulated Z80
  against the converter's model (`scene`, `compose`), its VDP commands
  logged by a stub and replayed: 168 views on map a, wrecked huts, no
  commands for an unchanged scene, the step-by-step fallback.
- `verify_p0`: the snapshots dump `g_Cockpit`; where the page shown holds
  the buffer's picture, the window is compared pixel for pixel with the
  model's (73 of 82 gameplay snapshots on NTSC).
