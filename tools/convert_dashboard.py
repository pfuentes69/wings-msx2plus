"""Adapt the original IFF dashboard to the mission SCREEN 5 display."""
import argparse
import hashlib
from io import BytesIO
import itertools
import json
import struct
from pathlib import Path
from PIL import Image
from convert_hellcat import c_array, pack_pixels
from extract_iff import iff_img
import convert_cockpit
from unpack_shapes import read_ppkc, unpack_rpck
from decode_shapes import decode_record

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes'

# ---- 248-pixel recomposition of the original 640x37 hi-res panel ----
# The panel is reduced exactly 2:1 (where a pixel pair differs, the locally
# rarer colour is kept, preserving 1-pixel detail), then whole columns that
# equal a neighbour are removed until 248 visible pixels remain. The dials keep
# their native size; only flat frame, green and box-interior columns go.
PANEL_REMOVE = frozenset({0, 1, 9, 10, 11, 12, 13, 15, 27, 39, 18, 19, 30, 31, 41, 42, 43,
    71, 72, 73, 74, 75, 76, 84, 124, 127, *range(131, 145), 193, 196, 235, 236,
    *range(243, 249), *range(270, 282), *range(305, 312), 317, 318, 319})
PANEL_DROP_ROW = 2  # identical to row 1; the dashboard has 36 rows below the separator
NEEDLES = tuple('ndl' + c for c in '123456789abcdefghijklmn')  # empty (0) .. full (22)
NEEDLE_FULL = len(NEEDLES) - 1
DIAL_HUB = {'oil': (208, 19), 'fuel': (430, 19)}    # needle origin, hi-res
DIAL_LAMP = {'oil': (208, 12), 'fuel': (430, 12)}   # olof origin, hi-res
# A new plane reads OIL at frame 16 (oil 128) and FUEL at 22 (fuel 192); see
# docs/research/amiga-fuel-oil.md. Oil reaches frame 22 only under throttle.
NEEDLE_NEW_OIL = 16
SCORE_DIGITS = 6
PILOT_WIDTH = 46
LABEL_FONT = {
    'O': ('.##.', '#..#', '#..#', '#..#', '.##.'),
    'I': ('###', '.#.', '.#.', '.#.', '###'),
    'L': ('#..', '#..', '#..', '#..', '###'),
    'F': ('###', '#..', '##.', '#..', '#..'),
    'U': ('#..#', '#..#', '#..#', '#..#', '.##.'),
    'E': ('###', '#..', '##.', '#..', '###'),
}
BLACK, WHITE, LAMP_ON, LAMP_RIM = 11, 15, 10, 8
DEFAULT_STATE = dict(oil=NEEDLE_NEW_OIL, fuel=NEEDLE_FULL, oil_lamp=False, fuel_lamp=False,
                     ammo=30, lives=3, weapon=0, score=0, kills=0, kill_icons=0)
# The kill icons (0xf178: dash.shp `zero`, one per kill): the original's 14
# (7 a row, 13 px apart on its 640-wide dashboard) do not fit the MSX
# panel's green field (26 x 9 px): KILL_ICONS_MAX, 4 a row, 6 px apart.
KILL_ICONS_MAX = 8


def digit_glyphs():
    """Original white counter digits (wnum): 12x7 hi-res, 2-pixel strokes -> 6x7."""
    sprite, _ = dashboard_shape('wnum')
    return [tuple(''.join('#' if sprite.getpixel((2 + 2*x, 2 + d*8 + y)) != 16 else '.'
                          for x in range(6)) for y in range(7)) for d in range(10)]


