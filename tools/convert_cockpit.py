"""The pilot's window: the original's cockpit view (docs/cockpit.md; how the
original draws it: docs/research/amiga-cockpit-view.md).

The original cuts the ground ahead into 11 depth bands and draws, far to
near, one row lower each, pre-drawn shapes from dash.shp sized by band: the
island's ground line and jungle strip, huts, dugouts, AA guns, the carrier
and its tower; over a carrier, a deck view sliding as the plane rolls; the
gunsight last. This module holds the port's half of it:

- the art: the shapes used, scaled to the port's 46-pixel window (3/8
  across, rows kept), packed into the 24 pilot-window atlas slots (slot 0
  is the compose buffer); convert_dashboard.py loads them into VRAM and
  writes their table (`art_source`) next to its own;
- each map's features (`--map`): spans of land, jungle and objects, in map
  columns (8 px), from the original's map words, for msx/cockpit.c;
- a model of the runtime (`scene`, `compose`): the verifiers' oracle.

  python tools/convert_cockpit.py --map a     # src/generated/map_a/cockpit_map.h
  python tools/convert_cockpit.py --views     # docs/cockpit/views.png
"""
import argparse
import functools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury'

WIDTH, HEIGHT, SLOT = 46, 24, 48     # the window, rows, an atlas slot's width
CENTRE = 22                         # the original's x 319 in the window
SKY, SEA, LAND = 2, 9, 5            # dashboard colours (the original's 2, 1, 5)

PLANE_VIEWS = '0123456789abcdefghijklmnop'
# A plane's shape (0..55, +28 facing right; the original's +30), made the
# view seen from the cockpit: +28 more when the player faces right (0x4206).
# The original's name lists (DATA 0x3118, 0x3188): the first 28 and the
# last 28 of each size.
PLANE_LIST = ('0111222334455 6kkllmmnnnooopp'.replace(' ', '') +
              'deeeffffghhiij77889 9aaabbb00'.replace(' ', ''))
# The size by band: zr1 for the nearest 3, zr2 for the next 6, zr3 for the
# farthest 2 (the original's table, -$696c, steps half a set and flips some
# views to the other facing; the sizes are kept, the facing set right).
PLANE_SIZE = [1, 1, 1, 2, 2, 2, 2, 2, 2, 3, 3]
PLANE_STATES = (2, 4)   # flying, shot down (planes.h)
PLANE_SLOTS = 4

# The shapes, in table order. The frame sets are the ones the original
# evidently meant (its arithmetic is off by one or two for trees, the
# carrier facing left and the tower; same cost, see the research's anomalies).
SETS = [('TREE', [f'3dl{i}' for i in range(4, 10)]),
        ('HUT', [f'hut{i}' for i in range(1, 7)]),
        ('WRECK', [f'hut{c}' for c in 'bcdefg']),
        ('DUGOUT', [f'dug{i}' for i in range(1, 7)]),
        ('GUN', [f'pil{i}' for i in range(1, 7)]),
        ('GUN_DAMAGED', [f'pil{c}' for c in 'bcdefg']),
        ('CARRIER', [f'3dc{c}' for c in 'abcdefghijklmnop']),
        ('TOWER', [f'3dt{c}' for c in 'abcdefghijklmnop']),
        ('DECK', [f'dec{i}' for i in range(4)]),
        ('SIGHT', ['targ']),
        # The enemy planes seen from the cockpit (zr*), three sizes.
        ('PLANE1', [f'zr1{c}' for c in PLANE_VIEWS]),
        ('PLANE2', [f'zr2{c}' for c in PLANE_VIEWS]),
        ('PLANE3', [f'zr3{c}' for c in PLANE_VIEWS]),
        # The enemy ships, from their own archives (0x45a6: frames 1..8 of
        # each view, the first facing right). The tallest (29 rows) lose
        # their bottom rows: with the horizon at 12 or lower the top of a
        # near ship is in the window, so no more than 24 rows ever show.
        ('DESTROYER', [f'destroyer.shp:d{v}{k}' for v in 'bs' for k in '12345678']),
        ('BATTLESHIP', [f'battleship.shp:b{v}{k}' for v in 'bs' for k in '12345678']),
        ('CRUISER', [f'cruiseship.shp:c{v}{k}' for v in 'lr' for k in '12345678'])]
