# Amiga cockpit view: executable findings

Recovered 2026-11-19 by static 68000 disassembly (Capstone) of
`reference_assets/original_files/Wings_of_Fury/wings`, with the conventions
of [amiga-enemy-planes.md](amiga-enemy-planes.md): code addresses are
CODE-hunk offsets, variables A4-relative, "map offset" is a byte offset into
the map words (column × 2; a column is 8 px), and a map word is
`id = (word >> 2) & 0x1ff`, `class = word & 3` (0 sea, 1 ship or carrier,
2 island). Nothing was observed running on an Amiga. Each claim is marked
**confirmed** (read directly from the code or data) or **inferred** (a
reading of what the code implies).

This is the "3-D view": the pilot's window in the middle of the dashboard.

## Summary

- It is **not** a 3-D projection. It is a **depth-band compositor**. Every
  object is drawn on the window's **centre column (x 319)**. The only
  variables are the **row** (from the band and the player's altitude) and
  the **frame** (one pre-drawn size per band). **Confirmed.**
- The ground ahead of the player is cut into **11 depth bands** (13..190
  map columns, about 104..1527 px ahead). They are drawn **far to near**.
  Band n is drawn one row lower than band n − 1. Each band draws at most:
  - one 1-px tan line (island ground in the band),
  - one full-width jungle strip (a tree column in the band),
  - one object (hut, dugout, AA gun, ship, carrier or carrier tower),
  - any enemy plane whose x falls in the band.
  **Confirmed.**
- Before the bands, the window is filled with sky. Sea is filled from the
  horizon row `alt / 16 + 24` down. **Climbing moves the horizon down** (more
  sky). Above altitude 128 there is no sea in the window. **Confirmed**
  arithmetic.
- Over a ship column (any altitude), a **deck view** is added. It is a fixed
  carrier frame plus a perspective deck (`dec0..dec3`) and the tower. It
  slides down 1 px for every 6 columns (48 px) of deck already passed.
  **Confirmed.**
- The gunsight `targ` is drawn last, at the centre. Its row follows the
  altitude. **Confirmed.**
- Every shape is pre-drawn. There is no run-time scaling, rotation or
  projection, and nothing is computed per pixel. All drawing is masked blits
  and rectangle fills, clipped to the window. **Confirmed.**
- The only orientation input is the **facing sign** (`-$5f72`, ±1). The view
  uses no pitch or turn angle. There is no rear view: the view looks along
  whichever way the plane faces, and flips with it. **Confirmed.**

## Where it runs

| Item | Value | Confidence |
| --- | --- | --- |
| Entry | 0x417e (A4 stub `-$7f38`), called unconditionally from the render loop at 0x0300, after the playfield (0x3772, which computes the horizon) and before the dashboard update 0xee16 (gauges, `ltar`/`rtar` arrow, kills) | confirmed |
| Clip | 0x525c sets the clip rectangle: rows 7..31, x 256..399 (right edge 400, rounded to 16) | confirmed |
| Window art | In `iff-dash` (640 × 37 hi-res), the blue interior is **x 259..380, rows 7..31**: 122 × 25 hi-res px, about 61 × 25 in lo-res pixels. The frame is at 256..258 and 381..383 | confirmed (pixels) |
| Centre | Every object is drawn at x = 319, using the shape's origin | confirmed |
| Sequence | 0x417e: 0x4564 (sky and sea fills); then, unless `-$60c8` = 1, 0x4206 (bands and deck view) and 0x41b4 (gunsight) | confirmed |
| Far view | `-$60c8` = 1 is the zoomed-out view, used above altitude 186 ([amiga-enemy-planes.md](amiga-enemy-planes.md)). It shows only the fills, and at that altitude the sea fill starts below the window: **plain sky** | confirmed control flow; altitude link from the other doc |
| Night | `dash.shp` or `nightdash.shp` is loaded by mission (0x6540, file name table `-$56f6[-$5c6e]`). Both have the same 117 names. Some origins and pixels differ | names confirmed; which missions use night is inferred |

## Shapes

The dashboard shape table `-$41ac` is built from the name list at DATA
0x11c8, in list order: `misl bomb torp olof olon targ bnum wnum ltar rtar
3dl0..3dl9 dug0..dug6 hut0..hut6 huta..hutg pil0..pil6 pila..pilg towr dec0..dec3
3dca..3dcp 3dta..3dtp ndl1..ndln gaug zero`. These are indices 0..116, so
`3dl0` = 10, `dug0` = 20, `hut0` = 27, `huta` = 34, `pil0` = 41, `pila` = 48,
`dec0` = 56, `3dca` = 60, `3dta` = 76. **Confirmed.** The loader is 0x6540.
The index order was checked against fixed uses: `targ` +0x14, `ltar` +0x20,
`gaug` +0x1cc, `zero` +0x1d0, `ndl1` +0x170.

All shapes live in `dash.shp` (and `nightdash.shp`), except the ship views
and the enemy planes' table:

| Shapes | What they are | Sizes (w × h, hi-res; trimmed width) | Used frames |
| --- | --- | --- | --- |
| `3dl0` | a 128-px white line | 128 × 1 | **never referenced** |
| `3dl1..3dl9` | full-width jungle strip (green and brown trees over a tan line), growing taller | 122 × 2..7 | `3dl5..3dl9` (see the anomalies below) |
| `hut0..hut6`, `huta..hutg` | intact barracks hut; wrecked hut | 17..32 × 4..8; 17..31 × 3..5 | frames 1..6 of each |
| `dug0..dug6` | dugout (brown strip) | 11..25 × 1..3 | 1..6 |
| `pil0..pil6`, `pila..pilg` | AA gun intact; damaged | 15..29 × 3..7 | 1..6 |
| `3dca..3dch`, `3dci..3dcp` | carrier seen end-on, two views of 8 sizes | 11..69 × 2..9 | see below |
| `3dta..3dth`, `3dti..3dtp` | carrier tower (island) for each view. Its origin puts it off-centre: left for a..h, right for i..p | 2..13 × 2..14 | see below |
| `dec0..dec3` | perspective deck: a white and grey checker trapezoid | 61 × 4..8 | deck view |
| `targ` | gunsight: grey ring, red centre | 19 × 9 | always |
| `zr10..zr4p` (4 sizes × 26) | the Zero seen from the cockpit, 26 attitudes (see [amiga-enemy-planes.md](amiga-enemy-planes.md)); table `-$3ba2`, 3 sets × 56 built by 0xd1ea from the name lists `-$4ee6`/`-$4e76` | `zr1*` ≤ 21 × 7, `zr2*` ≤ 17 × 5 | `zr1*`, `zr2*` only |
| `db1..dba`, `ds1..dsa` (destroyer.shp), `bb*`/`bs*` (battleship.shp), `cl*`/`cr*` (cruiseship.shp) | enemy ship seen from the cockpit, 10 sizes × 2 views (destroyer and battleship end-on, cruiser side-on) | up to 49 × 27 (destroyer), 55 × 29 (battleship), 96 × 18 (cruiser) | 1..8 of each view |
| `hut7`, `carr`, `towr`, `zr4*`, `3dl0..3dl4` | in the archive or the name list but not used by this view | | |

`hut7` and `carr` are in `dash.shp` but not in the name list, so they are
never loaded. `zr4*` are never used because no band reaches the fourth set.
**Confirmed.**

## Per-frame algorithm

Variables:

- `x`: the player's render x, `-$41a2`.
- `alt`: the render altitude, `-$419e` (on the deck: deck height).
- `f`: facing, `-$5f72` (−1 = left, +1 = right).
- `map`: the map words, `-$69d6`.
- `col = x >> 3`.

Tables, indexed by band `b` = 10 (farthest) .. 0 (nearest):

```
EDGE   (-$6960, words)  = 0, 6, 13, 21, 30, 40, 51, 63, 76, 90, 105, 130, 160
d0[b] = EDGE[b+2]   d1[b] = EDGE[b+1]   w[b] = d0 - d1
K6[b]  (-$6946)  = 6,6,5,5,4,4,3,3,2,2,1        // ground objects, frame 1..6
K7[b]  (-$693a)  = 7,7,6,6,5,4,3,2,1,0,0        // ships, carrier, tower, frame 0..7
ZOFF[b](-$696c)  = 0,0,0,28,28,28,56,56,56,84,84 // into the zr table
```

```
draw_cockpit():                                   // 0x417e
    base = alt/16 + 24                            // -$5c18, set in 0x3772 (asr: floor)
    fill(258,7 .. 380,31, colour 2)               // sky (0x4564)
    fill(258,base .. 380,31, colour 1)            // sea
    if far_view: return
    hide = 4                                      // no class is 4: nothing hidden
    if map[col] is class 1 and its ship is the US or the Japanese carrier
        hide = 1                                  // over a carrier: hide all ship columns
    row = base                                    // -$5c1c
    for b = 10 downto 0:
        // enemy planes: distance d1..d0 columns ahead
        for each of the 4 enemy records e with e.active:
            if e.mapoff (+2e) is between col+f*d1 and col+f*d0 (map offsets):
                i = e.frame (+30)                 // already includes the plane's own facing (+28)
                if f > 0: i = (i + 28) mod 56
                draw zr_table[i + ZOFF[b]] at (319, row - (e.alt(+26)/4 + 4))
        // terrain: distance d0..d0+w columns ahead, scanned outward
        obj = ground = -1; land = false
        for c = col + f*d0, w+1 columns, step f:
            if c is outside the map: continue
            cls = map[c] & 3; id = (map[c] >> 2) & 0x1ff
            if cls == hide: id = 0
            if id in 6..8 (tre1..tre3): ground = id
            elif id != 0 and obj not in (0x22, 0xf6): obj = id   // a tower sticks
            if cls == 2: land = true
        if land: fill(258,row .. 380,row, colour 5)              // 1-px tan line
        if ground >= 0: draw shape(ground) at (319, row)
        if obj    >= 0: draw shape(obj)    at (319, row)
        row += 1
    if !ship_flag (-$3902): deck_view(); ship_flag = 0
    draw targ at (319, alt >= 81 ? 24 : (81 - alt)/4 + 13)        // 0x41b4
```

`shape(id)` is 0x45a6. It uses band `b`, and `cls` is the class of the band's
last scanned column. `c_end` is the map offset one step past the band.

| id | Shape | Confidence |
| --- | --- | --- |
| 6..8 (trees) | index 14 + K6[b] → `3dl5..3dl9`, and `dug0` in the 2 nearest bands | confirmed arithmetic |
| 4 (hut) | `hut0` + K6[b] → `hut1..hut6` | confirmed |
| 5 (wrecked hut) | `huta` + K6[b] → `hutb..hutg` | confirmed |
| 3 (dugout) | `dug0` + K6[b] → `dug1..dug6` | confirmed |
| `cls` = 1, id 0x22 (US tower) or 0xf6 (Japanese island) | 0x4d + (f < 0 ? 10 : 0) + K7[b] | confirmed |
| `cls` = 1, any other id | Ship lookup 0x4a52 on `c_end`. Not found → nothing. Ship with base +1c ≠ 0 (destroyer, cruiser, battleship): its own archive, global table `-$40aa`, index +1c + (f < 0 ? 10 : 0) + K7[b], so `db1..db8` / `ds1..ds8` and the like; sets `ship_flag`. Carrier (+1c = 0, US **and Japanese**): 0x3c + (f < 0 ? 10 : 0) + K7[b] (the `3dc*` art); clears `ship_flag` | confirmed |
| 15 (AA gun) | `pil0` + K6[b] → `pil1..pil6` | confirmed |
| 16..30 (damaged AA gun) | `pila` + K6[b] → `pilb..pilg` | confirmed |
| anything else | not drawn: beaches, balloons, airstrips, soldiers, wreckage | confirmed |

Not in the window: soldiers, balloons, bombs, rockets, explosions, parked
planes and the player's own shots. **Confirmed** (there is no code path for
them).