def _reduce_half(image):
    width, height = image.size; source = image.load()
    result = Image.new('P', (width // 2, height)); target = result.load()
    for y in range(height):
        for x in range(width // 2):
            a, b = source[2*x, y], source[2*x+1, y]
            if a != b:
                near = [source[xx, yy] for xx in range(max(0, 2*x-3), min(width, 2*x+5))
                        for yy in range(max(0, y-1), min(height, y+2))]
                a = a if near.count(a) <= near.count(b) else b
            target[x, y] = a
    return result


def _paste(image, name, x, y, recolor=None):
    sprite, meta = dashboard_shape(name)
    ox, oy = meta['origin_candidate']
    for yy in range(sprite.height):
        for xx in range(sprite.width):
            color = sprite.getpixel((xx, yy))
            if color == 16 or (name == 'olon' and color == 17):
                continue
            color = recolor.get(color, color & 15) if recolor else color & 15
            if 0 <= x-ox+xx < image.width and 0 <= y-oy+yy < image.height:
                image.putpixel((x-ox+xx, y-oy+yy), color)


def panel_columns():
    keep = [x for x in range(320) if x not in PANEL_REMOVE]
    assert len(keep) == 248
    return keep, {x: i for i, x in enumerate(keep)}


def _col(x320):
    """Screen x of a kept reduced-panel column."""
    return 8 + panel_columns()[1][x320]


def _row(y37):
    """Dashboard row (0..39, screen line 172 + row) of a reduced-panel row."""
    return 4 + y37 - (y37 > PANEL_DROP_ROW)


def _text(pixels, x, y, text, color, font):
    for char in text:
        rows = font[char]
        for yy, row in enumerate(rows):
            for xx, bit in enumerate(row):
                if bit == '#': pixels[(y+yy)*256 + x+xx] = color
        x += len(rows[0]) + 1


def _box(pixels, x0, x1, y0, y1, color):
    for y in range(y0, y1+1):
        pixels[y*256+x0:y*256+x1+1] = bytes([color]) * (x1-x0+1)


def weapon_icon(weapon):
    """Original bomb/misl/torp icon reduced 2:1; uniform body columns removed to fit."""
    sprite, _ = dashboard_shape(('bomb', 'misl', 'torp')[weapon])
    rows = [[sprite.getpixel((2*x, y)) for x in range(sprite.width // 2)] for y in range(sprite.height)]
    # The leading 12-pixel square (colour 22) is the source's own green
    # background, not part of the icon.
    rows = [[16 if c == 22 else c for c in r] for r in rows]
    columns = [x for x in range(len(rows[0])) if any(r[x] != 16 for r in rows)]
    rows = [[r[x] for x in columns] for r in rows]
    x0, x1 = _col(14) + 1, _col(38) - 1
    room = x1 - x0 + 1 - 2  # a 1-pixel margin each side when possible
    while len(rows[0]) > room:
        for x in range(len(rows[0]) - 2, 0, -1):
            if all(r[x] == r[x+1] for r in rows):
                for r in rows: del r[x]
                break
        else:
            break
    if len(rows[0]) > x1 - x0 + 1:
        raise ValueError('weapon icon does not fit its box')
    return [[(16 if c == 16 else c & 15) for c in r] for r in rows]


def _counter_x(lo, hi):
    """Screen x of a 6-pixel digit centred in the white box spanning lo..hi."""
    x0, x1 = _col(lo), _col(hi)
    return x0 + (x1 - x0 + 1 - 6) // 2


def layout():
    """Screen-coordinate layout shared by the converter, runtime header and oracles."""
    ammo = [_counter_x(16, 25), _counter_x(28, 37)]
    score_x1 = _col(303)
    kills_x0, kills_x1 = _col(249), _col(266)
    window = _col(130)
    return dict(ammo_x=ammo, ammo_y=_row(20), lives_x=_counter_x(58, 66),
                lives_y=_row(20),
                score_x=score_x1 - 1 - (SCORE_DIGITS * 7 - 1) + 1, score_y=_row(11),
                kills_x=kills_x0 + (kills_x1 - kills_x0 + 1 - 13) // 2, kills_y=_row(21),
                pilot_x=window, pilot_y=_row(8))


_COMPOSED = {}


def compose(**changes):
    """The 256x40 dashboard (MSX dashboard-palette indices) for a HUD state."""
    state = dict(DEFAULT_STATE, **changes)
    key = tuple(sorted(state.items()))
    if key not in _COMPOSED:
        _COMPOSED[key] = bytes(_compose(state))
    return bytearray(_COMPOSED[key])


def _compose(state):
    image, _ = original()
    image = image.copy()
    for dial in ('oil', 'fuel'):
        _paste(image, NEEDLES[state[dial]], *DIAL_HUB[dial])
        if state[dial + '_lamp']:
            _paste(image, 'olof', *DIAL_LAMP[dial], recolor={28: LAMP_RIM, 19: LAMP_ON})
    reduced = _reduce_half(image).load()
    keep, at = panel_columns()
    for x in PANEL_REMOVE:
        if not any(0 <= x+d < 320 and all(reduced[x, y] == reduced[x+d, y] for y in range(37)) for d in (-1, 1)):
            raise ValueError(f'panel column {x} is not a duplicate')
    if any(reduced[x, PANEL_DROP_ROW] != reduced[x, PANEL_DROP_ROW-1] for x in range(320)):
        raise ValueError('dropped panel row is not a duplicate')
    pixels = bytearray([1]) * (256 * 40)
    rows = [y for y in range(37) if y != PANEL_DROP_ROW]
    for row, y in enumerate(rows):
        for column, x in enumerate(keep):
            p = reduced[x, y]
            pixels[(row+4)*256 + 8+column] = 11 if p == 0 else 9 if p == 1 else p
    sx, sy = _col, _row
    digits = {str(i): g for i, g in enumerate(digit_glyphs())}
    digits[' '] = ('......',) * 7
    # OIL/FUEL legends: the reduced hi-res lettering breaks up, so redraw it in
    # a 1-pixel-stroke face matching the original 2-pixel hi-res strokes.
    for centre, lo, hi, word in ((104, 95, 113, 'OIL'), (215, 205, 226, 'FUEL')):
        _box(pixels, sx(lo), sx(hi), sy(29), sy(33), BLACK)
        width = sum(len(LABEL_FONT[c][0]) + 1 for c in word) - 1
        _text(pixels, sx(centre) - width // 2, sy(29), word, WHITE, LABEL_FONT)
    spots = layout()
    for value, (lo, hi), x in zip(f"{state['ammo']:02d}", ((16, 25), (28, 37)), spots['ammo_x']):
        _box(pixels, sx(lo), sx(hi), sy(19), sy(27), WHITE)
        _text(pixels, x, spots['ammo_y'], value, BLACK, digits)
    _box(pixels, sx(58), sx(66), sy(19), sy(27), WHITE)
    _text(pixels, spots['lives_x'], spots['lives_y'], str(min(state['lives'], 9)), BLACK, digits)
    _box(pixels, sx(14) + 1, sx(38) - 1, sy(11), sy(17), BLACK)
    icon = weapon_icon(state['weapon'])
    x0 = sx(14) + 1 + (sx(38) - 1 - (sx(14) + 1) + 1 - len(icon[0])) // 2
    for yy, row in enumerate(icon):
        for xx, color in enumerate(row):
            if color != 16: pixels[(sy(12)+yy)*256 + x0+xx] = color
    _box(pixels, sx(249), sx(303), sy(10), sy(18), BLACK)
    if state['score'] is not None:
        _text(pixels, spots['score_x'], spots['score_y'], str(state['score']).rjust(SCORE_DIGITS), WHITE, digits)
    _box(pixels, sx(249), sx(266), sy(20), sy(28), BLACK)
    _text(pixels, spots['kills_x'], spots['kills_y'], f"{min(state['kills'], 99):02d}", WHITE, digits)
    if state['kill_icons']:
        icon = kill_icon()
        x0, y0 = KILL_ICON_ORIGIN
        for k in range(min(state['kill_icons'], KILL_ICONS_MAX)):
            for yy in range(5):
                for xx in range(5):
                    if icon[yy * 5 + xx]: pixels[(y0 + 4 * (k // 4) + yy) * 256 + x0 + 6 * (k % 4) + xx] = WHITE
    return pixels


# The green field right of the kills box: icons from here (dashboard rows).
KILL_ICON_ORIGIN = (226, 23)


def kill_icon():
    """dash.shp `zero` (10 x 5 on the 640-wide dashboard) halved: 5 x 5."""
    image, meta = dashboard_shape('zero')
    w, h = meta['width'], meta['height']
    px = image.tobytes()
    return [1 if any(px[y * w + x] != meta['base_color_candidate'] for x in (2 * c, 2 * c + 1)) else 0
            for y in range(h) for c in range(5)]


def original():
    image, metadata = iff_img(SOURCE / 'iff-dash')
    if image.size != (640, 37) or image.mode != 'P':
        raise ValueError('unexpected original dashboard geometry')
    return image, metadata

def dashboard_palette():
    """Use the original instrument colors during the fixed dashboard raster."""
    source = original()[0].getpalette()
    palette = bytearray()
    for i in range(16):
        r, g, b = (round(v * 7 / 240) for v in source[i*3:i*3+3])
        palette.extend(((r << 4) | b, g))
    # Index zero is also the hardware-masked border: keep the flight sky.
    palette[:2] = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()[:2]
    # A shared dark-sea slot keeps the separator stable while colors change.
    # Move the dashboard blue to unused pink slot 9, leaving slot 1 unchanged.
    palette[18:20] = palette[2:4]
    palette[2:4] = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()[2:4]
    return bytes(palette)


def dashboard_shape(name):
    for key, _, raw in read_ppkc(unpack_rpck((SOURCE / 'dash.shp').read_bytes())):
        if key == name:
            pixels, meta = decode_record(raw)
            return Image.frombytes('P', (meta['width'], meta['height']), pixels), meta
    raise ValueError(f'missing dashboard sprite {name}')


HUD_ELEMENTS = (
    # name, bank, variant states (index = runtime value), rectangle group
    ('AMMO_TENS', 17, [dict(ammo=d * 10) for d in range(10)], None),
    ('AMMO_UNITS', 17, [dict(ammo=30 + d) for d in range(10)], None),
    ('LIVES', 17, [dict(lives=d) for d in range(10)], None),
    ('WEAPON', 17, [dict(weapon=w) for w in range(3)], None),
    # Each dial frame exists with the lamp dark and lit: needles at the lamp's
    # thresholds (oil < 116, fuel <= 64) do cross it, and the needle is drawn
    # over the lamp, as in the original.
    ('OIL_DIAL', 17, [dict(oil=f) for f in range(len(NEEDLES))], 'oil'),
    ('FUEL_DIAL', 18, [dict(fuel=f) for f in range(len(NEEDLES))], 'fuel'),
    ('OIL_DIAL_LIT', 19, [dict(oil=f, oil_lamp=True) for f in range(len(NEEDLES))], 'oil'),
    ('FUEL_DIAL_LIT', 20, [dict(fuel=f, fuel_lamp=True) for f in range(len(NEEDLES))], 'fuel'),
    # Kills (HUD-07, 0xf178): two digits and the icons.
    ('KILLS_TENS', 19, [dict(kills=d * 10) for d in range(10)], None),
    ('KILLS_UNITS', 19, [dict(kills=d) for d in range(10)], None),
    ('KILL_ICONS', 19, [dict(kill_icons=n) for n in range(KILL_ICONS_MAX + 1)], None),
)


def hud_variants():
    """Byte-aligned dashboard rectangles, one pre-rendered copy per value.

    Each rectangle covers every pixel its element (or rectangle group) can
    change; the rest is the static panel, so any value can be copied in on
    its own. Lit and dark dial frames share one rectangle.
    """
    bounds = {}
    for name, bank, states, group in HUD_ELEMENTS:
        reference = compose(**{k: v for k, v in states[0].items() if not k.endswith('_lamp')})
        changed = [i for state in states for i, (a, b) in enumerate(zip(reference, compose(**state))) if a != b]
        key = group or name
        bounds.setdefault(key, []).extend(changed)
    elements = []
    for name, bank, states, group in HUD_ELEMENTS:
        changed = bounds[group or name]
        xs = [i % 256 for i in changed]; ys = [i // 256 for i in changed]
        x0, x1, y0, y1 = min(xs) & ~1, max(xs) | 1, min(ys), max(ys)
        renders = [compose(**state) for state in states]
        data = b''.join(pack_pixels(bytes(render[y*256+x] for y in range(y0, y1+1) for x in range(x0, x1+1)))
                        for render in renders)
        elements.append(dict(name=name, bank=bank, group=group, x=x0, y=y0, width=x1-x0+1, height=y1-y0+1,
                             count=len(renders), data=data))
    for a in elements:
        for b in elements:
            if a is b or (a['group'] and a['group'] == b['group']): continue
            if (a['x'] < b['x'] + b['width'] and b['x'] < a['x'] + a['width'] and
                    a['y'] < b['y'] + b['height'] and b['y'] < a['y'] + a['height']):
                raise ValueError(f"HUD rectangles overlap: {a['name']} {b['name']}")
    return elements


def panel():
    """The default dashboard: full gauges, lamps off, 30 bombs, three lives."""
    return bytes(compose())

def reticle():
    im, _ = dashboard_shape('targ')
    im = im.resize((12, 9), Image.Resampling.NEAREST)
    return bytes(0 if p == 16 else 9 if p & 15 == 1 else p & 15 for p in im.tobytes())

def rle(packed):
    encoded = bytearray()
    for value, group in itertools.groupby(packed):
        count = len(list(group))
        while count:
            take = min(count, 255); encoded.extend((take, value)); count -= take
    return encoded

def ui_shape(name):
    im, meta = dashboard_shape(name)
    return bytes(0 if p == 16 else 9 if p & 15 == 1 else p & 15 for p in im.tobytes()), meta

def pilot_frame(kind, level):
    """Forward-looking pilot display, PILOT_WIDTH pixels wide in a 48-pixel slot.

    The horizon recedes with altitude; source perspective strips and carrier
    silhouettes replace the former side map. The two padding columns on the
    right are never copied to the screen.
    """
    width = PILOT_WIDTH
    horizon = 17 + level * 2
    pixels = bytearray([2]) * (48 * 24)
    for y in range(min(24, horizon), 24):
        pixels[y*48:y*48+width] = bytes([6 if kind == 2 else 9]) * width
    if kind:
        name = '3dl9' if kind == 2 else '3dc' + chr(ord('a') + max(0, 7-level))
        source, meta = ui_shape(name)
        scaled = max(2, round(meta['width'] * width / 128))
        resized = Image.frombytes('P', (meta['width'], meta['height']), source).resize(
            (scaled, meta['height']), Image.Resampling.NEAREST)
        ox = round(meta['origin_candidate'][0] * width / 128)
        oy = meta['origin_candidate'][1]
        for yy in range(meta['height']):
            for xx in range(scaled):
                dx, dy = width // 2 - ox + xx, horizon - oy + yy
                color = resized.tobytes()[yy*scaled+xx]
                if color and 0 <= dx < width and 0 <= dy < 24: pixels[dy*48+dx] = color
    target = reticle()
    for y in range(9):
        for x in range(12):
            c = target[y*12+x]
            if c: pixels[(4+y)*48 + (width-12)//2 + x] = c
    return bytes(pixels)

def ocean_artwork():
    """Keep source wave indices and the separate ocean palette together."""
    palette, _ = iff_img(SOURCE / 'ocean.palette')
    records={name:raw for name,_,raw in read_ppkc(unpack_rpck((SOURCE/'world.shp').read_bytes()))}
    frames=[]
    for letter in 'abcdefghijkl':
        pixels,meta=decode_record(records['wav'+letter], plane_constants=True)
        if (meta['width'],meta['height'])!=(96,11): raise ValueError('wave dimensions changed')
        if any(v == 0 for v in pixels[192:]):
            raise ValueError('wave transparency extends beyond the two restored rows')
        frames.append(pixels)
    return frames, bytes(palette.getpalette()[:96])

def wave_mapping():
    _, source = ocean_artwork()
    target = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    colors = [(target[i*2] >> 4, target[i*2+1], target[i*2] & 7) for i in range(16)]
    # Retain the shared aircraft palette. Fit opaque ocean shades to its five
    # blue slots; zero alone is transparent, never a substitute for dark sea.
    return {i: (0 if i == 0 else min(range(1,6), key=lambda j:
        sum((source[i*3+c]*7/240-colors[j][c])**2 for c in range(3))))
        for i in range(32)}

def waves():
    frames, _ = ocean_artwork()
    mapping = wave_mapping()
    return [bytes(mapping[v] for v in frame) for frame in frames]

# The original's 12 tumble frames (shapes 0x40..0x4b, torpedo.shp bom0..bomb):
# a bomb starts at bom3 (nose left) moving left or bom9 moving right and steps
# one frame every second original tick (0x07f2, 0x0cca).
BOMB_NAMES = tuple(f'bom{n:x}' for n in range(12))
BOMB_HEIGHT = 6   # every frame fits 7 x 6

def bomb_frames():
    """Each frame cropped into an 8 x BOMB_HEIGHT cell (7 px wide at most, so
    an 8-px byte-aligned backup always covers it): pixels and the pivot's (x, y)
    in the cell (the bomb's position is drawn at the pivot)."""
    records={n:r for n,_,r in read_ppkc(unpack_rpck((SOURCE/'torpedo.shp').read_bytes()))}
    mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
    result,pivots=bytearray(len(BOMB_NAMES)*8*BOMB_HEIGHT),[]
    for frame,name in enumerate(BOMB_NAMES):
        pixels,meta=decode_record(records[name],plane_constants=True)
        ox,oy=meta['origin_candidate']
        points=[(i%meta['width']-ox,i//meta['width']-oy,c) for i,c in enumerate(pixels) if c]
        px=-min(x for x,_,_ in points);py=-min(y for _,y,_ in points)
        if max(x for x,_,_ in points)+px>=7 or max(y for _,y,_ in points)+py>=BOMB_HEIGHT:raise ValueError('bomb exceeds its cell')
        for x,y,c in points:result[(frame*BOMB_HEIGHT+y+py)*8+x+px]=mapping[str(c)]
        pivots.append((px,py))
    return bytes(result),pivots

def bomb_pixels():
    return bomb_frames()[0]

# The enemy planes' frame slots (src/msx/smoke_draw.c): 4 cells of 48 x 26
# in the tile cells the tile cache gave up (slots 40..51: page 3, x 64..159,
# rows 180..231). A plane's near frame streams into one from ROM.
PLANE_SLOT_SIZE = (48, 26)
PLANE_SLOTS = tuple((64 + 48 * (k % 2), 768 + 180 + 26 * (k // 2)) for k in range(4))
# The pilot window's torpedo-plane arrows (dash.shp ltar, rtar; 0xf21a), in
# 16 x 5 cells below the plane slots.
ARROW_SLOTS = ((64, 768 + 232), (80, 768 + 232))
ARROW_HEIGHT = 5


def arrow_frames():
    """ltar and rtar for the pilot window: drawn at (320, 10) on the
    original's 640-wide dashboard, around the window's top centre (window
    x 256..384, top row 8); scaled to the 46-pixel window as the pilot
    views are. Returns [(pixels 16 x 5, window x)]."""
    out = []
    for name in ('ltar', 'rtar'):
        image, meta = dashboard_shape(name)   # one bit-plane over its base colour 21
        source = bytes(0 if p == meta['base_color_candidate'] else p & 15 for p in image.tobytes())
        w, h = meta['width'], meta['height']
        if h != ARROW_HEIGHT: raise ValueError('arrow height changed')
        scaled = round(w * PILOT_WIDTH / 128)
        image = Image.frombytes('P', (w, h), source).resize((scaled, h), Image.Resampling.NEAREST).tobytes()
        pixels = bytearray(16 * h)
        for y in range(h):
            pixels[y * 16:y * 16 + scaled] = image[y * scaled:(y + 1) * scaled]
        out.append((bytes(pixels), round((320 - meta['origin_candidate'][0] - 256) * PILOT_WIDTH / 128)))
    return out


def atlas_slots(count, reserve_water=False, reserve_ship=False, reserve_combat=False, reserve_crew=False, frames=None, reserve_wheels=(), reserve_rope=False, reserve_smoke=(), reserve_rockets=()):
    if frames is None: frames=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
    tiles=json.loads((ROOT/'assets_msx/mission_a/manifest.json').read_text())['selected']['tile_count']
    occupied=[bytearray(256) for _ in range(512)]
    # VRAM row 1023 (page 3's last) is overwritten at run time: never allocate it.
    occupied[511][:]=bytes([1])*256
    for f in frames:
        if f.get('streamed') or f.get('unused'): continue
        for y in range(f['atlas_y']-512,f['atlas_y']-512+f['height']):
            occupied[y][f['atlas_x']:f['atlas_x']+f['width']]=bytes([1])*f['width']
    for tile in range(tiles):
        x=tile%288//9*8;y=tile//288*256+180+tile%9*8
        for row in range(y,y+8):occupied[row][x:x+8]=bytes([1])*8
    slots=[]
    for y in range(489):
        for x in range(0,209,2):
            if all(not any(occupied[row][x:x+48]) for row in range(y,y+24)):
                slots.append((x,y+512))
                for row in range(y,y+24):occupied[row][x:x+48]=bytes([1])*48
                if len(slots)==count:
                    if not reserve_water: return slots
                    def allocate(number,width,height):
                        result=[]
                        for yy in range(513-height):
                            for xx in range(0,257-width,2):
                                if all(not any(occupied[r][xx:xx+width]) for r in range(yy,yy+height)):
                                    result.append((xx,yy+512))
                                    for r in range(yy,yy+height):occupied[r][xx:xx+width]=bytes([1])*width
                                    if len(result)==number:return result
                        raise ValueError(f'not enough {width}x{height} atlas rectangles')
                    backups=allocate(2,256,4)
                    tails=allocate(3,96,2)
                    if reserve_ship:
                        ships = allocate(24,16,14)
                        if reserve_combat:
                            if reserve_crew:
                                crew=allocate(34,22,7)
                                weapons=allocate(36,8,8)
                                bombs=allocate(len(BOMB_NAMES),8,BOMB_HEIGHT)
                                if reserve_wheels:
                                    # Landing-gear overlay pieces (tools/convert_hellcat.py),
                                    # allocated last so nothing above moves; largest first,
                                    # each at its own size, in the leftover gaps.
                                    order=sorted(range(len(reserve_wheels)),key=lambda i:-reserve_wheels[i][0]*reserve_wheels[i][1])
                                    cells=[None]*len(reserve_wheels)
                                    for i in order:cells[i]=allocate(1,*reserve_wheels[i])[0]
                                    if reserve_rope:
                                        # Arresting-rope strip backups, one per display page.
                                        rope=allocate(2,128,2)
                                        if reserve_smoke:
                                            # Engine smoke pieces, largest first, in the remaining gaps.
                                            order=sorted(range(len(reserve_smoke)),key=lambda i:-reserve_smoke[i][0]*reserve_smoke[i][1])
                                            smoke=[None]*len(reserve_smoke)
                                            for i in order:smoke[i]=allocate(1,*reserve_smoke[i])[0]
                                            if reserve_rockets:
                                                # Rocket pieces, last of all: the static tile cells
                                                # the tile cache does not use come free for them (the
                                                # cache fills rows 180..243 of its columns,
                                                # src/msx/mission_streamer.c), so nothing above moves.
                                                cache=set()
                                                from convert_mission import TERRAIN_SLOTS
                                                for slot in range(TERRAIN_SLOTS):
                                                    sx,sy=slot%32*8,slot//32*256+180
                                                    cache.update((row,sx) for row in range(sy,sy+64))
                                                for tile in range(tiles):
                                                    x=tile%288//9*8;y=tile//288*256+180+tile%9*8
                                                    for row in range(y,y+8):
                                                        if (row,x) not in cache:occupied[row][x:x+8]=bytes(8)
                                                for px,py in PLANE_SLOTS:
                                                    for row in range(py-512,py-512+PLANE_SLOT_SIZE[1]):occupied[row][px:px+PLANE_SLOT_SIZE[0]]=bytes([1])*PLANE_SLOT_SIZE[0]
                                                for px,py in ARROW_SLOTS:
                                                    for row in range(py-512,py-512+ARROW_HEIGHT):occupied[row][px:px+16]=bytes([1])*16
                                                order=sorted(range(len(reserve_rockets)),key=lambda i:-reserve_rockets[i][0]*reserve_rockets[i][1])
                                                rockets=[None]*len(reserve_rockets)
                                                for i in order:rockets[i]=allocate(1,*reserve_rockets[i])[0]
                                                return slots,backups,ships,tails,weapons,crew,bombs,cells,rope,smoke,rockets
                                            return slots,backups,ships,tails,weapons,crew,bombs,cells,rope,smoke
                                        return slots,backups,ships,tails,weapons,crew,bombs,cells,rope
                                    return slots,backups,ships,tails,weapons,crew,bombs,cells
                                return slots,backups,ships,tails,weapons,crew,bombs
                            return slots,backups,ships,tails,allocate(36,8,8)
                        return slots,backups,ships,tails
                    return slots,backups
    raise ValueError('not enough pilot-view atlas rectangles')

def artifacts():
    image,metadata=original();files={}
    def png(path,im):
        output=BytesIO();im.save(output,format='PNG');files[ROOT/path]=output.getvalue()
    def indexed(path,pixels,width,height, dashboard=False):
        im=Image.frombytes('P',(width,height),bytes(pixels));p=dashboard_palette() if dashboard else (ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        im.putpalette(bytes(v*255//7 for i in range(16) for v in (p[i*2]>>4,p[i*2+1],p[i*2]&7))+bytes(720));png(path,im)
    png('assets_src/dashboard/original.png',image)
    indexed('assets_msx/dashboard/panel.png',panel(),256,40, dashboard=True)
    files[ROOT/'assets_msx/dashboard/palette.bin']=dashboard_palette()
    slots, water_backups, ship_slots, tails, weapon_backups, crew_slots, bomb_slots=atlas_slots(27, reserve_water=True, reserve_ship=True, reserve_combat=True, reserve_crew=True); profiles=convert_cockpit.art()[0]   # the cockpit window's shapes; slot 0 its compose buffer
    files[ROOT/'assets_msx/dashboard/pilot.indices']=b''.join(profiles)
    spots=layout(); arrows=arrow_frames()
    cockpit_c,cockpit_h,cockpit_bank=convert_cockpit.art_source(slots[:24],[('WINDOW_X',spots['pilot_x']),('WINDOW_Y',spots['pilot_y']),
        ('ARROW_HEIGHT',ARROW_HEIGHT),('ARROW_LEFT_X',arrows[0][1]),('ARROW_RIGHT_X',arrows[1][1])]+
        [(f'ARROW{i}_ATLAS_{a}',v) for i,(x,y) in enumerate(ARROW_SLOTS) for a,v in (('X',x),('Y',y))])
    files[ROOT/f'assets_msx/cockpit/bank_{convert_cockpit.COCKPIT_BANK}.bin']=cockpit_bank
    files[ROOT/'src/generated/cockpit_art.c']=cockpit_c.encode()
    files[ROOT/'src/generated/cockpit_art.h']=cockpit_h.encode()
    indexed('assets_msx/dashboard/pilot-sheet.png',b''.join(profiles),48,24*24, dashboard=True)
    water=waves();files[ROOT/'assets_msx/dashboard/waves.sc5']=b''.join(pack_pixels(w) for w in water)
    files[ROOT/'assets_msx/dashboard/waves.indices']=b''.join(water)
    indexed('assets_msx/dashboard/waves.png',b''.join(water),96,11*12)
    source_frames, ocean_palette = ocean_artwork()
    files[ROOT/'assets_src/dashboard/waves.indices']=b''.join(source_frames)
    files[ROOT/'assets_src/dashboard/ocean-palette.rgb']=bytes(ocean_palette)
    source_sheet=Image.frombytes('P',(96,132),b''.join(source_frames))
    source_sheet.putpalette(bytes((v>>4)*17 for v in ocean_palette)+bytes(672))
    source_sheet.info['transparency']=0
    png('assets_src/dashboard/waves-ocean.png',source_sheet)
    reduced={name:raw for name,_,raw in read_ppkc(unpack_rpck((SOURCE/'8thscale.shp').read_bytes()))}
    names=[name for name in reduced if name.startswith('lpn')]
    mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
    poses=[]; far_pixels=bytearray()
    for index,name in enumerate(names):
        raw=reduced[name]; pixels,meta=decode_record(raw,allow_reduced_flag=True,plane_constants=True)
        pixels=bytes(0 if v==0 else mapping[str(v)] for v in pixels)
        x,y=slots[24+index//12];x+=(index%3)*16;y+=(index%12//3)*5
        poses.append(dict(name=name,atlas_x=x,atlas_y=y,sha256=hashlib.sha256(raw).hexdigest(),**meta))
        far_pixels.extend(pixels+bytes(16*(5-meta['height'])))
    animation=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
    selected=['lpnn']*len(animation['frames'])
    table_start=(ROOT/'reference_assets/original_files/Wings_of_Fury/wings').read_bytes().find(b'lpn2lpn1lpn0')-160
    if table_start != 0x13ed4: raise ValueError('reduced aircraft table moved')
    exe=(ROOT/'reference_assets/original_files/Wings_of_Fury/wings').read_bytes()
    def slot_name(slot):return exe[table_start+slot*4:table_start+slot*4+4].decode()
    for bank,right in [('left_bank',False),('right_bank',True)]:
        source_names=animation['evidence']['source_tables'][bank]['names']
        for frame,meta in enumerate(animation['frames']):
            if meta['name'] not in source_names:continue
            phase=source_names.index(meta['name'])
            if phase==0:continue
            if phase<=8 or phase>=18:
                step=phase if phase<=8 else 26-phase
                slot=52+((step-1)//4)+(2 if right else 0)
            else:slot=phase+47+(9 if right != (phase>13) else 0)
            selected[frame]=slot_name(slot)
    for ids,labels in [(animation['pitch_right'],['lpnp','lpnp','lpno','lpno','lpnn','lpnq','lpnq','lpnr','lpnr','lpns']),
                       (animation['pitch_left'],['lpn2','lpn2','lpn1','lpn1','lpn0','lpn3','lpn3','lpn4','lpn4','lpn5'])]:
        for frame,name in zip(ids,labels): selected[frame]=name
    pose_ids=bytes(names.index(name) for name in selected)
    files[ROOT/'assets_msx/dashboard/far-plane.indices']=bytes(far_pixels)
    indexed('assets_msx/dashboard/far-poses.png',far_pixels,16,5*len(poses))
    code='/* Generated by tools/convert_dashboard.py; do not edit. */\n#pragma once\n'
    code+=c_array('g_DashboardPalette',dashboard_palette(),'[32]')
    bundle=bytearray(); offsets={}
    arrows=arrow_frames()
    indexed('assets_msx/dashboard/arrows.png',b''.join(p for p,_ in arrows),16,ARROW_HEIGHT*2, dashboard=True)
    for name,data in [('DashboardPanel',pack_pixels(panel())),('FarPlaneRLE',pack_pixels(far_pixels)),('BombRLE',pack_pixels(bomb_pixels())),
                      ('ArrowRLE',b''.join(pack_pixels(p) for p,_ in arrows))]:
        offsets[name]=len(bundle); bundle.extend(rle(data))
        code+=f'#define {name.upper()}_OFFSET {offsets[name]}\n'
    code+='#define DASHBOARD_BANK 12\n'
    # Pre-rendered HUD rectangles (see hud_variants) in their own banks.
    elements=hud_variants(); hud_banks={}
    for e in elements:
        blob=hud_banks.setdefault(e['bank'],bytearray()); e['offset']=len(blob); blob.extend(e['data'])
    if max(e['width']//2*e['height'] for e in elements)>288: raise ValueError('HUD variant exceeds the runtime patch buffer')
    for bank,blob in hud_banks.items():
        if len(blob)>8192: raise ValueError(f'HUD variants exceed bank {bank}')
        files[ROOT/f'assets_msx/dashboard/bank_{bank}.bin']=bytes(blob)
    spots=layout()
    for index,e in enumerate(elements): code+=f"#define HUD_{e['name']} {index}\n"
    code+=f"#define HUD_ELEMENT_COUNT {len(elements)}\n"
    def table(ctype,name,values):
        return f"static const {ctype} {name}[] = {{{', '.join(str(v) for v in values)}}};\n"
    code+=table('unsigned char','g_HudBank',[e['bank'] for e in elements])
    code+=table('unsigned char','g_HudColumn',[e['x']//2 for e in elements])
    code+=table('unsigned char','g_HudRow',[e['y'] for e in elements])
    code+=table('unsigned char','g_HudBytes',[e['width']//2 for e in elements])
    code+=table('unsigned char','g_HudHeight',[e['height'] for e in elements])
    code+=table('unsigned short','g_HudOffset',[e['offset'] for e in elements])
    code+=table('unsigned short','g_HudSize',[e['width']//2*e['height'] for e in elements])
    glyph_rows=[sum(1<<(5-x) for x,bit in enumerate(row) if bit=='#') for glyph in digit_glyphs() for row in glyph]
    code+=table('unsigned char','g_HudDigitRows',glyph_rows)
    for key in ('pilot_x','pilot_y','score_x','score_y','kills_x','kills_y'):
        code+=f"#define HUD_{key.upper()} {spots[key]}\n"
    code+=f"#define HUD_PILOT_WIDTH {PILOT_WIDTH}\n#define HUD_SCORE_DIGITS {SCORE_DIGITS}\n"
    code+=f"#define HUD_KILL_ICONS_MAX {KILL_ICONS_MAX}\n"
    code+=f"#define HUD_ARROW_HEIGHT {ARROW_HEIGHT}\n#define HUD_ARROW_LEFT_X {arrows[0][1]}\n#define HUD_ARROW_RIGHT_X {arrows[1][1]}\n"
    code+="".join(f"#define HUD_ARROW{i}_ATLAS_X {x}\n#define HUD_ARROW{i}_ATLAS_Y {y}\n" for i,(x,y) in enumerate(ARROW_SLOTS))
    code+=f"#define HUD_NEEDLE_FULL {NEEDLE_FULL}\n#define HUD_NEEDLE_NEW_OIL {NEEDLE_NEW_OIL}\n"
    code+=f"#define HUD_BLACK {BLACK}\n#define HUD_WHITE {WHITE}\n"
    if len(bundle)>8192: raise ValueError('dashboard assets exceed bank 12')
    files[ROOT/'assets_msx/dashboard/bank_12.bin']=bytes(bundle)
    tables=bytearray();table_offsets={}
    table_header='/* Generated by tools/convert_dashboard.py; do not edit. */\n#pragma once\n'
    def table(name,kind,values):
        nonlocal table_header
        table_offsets[name]=len(tables)
        table_header+=f'#define {name} (({kind}*)(g_DashboardTables+{len(tables)}))\n'
        for value in values:tables.extend(struct.pack('<H' if kind=='unsigned short' else 'B',value))
    pivots=bomb_frames()[1]
    table('g_BombPivotX','unsigned char',[x for x,y in pivots])
    table('g_BombPivotY','unsigned char',[y for x,y in pivots])
    table_header+=f'#define BOMB_FRAMES {len(BOMB_NAMES)}\n#define BOMB_HEIGHT {BOMB_HEIGHT}\n'
    for name,slots0 in [('Bomb',bomb_slots),('Pilot',slots[:24]),('WaveTail',tails),('WaveBackdrop',water_backups),('WeaponBackup',weapon_backups)]:
        table('g_'+name+'X','unsigned char',[x for x,y in slots0])
        table('g_'+name+'Y','unsigned short',[y for x,y in slots0])
    code+=f"#define FAR_PLANE_COUNT {len(poses)}\n"
    table_offsets['g_FarShapes']=len(tables)
    table_header+=f'#define g_FarShapes ((AircraftShape*)(g_DashboardTables+{len(tables)}))\n'
    for p in poses:tables.extend(struct.pack('<HbbBBBH',0,-p['origin_candidate'][0],-p['origin_candidate'][1],16,p['height'],p['atlas_x'],p['atlas_y']))
    table('g_FarPoseForFrame','unsigned char',pose_ids)
    tables.extend(bytes((-len(tables))%64))
    table_header+=f'#define DASHBOARD_TABLE_BYTES {len(tables)}\nextern unsigned char g_DashboardTables[DASHBOARD_TABLE_BYTES];\n'
    files[ROOT/'src/generated/dashboard_tables.h']=table_header.encode()
    code+='unsigned char g_DashboardTables[DASHBOARD_TABLE_BYTES];\n'
    if len(tables)>8192:raise ValueError('dashboard tables exceed bank 7')
    code+=f'#define AIRCRAFT_TABLE_OFFSET {len(tables)}\n'
    table_offsets['g_AircraftShapes']=len(tables)
    for frame in animation['frames']:
        # Unused frames have no atlas slot: no size, so LoadShape skips them.
        size=(0,0) if frame.get('unused') else (frame['width'],frame['height'])
        tables.extend(struct.pack('<HbbBBBH',frame['data_offset'],frame['dx'],frame['dy'],*size,frame['atlas_x'],frame['atlas_y']))
    if len(tables)>8192:raise ValueError('dashboard tables exceed bank 7')
    files[ROOT/'assets_msx/dashboard/bank_7.bin']=bytes(tables)
    files[ROOT/'assets_msx/dashboard/bombs.indices']=bomb_pixels()
    indexed('assets_msx/dashboard/bombs.png',bomb_pixels(),8,BOMB_HEIGHT*len(BOMB_NAMES))
    files[ROOT/'src/generated/dashboard.h']=code.encode()
    records=[]
    for name,offset,raw in read_ppkc(unpack_rpck((SOURCE/'dash.shp').read_bytes())):
        _,meta=decode_record(raw)
        records.append(dict(name=name,offset=offset,sha256=hashlib.sha256(raw).hexdigest(),**meta))
    manifest=dict(records=records, source='reference_assets/original_files/Wings_of_Fury/shapes/iff-dash',source_sha256=hashlib.sha256((SOURCE/'iff-dash').read_bytes()).hexdigest(),**metadata,
        tables_bank=dict(bank=7,bytes=len(tables),offsets=table_offsets,sha256=hashlib.sha256(tables).hexdigest()),
        asset_bank=dict(bank=12,bytes=len(bundle),offsets=offsets,sha256=hashlib.sha256(bundle).hexdigest()),
        bomb_slots=bomb_slots,bomb_names=BOMB_NAMES,
        bomb_source='torpedo.shp',bomb_source_sha256=hashlib.sha256((SOURCE/'torpedo.shp').read_bytes()).hexdigest(),
        bomb_pivots=bomb_frames()[1],bomb_timing='original tumble: start bom3 (moving left) or bom9, one frame every 4 weapon ticks (2 original ticks)',pilot_slots=slots[:24],far_poses=poses,far_pose_for_frame=list(pose_ids),
        dashboard_palette='original iff-dash RGB4 quantized to RGB3; shared flight border/sea slots 0/1; dashboard blue relocated to 9',
        hud_layout=dict(layout(), removed_columns=sorted(PANEL_REMOVE), dropped_row=PANEL_DROP_ROW,
                        needles=list(NEEDLES), new_plane_needles=dict(oil=NEEDLE_NEW_OIL, fuel=NEEDLE_FULL),
                        elements=[{k:v for k,v in e.items() if k!='data'} | dict(sha256=hashlib.sha256(e['data']).hexdigest()) for e in elements]),
        wave_palette='original ocean.palette CMAP, nearest fit to five shared blue slots; source zero stays transparent',
        ocean_palette_sha256=hashlib.sha256((SOURCE/'ocean.palette').read_bytes()).hexdigest(),
        wave_source_sha256=hashlib.sha256(b''.join(source_frames)).hexdigest(),
        wave_source_to_msx=wave_mapping(), wave_backdrop_slots=water_backups, wave_tail_slots=tails, weapon_backups=weapon_backups,
        wave_names=['wav'+c for c in 'abcdefghijkl'],target=dict(width=256,height=40,visible_width=248),
        scope='original dashboard and perspective sprites; the pilot window shapes are scaled for the cockpit view (tools/convert_cockpit.py)')
    files[ROOT/'assets_src/dashboard/manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    return files

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    for path, data in artifacts().items():
        if args.check:
            if not path.exists() or path.read_bytes() != data: parser.error(f'stale dashboard: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