SHIP_SETS = ('DESTROYER', 'BATTLESHIP', 'CRUISER')   # by mission_ships.h kind 0..2
NAMES = [n for _, names in SETS for n in names]
FIRST, _count = {}, 0
for _key, _names in SETS:
    FIRST[_key] = _count; _count += len(_names)

# The bands, b = 0 (nearest) .. 10: the ground they cover, in columns ahead
# (the original's EDGE table: d0 .. d0 + w), and the frame by band: ground
# objects 1..6 (K6), carrier and tower 0..7 (K7).
EDGE = [0, 6, 13, 21, 30, 40, 51, 63, 76, 90, 105, 130, 160]
BAND_NEAR = [EDGE[b + 2] for b in range(11)]
BAND_FAR = [2 * EDGE[b + 2] - EDGE[b + 1] for b in range(11)]
K6 = [6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 1]
K7 = [7, 7, 6, 6, 5, 4, 3, 2, 1, 0, 0]
FAR_ALTITUDE = 186                   # above: the distant view, plain sky
# The port's picture sits LIFT rows higher than the original's (horizon
# altitude / 16 + 17 in the window): the near bands stay in the window.
LIFT = 5

# Object kinds in a map's spans.
KIND_HUT, KIND_DUGOUT, KIND_GUN, KIND_CARRIER, KIND_TOWER, KIND_SHIP = range(6)
TOWERS = (0x22, 0xf6)
SCENE_BYTES = 19 + 2 * PLANE_SLOTS   # ... and per plane slot: its row, its view + 1


_RECORDS = {}