### Bands in practice

| b | Row | Planes (columns ahead) | Terrain (columns) | K6 | K7 | Plane set |
| --- | --- | --- | --- | --- | --- | --- |
| 10 | base | 130..160 | 160..190 | 1 | 0 | `zr2`, other list |
| 9 | base+1 | 105..130 | 130..155 | 2 | 0 | `zr2`, other list |
| 8 | base+2 | 90..105 | 105..120 | 2 | 1 | `zr2` |
| 7 | base+3 | 76..90 | 90..104 | 3 | 2 | `zr2` |
| 6 | base+4 | 63..76 | 76..89 | 3 | 3 | `zr2` |
| 5 | base+5 | 51..63 | 63..75 | 4 | 4 | `zr1`, other list |
| 4 | base+6 | 40..51 | 51..62 | 4 | 5 | `zr1`, other list |
| 3 | base+7 | 30..40 | 40..50 | 5 | 6 | `zr1`, other list |
| 2 | base+8 | 21..30 | 30..39 | 5 | 6 | `zr1` |
| 1 | base+9 | 13..21 | 21..29 | 6 | 7 | `zr1` |
| 0 | base+10 | 6..13 | 13..20 | 6 | 7 | `zr1` |

**Confirmed.** Consequences:

- The terrain scan covers 165 columns per frame. Columns 0..12 (the
  nearest 104 px) and 121..129, 156..159 are never looked at.