def shape(name):
    """A shape (dash.shp, or 'archive:name' from a ship's archive) in
    dashboard colours (0 transparent), trimmed and scaled 3/8 across about
    its origin, at most 24 rows (its top: see SHIP_SETS): (pixels, width,
    height, ox, oy)."""
    from unpack_shapes import read_ppkc, unpack_rpck
    from decode_shapes import decode_record
    archive, name = name.split(':') if ':' in name else ('dash.shp', name)
    if archive not in _RECORDS:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')   # the ship archives' trailing padding
            _RECORDS[archive] = {n.strip(): r for n, _, r in read_ppkc(unpack_rpck((SOURCE / 'shapes' / archive).read_bytes()))}
    raw, meta = decode_record(_RECORDS[archive][name], plane_constants=True)
    # The dashboard's slots: 0 is the sky (transparent here), 1 the dark sea
    # (the dashboard's blue is 9), opaque black 11.
    px = [0 if not p else 11 if not p & 15 else 9 if p & 15 == 1 else p & 15 for p in raw]
    w, h = meta['width'], meta['height']
    ox, oy = meta['origin_candidate']
    cols = [x for x in range(w) if any(px[y * w + x] for y in range(h))]
    x0, x1 = cols[0], cols[-1] + 1
    t0 = (x0 - ox) * 3 // 8
    t1 = -((-(x1 - ox) * 3) // 8)
    tw = max(1, t1 - t0)
    out = bytearray(tw * h)
    for y in range(h):
        for tx in range(tw):
            sx = min(max(ox + int((t0 + tx + 0.5) * 8 / 3), x0), x1 - 1)
            out[y * tw + tx] = px[y * w + sx]
    return bytes(out[:tw * min(h, HEIGHT)]), tw, min(h, HEIGHT), -t0, oy


@functools.lru_cache(maxsize=None)
def art():
    """The shapes packed into slots 1..23 (first fit on an occupancy grid,
    tallest first): the 24 slot images (48 x 24, slot 0 blank: the compose
    buffer) and each shape's (slot, x, y, w, h, ox, oy)."""
    shapes = [shape(n) for n in NAMES]
    order = sorted(range(len(shapes)), key=lambda i: (-shapes[i][2], -shapes[i][1], i))
    slots = [bytearray(SLOT * HEIGHT) for _ in range(24)]
    used = [[bytearray(SLOT) for _ in range(HEIGHT)] for _ in range(24)]
    place = [None] * len(shapes)
    for i in order:
        px, w, h, ox, oy = shapes[i]
        spot = next(((slot, x, y) for slot in range(1, 24) for y in range(HEIGHT - h + 1) for x in range(SLOT - w + 1)
                     if not any(any(used[slot][y + yy][x:x + w]) for yy in range(h))), None)
        assert spot, 'the cockpit shapes overflow the pilot slots'
        slot, x, y = spot
        for yy in range(h):
            used[slot][y + yy][x:x + w] = bytes([1]) * w
            slots[slot][(y + yy) * SLOT + x:(y + yy) * SLOT + x + w] = px[yy * w:(yy + 1) * w]
        place[i] = (slot, x, y, w, h, ox, oy)
    return [bytes(s) for s in slots], place


COCKPIT_BANKS = (52, 58)   # the slots' pixels, packed, 24 bytes a row, 14 slots a bank (msx/cockpit.c Cockpit_Load)
BANK_SLOTS = 8192 // (SLOT * HEIGHT // 2)


def art_source(slots_xy, defines=()):
    """generated/cockpit_art.c (segment 51) and .h: each shape's atlas
    rectangle and origin, from the pilot slots' VRAM places; and the bank
    the slots' pixels load from (slot 0, the compose buffer, is not loaded)."""
    from convert_hellcat import pack_pixels
    images, place = art()
    used = max(p[0] for p in place) + 1
    packed = [pack_pixels(images[s]) for s in range(1, used)]
    banks = {b: b''.join(packed[k * BANK_SLOTS:(k + 1) * BANK_SLOTS]) for k, b in enumerate(COCKPIT_BANKS)}
    assert len(packed) <= BANK_SLOTS * len(COCKPIT_BANKS)
    h = ['/* Generated by tools/convert_cockpit.py (via convert_dashboard.py); do not edit. */', '#pragma once',
         f'#define COCKPIT_SHAPES {len(NAMES)}', f'#define COCKPIT_BUFFER_X {slots_xy[0][0]}u',
         f'#define COCKPIT_BUFFER_Y {slots_xy[0][1]}u', f'#define COCKPIT_SCENE_BYTES {SCENE_BYTES}',
         f'#define COCKPIT_BANK {COCKPIT_BANKS[0]}', f'#define COCKPIT_BANK2 {COCKPIT_BANKS[1]}',
         f'#define COCKPIT_BANK_SLOTS {BANK_SLOTS}', f'#define COCKPIT_SLOTS {used}',
         'extern const unsigned char g_CockpitSlotX[COCKPIT_SLOTS];', 'extern const unsigned short g_CockpitSlotY[COCKPIT_SLOTS];']
    h += [f'#define COCKPIT_{k} {v}' for k, v in defines]   # the window's and the arrows' places (convert_dashboard)
    h += [f'#define COCKPIT_{k} {FIRST[k]}' for k, _ in SETS]
    kinds = {'X': 'unsigned char', 'Y': 'unsigned short', 'DX': 'unsigned char', 'W': 'unsigned char',
             'H': 'unsigned char', 'OY': 'signed char'}
    for name, kind in kinds.items():
        h.append(f'extern const {kind} g_Cockpit{name}[COCKPIT_SHAPES];')
    c = ['/* Generated by tools/convert_cockpit.py (via convert_dashboard.py); do not edit. */',
         '#include "../msx/banking.h"', '#include "cockpit_art.h"', 'WINGS_CODE_SEGMENT(WINGS_SEGMENT_COCKPIT)',
         '/* ' + ' '.join(NAMES) + ' */']
    # Every shape is drawn about the window's centre column: its columns are
    # clipped to the window here, once (X, DX in the buffer, W).
    clipped = []
    for s, x, y, w, hh, ox, oy in place:
        left = CENTRE - ox
        skip = max(0, -left)
        width = min(w - skip, WIDTH - max(left, 0))
        assert width > 0, 'a shape outside the window'
        clipped.append((slots_xy[s][0] + x + skip, slots_xy[0][0] + max(left, 0), width))
    columns = {'X': [c[0] for c in clipped], 'Y': [slots_xy[s][1] + y for s, x, y, w, hh, ox, oy in place],
               'DX': [c[1] for c in clipped], 'W': [c[2] for c in clipped],
               'H': [p[4] for p in place], 'OY': [p[6] for p in place]}
    for name, values in columns.items():
        kind = kinds[name]
        assert all(-128 <= v < 128 if kind == 'signed char' else 0 <= v < (65536 if name == 'Y' else 256) for v in values), name
        c.append(f'const {kind} g_Cockpit{name}[COCKPIT_SHAPES] = {{{", ".join(map(str, values))}}};')
    # Distance ahead (0..190) to the first band reaching it and the last band
    # starting by it (255: none).
    first = [min([b for b in range(11) if BAND_FAR[b] >= d], default=255) for d in range(191)]
    last = [max([b for b in range(11) if BAND_NEAR[b] <= d], default=255) for d in range(191)]
    h += ['extern const unsigned char g_CockpitFirstBand[191];', 'extern const unsigned char g_CockpitLastBand[191];',
          'extern const unsigned char g_CockpitPlaneBand[160];', 'extern const unsigned char g_CockpitPlaneView[56];',
          f'#define COCKPIT_LIFT {LIFT}']
    c.append(f'const unsigned char g_CockpitPlaneBand[160] = {{{", ".join(str(plane_band(d)) for d in range(160))}}};')
    c.append(f'const unsigned char g_CockpitPlaneView[56] = {{{", ".join(str(PLANE_VIEWS.index(v)) for v in PLANE_LIST)}}};')
    c.append(f'const unsigned char g_CockpitFirstBand[191] = {{{", ".join(map(str, first))}}};')
    c.append(f'const unsigned char g_CockpitLastBand[191] = {{{", ".join(map(str, last))}}};')
    c.append(f'const unsigned char g_CockpitSlotX[COCKPIT_SLOTS] = {{{", ".join(str(x) for x, y in slots_xy[:used])}}};')
    c.append(f'const unsigned short g_CockpitSlotY[COCKPIT_SLOTS] = {{{", ".join(str(y) for x, y in slots_xy[:used])}}};')
    return '\n'.join(c) + '\n', '\n'.join(h) + '\n', banks


def plane_band(d):
    """The band of a plane d columns ahead (EDGE[b+1] <= d < EDGE[b+2]), 255: none."""
    return next((b for b in range(11) if EDGE[b + 1] <= d < EDGE[b + 2]), 255)


def horizon(altitude):
    """The port's horizon row: the original's is altitude / 16 + 17, which
    puts the near bands below the window, and above altitude 100 nearly all
    of them; the port's starts 5 rows higher and drops half as fast."""
    return altitude // 32 + 17 - LIFT


def plane_scene(original, b, alt, shape, left):
    """A plane's (row, view + 1) in band b: its row from the original's
    horizon (altitude / 16 + 17), which the gunsight's row matches."""
    row = original + 10 - b - ((alt >> 2) + 4)
    view = FIRST[f'PLANE{PLANE_SIZE[b]}'] + PLANE_VIEWS.index(PLANE_LIST[(shape + (0 if left else 28)) % 56])
    return row, view + 1


def map_words(map_name):
    from decode_mission import parse_map
    cells = parse_map((SOURCE / f'maps/{map_name}.map').read_bytes())['cells']
    return [c['raw_word'] for c in cells]


def runs(columns, gap=0):
    """(first, last) runs of the columns, merging gaps up to `gap` columns."""
    out = []
    for c in columns:
        if out and c - out[-1][1] <= gap + 1: out[-1][1] = c
        else: out.append([c, c])
    return [tuple(r) for r in out]


@functools.lru_cache(maxsize=None)
def features(map_name):
    """The map's spans in columns: land, jungle, and objects (first, last,
    kind, index). Jungle runs merge across gaps of up to 7 columns: no band
    is narrower than 8, so a band touches a merged run exactly when it holds
    a jungle column."""
    words = map_words(map_name)
    ids = [(w >> 2) & 511 for w in words]
    cls = [w & 3 for w in words]
    land = runs([c for c in range(len(words)) if cls[c] == 2])
    trees = runs([c for c in range(len(words)) if cls[c] == 2 and 6 <= ids[c] <= 8], gap=7)
    objects = []
    for kind, test in ((KIND_HUT, lambda i: i in (4, 5)), (KIND_DUGOUT, lambda i: i == 3),
                       (KIND_GUN, lambda i: 15 <= i <= 30)):
        found = runs([c for c in range(len(words)) if cls[c] == 2 and test(ids[c])])
        objects += [(a, b, kind, k) for k, (a, b) in enumerate(found)]
    # Ships: a run with a tower is a carrier (the Japanese one too, with the
    # US carrier's art as in the original); the player's (where the mission
    # starts) has the deck view. The others are the enemy ships, in
    # mission_ships.h's order (their index is their g_ShipsGone bit).
    from decode_mission import parse_map
    start = parse_map((SOURCE / f'maps/{map_name}.map').read_bytes())['reset_x'] >> 3
    ships = ship_records(map_name)
    carrier = None
    for a, b in runs([c for c in range(len(words)) if cls[c] == 1]):
        towers = [c for c in range(a, b + 1) if ids[c] in TOWERS]
        if not towers:
            index = [k for k, (left, right, _) in enumerate(ships) if left < (b + 1) * 8 and right >= a * 8]
            assert len(index) == 1, ('an enemy ship without its record', a, b, ships)
            objects.append((a, b, KIND_SHIP, index[0]))
            continue
        if a <= start <= b: carrier = (a, b)
        objects.append((a, b, KIND_CARRIER, 0))
        objects += [(t0, t1, KIND_TOWER, 0) for t0, t1 in runs(towers)]
    assert carrier, 'no carrier at the start'
    # Huts in the order of the island's records (src/generated/map_*/mission_island.h).
    island = (ROOT / f'src/generated/map_{map_name}/mission_island.h')
    if island.exists():
        found = re.search(r's_HutX\[\d+\] = \{([^}]*)\}', island.read_text())
        count = int(re.search(r'#define ISLAND_HUTS (\d+)', island.read_text()).group(1))
        anchors = [int(v) for v in found.group(1).split(',')][:count] if found else []
        huts = [o for o in objects if o[2] == KIND_HUT]
        assert len(anchors) == len(huts) and all(a * 8 <= x < (b + 1) * 8 for (a, b, _, _), x in zip(huts, anchors)), \
            ('huts do not match the island records', anchors, huts)
    objects.sort()
    return land, trees, objects, carrier


@functools.lru_cache(maxsize=None)
def ship_records(map_name):
    """The enemy ships of src/generated/map_*/mission_ships.h: (left, right, kind)."""
    path = ROOT / f'src/generated/map_{map_name}/mission_ships.h'
    if not path.exists(): return []
    text = path.read_text()
    count = int(re.search(r'#define SHIP_COUNT (\d+)', text).group(1))
    if not count: return []
    values = {n: [int(v) for v in re.search(rf'{n}\[\d+\] = \{{([^}}]*)\}}', text).group(1).split(',')]
              for n in ('s_ShipLeft', 's_ShipRight', 's_ShipKind')}
    return list(zip(values['s_ShipLeft'], values['s_ShipRight'], values['s_ShipKind']))[:count]


def map_header(map_name):
    land, trees, objects, carrier = features(map_name)
    ships = ship_records(map_name)
    def array(kind, name, values):
        values = values or [0]
        return f'static const {kind} {name}[{len(values)}] = {{{", ".join(map(str, values))}}};'
    out = ['/* Generated by tools/convert_cockpit.py; do not edit.',
           ' * The cockpit window\'s features in map columns (8 px). Include only',
           ' * from msx/cockpit.c. */', '#pragma once',
           f'#define COCKPIT_LANDS {len(land)}', f'#define COCKPIT_TREES {len(trees)}',
           f'#define COCKPIT_OBJECTS {len(objects)}',
           f'#define COCKPIT_OBJECT_REACH {max([b - a + 1 for a, b, _, _ in objects], default=1)}u   /* the longest object span */',
           f'#define COCKPIT_CARRIER_FIRST {carrier[0] if carrier else 0xFFFF}u',
           f'#define COCKPIT_CARRIER_LAST {carrier[1] if carrier else 0}u',
           array('uint16_t', 's_LandFirst', [a for a, b in land]), array('uint16_t', 's_LandLast', [b for a, b in land]),
           array('uint16_t', 's_TreeFirst', [a for a, b in trees]), array('uint16_t', 's_TreeLast', [b for a, b in trees]),
           '/* kind: 0 hut (index: g_Island.hut), 1 dugout, 2 AA gun, 3 carrier, 4 its tower, 5 enemy ship (index: its g_ShipsGone bit) */',
           array('uint16_t', 's_ObjectFirst', [o[0] for o in objects]), array('uint16_t', 's_ObjectLast', [o[1] for o in objects]),
           array('uint8_t', 's_ObjectKind', [o[2] for o in objects]), array('uint8_t', 's_ObjectIndex', [o[3] for o in objects]),
           '/* Each enemy ship\'s views (its kind: COCKPIT_DESTROYER, _BATTLESHIP, _CRUISER). */',
           array('uint8_t', 's_ShipView', [f'COCKPIT_{SHIP_SETS[k]}' if k < 3 else 'COCKPIT_CARRIER' for _, _, k in ships])]
    return '\n'.join(out) + '\n'


# The runtime's model (msx/cockpit.c), for the verifiers.

def scene(map_name, x, altitude, facing_left, arrow=0, wrecked=(), planes=(), gone=0):
    """The scene bytes msx/cockpit.c computes (g_Cockpit.scene); planes:
    (state, x, alt, shape) per slot."""
    land, trees, objects, carrier = features(map_name)
    s = bytearray(SCENE_BYTES)
    s[2] = arrow
    if altitude > FAR_ALTITUDE:
        s[0] = 255
        return bytes(s)
    col = x >> 3
    s[0] = horizon(altitude)
    s[3] = 17 if altitude >= 81 else (81 - altitude) // 4 + 6
    deck = carrier and carrier[0] <= col <= carrier[1]
    s[1] = facing_left
    if deck:
        n = carrier[1] - col + 1 if facing_left else col - carrier[0] + 1
        s[1] |= 2 | (n // 6 if n < 90 else 15) << 4
    def ahead(a, b):
        return (col - b, col - a) if facing_left else (a - col, b - col)
    def bands(a, b):
        lo, hi = ahead(a, b)
        return [k for k in range(11) if lo <= BAND_FAR[k] and hi >= BAND_NEAR[k]], hi
    for spans, at in ((land, 4), (trees, 6)):
        mask = 0
        for a, b in spans:
            for k in bands(a, b)[0]: mask |= 1 << k
        s[at], s[at + 1] = mask & 255, mask >> 8
    far = [-1] * 11
    ships = ship_records(map_name)
    for a, b, kind, index in objects:
        if deck and kind in (KIND_CARRIER, KIND_TOWER, KIND_SHIP): continue
        if kind == KIND_SHIP and gone >> index & 1: continue
        found, hi = bands(a, b)
        for k in found:
            d = min(hi, BAND_FAR[k])
            current = s[8 + k] - 1
            if current >= FIRST['TOWER'] and current < FIRST['DECK']: continue   # a tower sticks
            if kind != KIND_TOWER and d <= far[k]: continue
            far[k] = d
            if kind == KIND_HUT:
                frame = (FIRST['WRECK'] if index in wrecked else FIRST['HUT']) + K6[k] - 1
            elif kind == KIND_DUGOUT: frame = FIRST['DUGOUT'] + K6[k] - 1
            elif kind == KIND_GUN: frame = FIRST['GUN'] + K6[k] - 1
            elif kind == KIND_SHIP:
                frame = FIRST[SHIP_SETS[ships[index][2]]] + K7[k] + (8 if facing_left else 0)
            else: frame = FIRST['CARRIER' if kind == KIND_CARRIER else 'TOWER'] + K7[k] + (8 if facing_left else 0)
            s[8 + k] = frame + 1
    # The planes, slot by slot: in a band 48..1280 px ahead, and in rows
    # -12..35 of the window (else not shown).
    for i, (state, px, alt, shape) in enumerate(planes):
        if state not in PLANE_STATES: continue
        d = (col - (px >> 3)) if facing_left else ((px >> 3) - col)
        if not 0 <= d < 160 or plane_band(d) == 255: continue
        row, view = plane_scene(altitude // 16 + 17, plane_band(d), alt, shape, facing_left)
        if -12 <= row < 36: s[19 + 2 * i], s[20 + 2 * i] = row & 255, view
    return bytes(s)


def compose(scene_bytes, arrows=None):
    """The window (46 x 24 dashboard colours) msx/cockpit.c draws for these
    scene bytes; arrows: convert_dashboard.arrow_frames()."""
    slots, place = art()
    s = scene_bytes
    win = bytearray([SKY]) * (SLOT * HEIGHT)
    def blit(i, row, top=0):
        slot, sx, sy, w, h, ox, oy = place[i]
        for yy in range(h):
            for xx in range(w):
                X, Y = CENTRE - ox + xx, row - oy + yy
                c = slots[slot][(sy + yy) * SLOT + sx + xx]
                if c and top <= Y < HEIGHT and 0 <= X < WIDTH: win[Y * SLOT + X] = c
    base = s[0]
    if base != 255:
        for y in range(base, HEIGHT): win[y * SLOT:(y + 1) * SLOT] = bytes([SEA]) * SLOT
        land = s[4] | s[5] << 8; trees = s[6] | s[7] << 8
        # The ground, far to near, then the targets on it: the port draws
        # them last, so a nearer band's jungle does not hide them.
        for k in range(10, -1, -1):
            row = base + 10 - k
            if land >> k & 1 and row < HEIGHT: win[row * SLOT:(row + 1) * SLOT] = bytes([LAND]) * SLOT
            if trees >> k & 1: blit(FIRST['TREE'] + K6[k] - 1, row)
        # The deck view, then the gunsight: under the targets and planes
        # (the original draws it last, over them, at the column they are on).
        if s[1] & 2:
            step = s[1] >> 4; y = base + step + 9; top = base + max(0, step - 7)
            left = s[1] & 1
            blit(FIRST['DECK'] + min(3, step // 2), y + 1, top)
            blit(FIRST['CARRIER'] + (13 if left else 5), y, top)
            blit(FIRST['TOWER'] + (13 if left else 5), y)
        blit(FIRST['SIGHT'], s[3])
        for k in range(10, -1, -1):
            if s[8 + k]: blit(s[8 + k] - 1, base + 10 - k)
        # The planes, the farthest size first, then by slot.
        def size(view): return 3 if view - 1 >= FIRST['PLANE3'] else 2 if view - 1 >= FIRST['PLANE2'] else 1
        order = sorted((i for i in range(PLANE_SLOTS) if s[20 + 2 * i]), key=lambda i: (-size(s[20 + 2 * i]), i))
        for i in order:
            row = s[19 + 2 * i]
            blit(s[20 + 2 * i] - 1, row - 256 if row > 127 else row)
    if s[2] and arrows:
        pixels, ax = arrows[s[2] - 1]
        for yy in range(len(pixels) // 16):
            for xx in range(16):
                c = pixels[yy * 16 + xx]
                if c and 0 <= ax + xx < WIDTH: win[yy * SLOT + ax + xx] = c
    return bytes(b for y in range(HEIGHT) for b in win[y * SLOT:y * SLOT + WIDTH])


VIEWS = [('a', 'Flying west over the island, altitude 40: the dugout, the huts, the far dugout', [(3700, 40, 1), (3300, 40, 1), (2900, 40, 1), (2600, 40, 1)]),
         ('a', 'The same at altitude 150', [(3700, 150, 1), (3300, 150, 1), (2900, 150, 1), (2600, 150, 1)]),
         ('a', 'Both huts wrecked (altitude 40)', [(3700, 40, 1, {0, 1}), (3300, 40, 1, {0, 1}), (2900, 40, 1, {0, 1}), (2600, 40, 1, {0, 1})]),
         ('a', 'An enemy plane ahead, closing (player at altitude 80)', [(5200, 80, 1, (), [(2, 5200 - d, 80, 0)]) for d in (900, 600, 350, 150)]),
         ('a', 'Back east to the carrier, altitude 50', [(5300, 50, 0), (5800, 50, 0), (6200, 50, 0), (6450, 50, 0)]),
         ('a', 'Landing from the east, then rolling along the deck', [(7550, 45, 1), (7420, 44, 1), (7340, 40, 1), (7200, 40, 1)]),
         ('j', 'Map j: the destroyer, then the battleship (altitude 40)', [(1600, 40, 1), (1000, 40, 1), (6300, 40, 0), (6900, 40, 0)]),
         ('a', 'Climbing: the horizon drops; above 186 the distant view', [(4300, 0, 1), (4300, 100, 1), (4300, 160, 1), (4300, 200, 1)])]


def views(path):
    """docs/cockpit/views.png: the model's window in typical places."""
    from PIL import Image, ImageDraw
    from convert_dashboard import dashboard_palette
    pal = dashboard_palette()
    rgb = [v for i in range(16) for v in (((pal[2 * i] >> 4) & 7) * 255 // 7, (pal[2 * i + 1] & 7) * 255 // 7, (pal[2 * i] & 7) * 255 // 7)]
    w, h = WIDTH * 4, HEIGHT * 4
    sheet = Image.new('RGB', (4 * (w + 12) + 12, len(VIEWS) * (h + 30) + 10), (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    for r, (m, title, cases) in enumerate(VIEWS):
        y0 = 10 + r * (h + 30)
        draw.text((12, y0), title, fill=(220, 220, 220))
        for k, case in enumerate(cases):
            x, alt, left = case[:3]
            window = compose(scene(m, x, alt, left, 0, case[3] if len(case) > 3 else (), case[4] if len(case) > 4 else ()))
            im = Image.frombytes('P', (WIDTH, HEIGHT), window)
            im.putpalette(rgb + [0] * 720)
            sheet.paste(im.convert('RGB').resize((w, h), Image.NEAREST), (12 + k * (w + 12), y0 + 16))
    sheet.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--map', default='a')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--views', action='store_true', help='write docs/cockpit/views.png')
    args = parser.parse_args()
    if args.views:
        views(ROOT / 'docs/cockpit/views.png')
        return
    path = ROOT / f'src/generated/map_{args.map}/cockpit_map.h'
    text = map_header(args.map)
    if args.check:
        assert path.read_text() == text, f'{path} is out of date'
        return
    path.write_text(text)


if __name__ == '__main__':
    main()