- Planes are seen from 48 to 1280 px ahead. Their row comes from their
  **absolute** altitude (`alt/4`) against the band row; the player's
  altitude enters only through `base`.
- Most shapes have their origin on the bottom row, so an object stands on
  its band's row. A nearer object is drawn later, lower and bigger, so it
  covers farther ones. Planes in a band are drawn before that band's
  terrain.

**Inferred** from the composition:

- An island reads as a stack of tan lines, one per band that holds island
  columns. Over it sit jungle strips wherever a band holds trees, with
  huts, dugouts and AA guns in the centre, growing as they approach.
- A carrier is 95 columns of non-zero ids, all class 1. It falls in several
  bands at once, and each band draws its own size of `3dc*`, 1 px lower than
  the one before. The stack forms a deck in perspective, and the tower
  appears in whichever band holds its column.
- The scene changes when an object crosses a band boundary (every 7..31
  columns), when `alt` crosses a multiple of 16, or when the facing flips.

A static simulation of these rules on map a looks like a carrier seen from
astern, growing as it nears, and like approaching island targets. It was not
compared with a running game. It used the carrier `3dc*` art only, without
the ship lookup or the deck view. Images:
`/private/tmp/claude-501/cockpit/sim_out.png` and `sim_island.png`
(scratch, not in the repo).

### Turning and facing away

The scan direction, the plane test and the view set (`a..h` or `i..p`, ship
`b`/`s`, `l`/`r`) all come from `f` alone. A turn flips everything in one
frame, when the facing flips (turn step 14, [amiga-cannon.md](amiga-cannon.md)).
Anything behind the player is never shown. **Confirmed.**

## Deck view (0x4430)

This runs after the bands whenever the player's own column is class 1 (any
ship, at any altitude) and `ship_flag` (`-$3902`) is clear. `ship_flag` is
set when a non-carrier ship is drawn in a band. It is cleared when a carrier
is drawn in a band, and after the deck view. It is never cleared per frame.
**Confirmed.**

```
deck_view():
    n = 0; c = col
    while id(map[c]) != 0: c -= f; n++        // deck columns behind the player
    s = T1[n]                                 // -$692f: n/6 for n < 90, 15 for 90..101
    y = base + s + 9                          // -$68b9[s] = s + 2, then + 7
    clip_top = base + max(0, s - 7)           // -$68c9
    draw dec[T4[s]] at (319, y + 1)           // -$68a9: 0,0,1,1,2,2,3,3,... → dec0..dec3
    draw (f < 0 ? 3dcn : 3dcf) at (319, y)    // still with clip_top
    restore clip
    draw (f < 0 ? 3dtn : 3dtf) at (319, y)
```

On map a the carrier is columns 825..919, every one class 1 with a non-zero
id. So `n` counts the deck behind the player, and `s` goes 0..15 over the
deck. The fixed picture slides down 1 px per 48 px travelled, the deck
trapezoid grows (`dec0` → `dec3`), and its far part is clipped away.
**Confirmed** arithmetic. That it reads as rolling along the deck is
**inferred**.

While over a carrier, the bands hide every class-1 column (`hide` = 1), so
only the deck view shows the carrier. **Confirmed.**

## Landing aid

The manual describes a "flashing white artificial horizon indicator" to line
up with the deck. Nothing in 0x417e flashes. No other code draws inside the
window apart from the torpedo-plane arrow at (320, 10) (0xf21a). The only
white full-width item, `3dl0`, is never referenced. **Confirmed** for this
executable.

The nearest candidate is the gunsight `targ`. It is grey with a red centre,
not white. Its row follows altitude: row 33 at altitude 0, row 13 at 80, and
it jumps to row 24 at 81 and above. **Inferred** to be the indicator; the
manual may describe another version.

## Anomalies

Each is **confirmed** arithmetic. Whether it was intended is **open**.

1. **Trees:** base 14 (`3dl4`) + K6 (1..6) gives `3dl5..3dl9`, then `dug0`
   in the 2 nearest bands. `3dl0..3dl4` are never used.
2. **Carrier facing left:** the view offset is 10, which suits the 10-frame
   ship archives. The carrier sets have 8 frames. Facing left (the landing
   approach) gives `3dck..3dcp`, then `3dta`/`3dtb` in the 4 nearest bands.
   The tower gives `3dtl..3dtp`, then `ndl1..ndl3` (gauge needles).
3. **Tower one frame ahead:** the tower base is 0x4d (`3dtb`), not 0x4c.
   Facing right, the tower gets `3dtb..3dth`, then `3dti` (the other set's
   smallest) in the 2 nearest bands. `3dta` is never used.
4. **Enemy planes:** offsets 28 and 84 land on the other facing's list. This
   is already noted in [amiga-enemy-planes.md](amiga-enemy-planes.md).
5. **Ship lookup:** it uses the column just past the band. A ship whose last
   column ends inside a band is not drawn in that band.
6. The Japanese carrier is drawn with the US carrier's `3dc*`/`3dt*` art. The
   deck view also appears over the Japanese carrier and, with `ship_flag`
   clear, over any ship.

## Cost

Per rendered frame, upper bounds. **Confirmed** from the loops; the counts
are counted, not timed.

- 2 rectangle fills, plus up to 11 one-row fills.
- 165 map words read, 11 × 4 plane range tests.
- At most 11 strips + 11 objects + 4 planes (each plane is in one band)
  + 3 deck-view blits + 1 gunsight: about 30 masked blits, all small (the
  largest is a 122 × 7 strip). Typical frames have a handful.
- No arithmetic beyond shifts, adds and table look-ups.

## Notes for an MSX2+ port (opinion)

The port's window is 46 × 24 (`HUD_PILOT_WIDTH`). The original's is
122 × 25 hi-res.

- **Geometry:** use x' = (x − 259) × 3/8 and y' = y − 7. 122 × 3/8 ≈ 46,
  which matches `PILOT_WIDTH`. Keep rows 1:1 and drop one row. The horizon is
  row' `alt/16 + 17`. Each band is +1 row, so the whole perspective is only
  11 rows deep, which fits 24 rows.
- **Art:** pre-scale every used shape by 3/8 horizontally, offline (the
  converter, like `pilot_frame` in `tools/convert_dashboard.py`), and keep
  them as transparent SCREEN 5 blocks in VRAM. At 4 bpp the used set is
  about 2.7 KB for land, carrier, tower, deck and gunsight, about 0.8 KB for
  the `zr1`/`zr2` planes, and about 7 KB for the three ship sets (the cruiser
  alone is 2.8 KB). Towers shrink to 1..5 px. Ships or the second plane size
  could be dropped first if VRAM is tight.
- **Composition:** per redraw, 2 HMMV fills, up to 11 one-row HMMV lines,
  and up to about 25 LMMM+TIMP copies, all inside about 48 × 24. Compose
  into a hidden 48 × 24 buffer and HMMM it into the dashboard page. This
  fits the existing per-page `s_Pilot` key scheme in `src/msx/dashboard.c`.
- **Z80 work:** replace the 165-column map scan with the port's object lists
  (ships, carrier, island targets, trees as island spans, enemy planes).
  Distance in columns → band via a 191-byte table, then frame via K6/K7.
  That is a few hundred T-states per object. Build a small key from the
  per-band (ground, object) pairs, the plane bands and frames, `base`, the
  facing and the deck step, and redraw only when it changes. The scene
  changes at most every few frames.
- **Anomalies:** decide whether to copy them or use the evidently intended
  sets: `3dl4..3dl9`, carrier `3dci..3dcp`, tower `3dta..`. The intended
  sets look better and cost the same.
- **Unknowns before matching it exactly:** the render rate, whether the
  original redraws the window every frame (the code does, unconditionally),
  and the manual's "flashing" indicator. A capture from a running Amiga
  would settle all three.

The reproduction helpers are not committed. Repeat the analysis by
disassembling CODE from 0x417e to 0x46c4 and reading the DATA tables named
above.
