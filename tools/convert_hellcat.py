"""Convert recovered aircraft poses and mapped turn frames to SCREEN 5 assets."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps
from map_aircraft import mapping

FRAMES = ('hc01', 'hc05', 'hc09')
# Kept in the record list so shape numbers stay put, but given no atlas space:
# the wheel overlays (wh01..wh14) replaced these wheels-down views at runtime.
UNUSED_FRAMES = ('hc40', 'hc41')
AIR_TURN_LEFT = ('hc28 hc29 hc2a hc2b hc2c hc2d hc2e hc2f hc30 hc31 hc32 hc32 hc32 '
                 'hc3b hc3b hc3c hc3d hc3e hc3f hc2d hc2c hc2b hc2a hc29 hc28').split()
AIR_TURN_RIGHT = ('hc22 hc23 hc24 hc25 hc26 hc27 hc37 hc38 hc39 hc3a hc3b hc3b hc3b '
                  'hc32 hc32 hc33 hc34 hc35 hc36 hc27 hc26 hc25 hc24 hc23 hc22').split()
WIDTH, HEIGHT = 48, 32


# The aircraft pixel data, 8 KiB segments in ROM banks: 8..10, 14, then the
# free banks 4..6 (15 is the elevator). Also in mission-flight.js and
# world_flight.c (s_AircraftBank).
AIRCRAFT_BANKS = (8, 9, 10, 14, 4, 5, 6)


def aircraft_bank(segment):
    return AIRCRAFT_BANKS[segment]


def rgb3(value):
    return (value * 7 + 127) // 255


def pack_pixels(indices):
    if len(indices) % 2 or any(not 0 <= index <= 15 for index in indices):
        raise ValueError('SCREEN 5 requires pairs of 4-bit color indices')
    return bytes((a << 4) | b for a, b in zip(indices[::2], indices[1::2]))


def mirror_frame(packed):
    """Reflect pixels, including nibble order, within each 48-pixel row."""
    if len(packed) != WIDTH * HEIGHT // 2:
        raise ValueError('expected a complete fixed-size aircraft frame')
    return bytes(((value & 15) << 4) | (value >> 4)
                 for y in range(HEIGHT)
                 for value in reversed(packed[y * 24:(y + 1) * 24]))


def convert(paths):
    images, shared_palette, colors = [], None, set()
    for path in paths:
        with Image.open(path) as image:
            if image.mode != 'P' or image.width != WIDTH or not 0 < image.height <= HEIGHT:
                raise ValueError(f'{path}: expected indexed 48-pixel image, at most 32 rows')
            if image.info.get('transparency') != 0:
                raise ValueError(f'{path}: expected transparent index 0')
            palette = image.getpalette()[:96]
            if len(palette) != 96 or (shared_palette is not None and palette != shared_palette):
                raise ValueError('frames must share a 32-color source palette')
            shared_palette = palette
            indices = list(image.tobytes())
            colors.update(indices)
            images.append((path, image.size, indices))
    opaque = sorted(colors - {0})
    if len(opaque) > 11:
        raise ValueError('aircraft exceeds 11 opaque colors reserved by this prototype')
    mapping = {0: 0, **{index: i + 1 for i, index in enumerate(opaque)}}
    # Index zero resolves transparent source pixels to a solid sky background.
    palette_rgb = [(0, 170, 255)] + [tuple(shared_palette[i * 3:i * 3 + 3]) for i in opaque]
    palette_rgb += [(0, 0, 0)] * (16 - len(palette_rgb))
    palette_rgb[12:] = [(255, 204, 68), (34, 51, 85), (255, 255, 255), (0, 0, 0)]
    palette_3 = [tuple(rgb3(v) for v in color) for color in palette_rgb]
    palette_bytes = bytes(v for r, g, b in palette_3 for v in ((r << 4) | b, g))
    frames, records = [], []
    for path, size, indices in images:
        # Center on a fixed canvas; do not apply the unconfirmed source hotspots.
        top = (HEIGHT - size[1]) // 2
        canvas = [0] * (WIDTH * HEIGHT)
        canvas[top * WIDTH:(top + size[1]) * WIDTH] = [mapping[i] for i in indices]
        packed = pack_pixels(canvas)
        frames.append(packed)
        records.append(dict(name=path.stem, source=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            source_size=list(size), canvas_offset=[0, top], bytes=len(packed),
                            packed_sha256=hashlib.sha256(packed).hexdigest()))
    return frames, palette_bytes, dict(format='raw SCREEN 5 packed pixels, no BSAVE header', canvas=[WIDTH, HEIGHT], frames=records,
        source_index_to_msx_index=mapping, palette_rgb3=palette_3,
        quantization='round(component * 7 / 255); MSX bytes: red<<4|blue, green',
        transparency='index 0 flattened to sky; no mask/terrain compositing',
        placement='vertically centered padded canvas; original hotspots not applied')


def c_array(name, data, dimensions):
    rows = ['    ' + ', '.join(f'0x{v:02x}' for v in data[i:i + 16]) for i in range(0, len(data), 16)]
    return f'const unsigned char {name}{dimensions} = {{\n' + ',\n'.join(rows) + '\n};\n'


FLASH_SOURCE = Path('reference_assets/unpacked_shapes/hellcat')
FLASH_CORE = 11  # playfield white
# Hidden rows 212..251 of the display pages are full: aircraft background
# backups use x=0..47, water frames x=48..239 (page 0) and x=48..143 (page 1),
# other caches page 1 x=144..245, and carrier heave exposes rows 254/255.
# The free page-0 strip x=240..255 holds one streamed slot per flash variant.
FLASH_SLOTS = ((240, 212), (240, 224))
FLASH_SLOT_SIZE = (16, 12)


def gun_flash_assets(pixels):
    """Original per-pose cannon flash/tracer overlays from hellcat.shp.

    The executable's player renderer (file offset 0x0672 in the code hunk)
    draws shape (pitch pose - 5 + 0x43 or 0x57, +10 when facing left) while
    firing, alternating with the pattern [none, fa, none, fb]. Records are
    fa01..fa14 and fb01..fb14: poses 1..10 right, then poses 1..10 left.
    Order here: variant (fa, fb) * 20 + (left ? 10 : 0) + pose index 0..9.
    """
    from decode_shapes import decode_record
    root = Path(__file__).resolve().parents[1]
    mapping = {int(k): v for k, v in json.loads(
        (root / 'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index'].items()}
    records = []
    for slot, variant in enumerate('ab'):
        for number in range(1, 21):
            name = f'f{variant}{number:02x}'
            path = next((root / FLASH_SOURCE).glob(f'*_{name}.bin'))
            raw = path.read_bytes()
            indices, meta = decode_record(raw)
            width, height = meta['width'], meta['height']
            ox, oy = meta['origin_candidate']
            # The pale-yellow core (source 10, RGB3 7,7,3) ties between grey
            # and orange on colour distance; white is closest in brightness and
            # reads as the hot core. The 16-colour playfield has no yellow.
            colors = [0 if v == 0 else FLASH_CORE if v == 10 else mapping[v] for v in indices]
            opaque = [(i % width, i // width) for i, c in enumerate(colors) if c]
            x0, x1 = min(p[0] for p in opaque), max(p[0] for p in opaque) + 1
            y0, y1 = min(p[1] for p in opaque), max(p[1] for p in opaque) + 1
            crop_width = (x1 - x0 + 1) // 2 * 2
            crop = [colors[row * width + col] if col < width else 0
                    for row in range(y0, y1) for col in range(x0, x0 + crop_width)]
            packed = pack_pixels(crop)
            x, y = FLASH_SLOTS[slot]
            if crop_width > FLASH_SLOT_SIZE[0] or y1 - y0 > FLASH_SLOT_SIZE[1]:
                raise ValueError('gun flash exceeds its streamed VRAM slot')
            records.append(dict(name=name, source=str(FLASH_SOURCE / path.name),
                source_sha256=hashlib.sha256(raw).hexdigest(), drawing_origin=[ox, oy],
                dx=25 + x0 - ox, dy=16 + y0 - oy, width=crop_width, height=y1 - y0,
                atlas_x=x, atlas_y=y, data_offset=len(pixels), bytes=len(packed),
                packed_sha256=hashlib.sha256(packed).hexdigest()))
            pixels.extend(packed)
    return records


WHEEL_CELL = (6, 6)  # largest piece


def wheel_blobs(color_map):
    """The original landing-gear overlays wh01..wh14 split into small pieces.

    The player renderer (0x0550) draws the wheel shape for the plane's pose
    behind the plane (poses 1..10 right are wh01..wh0a, left wh0b..wh14) at
    a vertical offset that slides 0..5 as the gear goes up or down. Each
    sprite has about 20 pixels in two or three blobs; whole sprites (up to
    28x23) do not fit the full atlas, so each blob (at most 6x6) gets its own
    small rectangle.
    Returns one list of (blob pixels, origin-relative x, y, width, height)
    per sprite.
    """
    from decode_shapes import decode_record
    root = Path(__file__).resolve().parents[1]
    terrain = {int(k): v for k, v in json.loads(
        (root / 'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index'].items()}
    sprites = []
    for number in range(1, 21):
        name = f'wh{number:02x}'
        path = next((root / FLASH_SOURCE).glob(f'*_{name}.bin'))
        indices, meta = decode_record(path.read_bytes())
        width = meta['width']
        ox, oy = meta['origin_candidate']
        # Wheel greys follow the aircraft palette; the odd outline pixels the
        # playfield mapping (as the cannon flash does).
        colors = {(i % width, i // width): color_map.get(v, terrain[v]) for i, v in enumerate(indices) if v}
        colors = {k: v for k, v in colors.items() if v}
        pieces, todo = [], set(colors)
        while todo:
            stack = [todo.pop()]
            blob = set(stack)
            while stack:
                x, y = stack.pop()
                for q in ((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    if q in todo:
                        todo.remove(q); blob.add(q); stack.append(q)
            x0 = min(x for x, _ in blob)
            y0 = min(y for _, y in blob)
            w = max(x for x, _ in blob) - x0 + 1
            h = max(y for _, y in blob) - y0 + 1
            w += w & 1
            if w > WHEEL_CELL[0] or h > WHEEL_CELL[1]:
                raise ValueError(f'{name}: wheel piece exceeds its atlas cell')
            crop = [colors.get((x0 + c, y0 + r), 0) if (x0 + c, y0 + r) in blob else 0
                    for r in range(h) for c in range(w)]
            pieces.append((name, crop, x0 - ox, y0 - oy, w, h))
        pieces.sort(key=lambda piece: (piece[3], piece[2]))
        sprites.append(pieces)
    return sprites


def wheel_assets(pixels, color_map, frames):
    """Pack the wheel pieces into leftover atlas gaps (identical pieces shared)."""
    from convert_dashboard import atlas_slots
    sprites = wheel_blobs(color_map)
    unique = {}
    for pieces in sprites:
        for name, crop, rx, ry, w, h in pieces:
            unique.setdefault((w, h, bytes(crop)), len(unique))
    keys = sorted(unique, key=unique.get)
    *_, cells, rope = atlas_slots(27, True, True, True, True, frames=frames,
                                  reserve_wheels=[(w, h) for w, h, _ in keys], reserve_rope=True)
    stored = {}
    for key, (x, y) in zip(keys, cells):
        packed = pack_pixels(list(key[2]))
        stored[key] = dict(atlas_x=x, atlas_y=y, data_offset=len(pixels), bytes=len(packed),
                           packed_sha256=hashlib.sha256(packed).hexdigest())
        pixels.extend(packed)
    records, first = [], []
    for pieces in sprites:
        first.append(len(records))
        for name, crop, rx, ry, w, h in pieces:
            records.append(dict(name=name, dx=25 + rx, dy=16 + ry, width=w, height=h, **stored[(w, h, bytes(crop))]))
    first.append(len(records))
    return records, first, [list(c) for c in cells], [list(r) for r in rope], [(w, h) for w, h, _ in keys]


SMOKE_NEAR = ('smk0', 'smk1', 'smk2', 'smk3', 'smk4')
SMOKE_FAR = ('smk0', 'smk1')
# Frames drawn through the smoke path after those seven: the hit spark smk5
# (effect type 6, 0x54e0), the dugout barrels gun0..gun6 and their muzzle
# flashes gnf0..gnf6 (shapes 0x81..0x8e, 0x4d50), and the distant view's
# ground-fire flash, 8thscale expl (shape 0x5a).
SMOKE_EXTRA_NEAR = ('smk5',) + tuple(f'gun{n}' for n in range(7)) + tuple(f'gnf{n}' for n in range(7))
SMOKE_EXTRA_FAR = ('expl',)
# Island soldiers (0x3eee): world.shp shapes 0x6f.. guy0..guy8 facing right
# (walk 0..4, dying 5..7, corpse 8), guy9..guyf, gy10, gy11 facing left, and
# 8thscale guy0/guy1 for the distant view.
SOLDIER_NEAR = tuple(f'guy{c}' for c in '0123456789abcdef') + ('gy10', 'gy11')
SOLDIER_FAR = ('guy0', 'guy1')
# The island flag (0x3b52): waving flg0..flg2 while the island holds out,
# then POST, a bare pole. Drawn in the close view only.
FLAG_NEAR = ('flg0', 'flg1', 'flg2')   # the cloth only: the pole is in the scenery
# Rockets (0x0702): torpedo.shp shapes 0x4c + frame once lit (rc01..rc14,
# with its flame) and 0x74 + frame before ignition (ro01..ro14); frames 0..9
# face right from the steepest climb to the steepest dive, 10..19 face left.
# The distant view draws 8thscale shape 9, bumb.
ROCKET_LIT = tuple(f'rc{n:02x}' for n in range(1, 21))
ROCKET_UNLIT = tuple(f'ro{n:02x}' for n in range(1, 21))
ROCKET_FAR = ('bumb',)
# Shell splashes from ship guns (0x52b0/0x52f8): shape 0x67 + life, world.shp
# spl6 down to spl1 over the sea, ric0 on land; 8thscale spl1..spl3 in the
# distant view (its spl4..spl6 do not exist: those frames draw nothing).
SPLASH_NEAR = tuple(f'spl{n}' for n in range(1, 7)) + ('ric0',)
SPLASH_FAR = ('spl1', 'spl2', 'spl3')
# The falling torpedo (0x0726): torpedo.shp tor2 (0x88) facing right, tor7
# (0x89) facing left; the distant view draws bumb, as for rockets. A running
# torpedo is not drawn (only its wake).
TORPEDO_FALL = ('tor2', 'tor7')
# Enemy planes (docs/research/amiga-enemy-planes.md, 0xd35a/0x0e1a):
# japplane.shp jp10..jp1f (the turn sequence's 16 views), jt10/jt1a (the
# armed torpedo plane), jc10/jc1a (the wreck), the muzzle flashes fc10,
# fd10 (facing right) and fc1a, fd1a (left); 8thscale zpn* far off. The
# near list's order is the frame number from SMOKE_FRAME_PLANE; the far
# list's from SMOKE_FRAME_FAR_PLANE (PLANE_FAR_FOR maps the near views).
PLANE_NEAR = tuple(f'jp1{c}' for c in '0123456789abcdef') + ('jt10', 'jt1a', 'jc10', 'jc1a', 'jp21', 'jp22',
                                                             'fc10', 'fd10', 'fc1a', 'fd1a')
# The first 20 near frames stream from ROM into a frame slot as a plane
# shows them (convert_dashboard.PLANE_SLOTS); they take no atlas cell.
PLANE_STREAMED = 22
PLANE_FAR = ('zpnn', 'zpn8', 'zpn9', 'zpng', 'zpnh', 'zpni', 'zpne', 'zpnf', 'zpn0', 'zpn6', 'zpn7', 'zpnb', 'zpnc', 'zpnd', 'zpnj', 'zpnk')
LATE_FRAMES = ROCKET_LIT + ROCKET_UNLIT + ROCKET_FAR + SPLASH_NEAR + SPLASH_FAR + TORPEDO_FALL + PLANE_NEAR + PLANE_FAR
SMOKE_FRAME_COUNT = (len(SMOKE_NEAR) + len(SMOKE_FAR) + len(SMOKE_EXTRA_NEAR) + len(SMOKE_EXTRA_FAR)
                     + len(SOLDIER_NEAR) + len(SOLDIER_FAR) + len(FLAG_NEAR) + len(LATE_FRAMES))


def smoke_assets(pixels, color_map, frames, wheel_sizes):
    """The original engine smoke: world.shp smk0..smk4 (near view) and
    8thscale.shp smk0/smk1 (far view), drawn at shape 0x60 + puff stage
    (0x0ee0; the executable's world shape table maps 0x61..0x65 to
    smk0..smk4). Frames that do not fit a leftover atlas gap whole are split
    into row bands. Returns pieces (offsets from the puff's origin) and the
    first piece of each frame: near stages 1..5, then far 1..2."""
    from convert_dashboard import atlas_slots
    from decode_shapes import decode_record
    from unpack_shapes import read_ppkc, unpack_rpck
    root = Path(__file__).resolve().parents[1]
    shapes = root / 'reference_assets/original_files/Wings_of_Fury/shapes'
    world = {n: r for n, _, r in read_ppkc(unpack_rpck((shapes / 'world.shp').read_bytes()))}
    reduced = {n: r for n, _, r in read_ppkc(unpack_rpck((shapes / '8thscale.shp').read_bytes()))}
    torpedo = {n: r for n, _, r in read_ppkc(unpack_rpck((shapes / 'torpedo.shp').read_bytes()))}
    japplane = {n: r for n, _, r in read_ppkc(unpack_rpck((shapes / 'japplane.shp').read_bytes()))}
    # The sprite colours (16..31) map as the aircraft's; the playfield colours
    # some new frames use (fire, flash, barrel outline) as the terrain's.
    terrain = json.loads((root / 'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
    color_map = {**{int(k): v for k, v in terrain.items()}, **color_map}
    images = []
    near, far = dict(plane_constants=True), dict(allow_reduced_flag=True, plane_constants=True)
    for records, names, options in ((world, SMOKE_NEAR, near), (reduced, SMOKE_FAR, far),
                                    (world, SMOKE_EXTRA_NEAR, near), (reduced, SMOKE_EXTRA_FAR, far),
                                    (world, SOLDIER_NEAR, near), (reduced, SOLDIER_FAR, far),
                                    (world, FLAG_NEAR, near), (torpedo, ROCKET_LIT, near),
                                    (torpedo, ROCKET_UNLIT, near), (reduced, ROCKET_FAR, far),
                                    (world, SPLASH_NEAR, near), (reduced, SPLASH_FAR, far),
                                    (torpedo, TORPEDO_FALL, near), (japplane, PLANE_NEAR, near),
                                    (reduced, PLANE_FAR, far)):
        for name in names:
            indices, meta = decode_record(records[name], **options)
            width = meta['width']
            ox, oy = meta['origin_candidate']
            colors = {(i % width, i // width): color_map[v] for i, v in enumerate(indices) if v}
            if name in FLAG_NEAR:   # leave the pole (columns 2..3) to the scenery
                colors = {(x, y): c for (x, y), c in colors.items() if x >= 4}
            x0, y0 = min(x for x, _ in colors), min(y for _, y in colors)
            x1, y1 = max(x for x, _ in colors) + 1, max(y for _, y in colors) + 1
            images.append((name, colors, x0, y0, (x1 - x0 + 1) // 2 * 2, y1 - y0, ox, oy,
                           hashlib.sha256(records[name]).hexdigest()))
    # Pieces: (frame, row offset, height); split the largest until all fit.
    # The rockets come last, in the cells the tile cache freed (atlas_slots),
    # so the other frames keep their places.
    rocket_first = SMOKE_FRAME_COUNT - len(LATE_FRAMES)
    def split(pieces):
        big = max(range(len(pieces)), key=lambda i: images[pieces[i][0]][4] * pieces[i][2])
        f, top, h = pieces[big]
        if h < 2:
            raise ValueError('smoke frames exceed the atlas gaps')
        pieces[big:big + 1] = [(f, top, h // 2), (f, top + h // 2, h - h // 2)]
    # The muzzle flashes (gnf0..gnf6, frames 15..21) go late too: squeezed
    # into the first pass's gaps they split into up to 8 one-row pieces, a
    # VDP command each, on every flashing barrel.
    plane_first = SMOKE_FRAME_COUNT - len(PLANE_FAR) - len(PLANE_NEAR)
    streamed = set(range(plane_first, plane_first + PLANE_STREAMED))
    late = (set(range(15, 22)) | set(range(rocket_first, len(images)))) - streamed
    pieces = [(f, 0, img[5]) for f, img in enumerate(images) if f not in late and f not in streamed]
    while True:
        sizes = [(images[f][4], h) for f, _, h in pieces]
        try:
            *_, smoke = atlas_slots(27, True, True, True, True, frames=frames,
                                    reserve_wheels=wheel_sizes, reserve_rope=True, reserve_smoke=sizes)
            break
        except ValueError:
            split(pieces)
    rocket = [(f, 0, images[f][5]) for f in sorted(late)]
    while True:
        try:
            *_, rocket_cells = atlas_slots(27, True, True, True, True, frames=frames,
                                           reserve_wheels=wheel_sizes, reserve_rope=True, reserve_smoke=sizes,
                                           reserve_rockets=[(images[f][4], h) for f, _, h in rocket])
            break
        except ValueError:
            split(rocket)
    pieces += rocket; smoke = list(smoke) + list(rocket_cells)
    records, first = [], []
    for f, img in enumerate(images):
        first.append(len(records))
        name, colors, x0, y0, w, _, ox, oy, sha = img
        for (pf, top, h), (ax, ay) in zip(pieces, smoke):
            if pf != f:
                continue
            crop = [colors.get((x0 + c, y0 + top + r), 0) for r in range(h) for c in range(w)]
            packed = pack_pixels(crop)
            records.append(dict(name=name, source_sha256=sha, dx=x0 - ox, dy=y0 + top - oy, width=w, height=h,
                                atlas_x=ax, atlas_y=ay, data_offset=len(pixels), bytes=len(packed),
                                packed_sha256=hashlib.sha256(packed).hexdigest()))
            pixels.extend(packed)
    first.append(len(records))
    # The streamed plane frames: whole, in ROM only.
    from convert_dashboard import PLANE_SLOT_SIZE
    planes = []
    for f in sorted(streamed):
        name, colors, x0, y0, w, h, ox, oy, sha = images[f]
        if w > PLANE_SLOT_SIZE[0] or h > PLANE_SLOT_SIZE[1]:
            raise ValueError(f'{name} ({w} x {h}) exceeds a plane frame slot')
        packed = pack_pixels([colors.get((x0 + c, y0 + r), 0) for r in range(h) for c in range(w)])
        planes.append(dict(name=name, source_sha256=sha, dx=x0 - ox, dy=y0 - oy, width=w, height=h,
                           atlas_x=0, atlas_y=0, data_offset=len(pixels), bytes=len(packed),
                           packed_sha256=hashlib.sha256(packed).hexdigest()))
        pixels.extend(packed)
    # Whole-frame box (dx, dy, width, height) for erasing a puff.
    boxes = []
    for f in range(len(images)):
        if f in streamed:
            r = planes[f - plane_first]
            boxes += [r['dx'], r['dy'], r['width'], r['height']]
            continue
        part = records[first[f]:first[f + 1]]
        x0 = min(r['dx'] for r in part); y0 = min(r['dy'] for r in part)
        boxes += [x0, y0, max(r['dx'] + r['width'] for r in part) - x0, max(r['dy'] + r['height'] for r in part) - y0]
    if len(images) != 141: raise ValueError('smoke frame numbering changed')
    return records, first, boxes, planes


CRASH_SOURCE = Path('reference_assets/unpacked_shapes/hellcat')
# The wreck (mode 8, 0xc7c6): hcr5 facing right, hcrf facing left
# (docs/research/amiga-player-crash.md).
CRASH_WRECK = ('hcr5', 'hcrf')


def crash_assets(pixels, frames):
    """The player's wreck (hellcat.shp hcr5 / hcrf), drawn instead of the plane.

    The burning wreck replaces the plane, so its frame streams into the atlas
    rectangle of one large static aircraft frame (the host); the runtime
    reloads the host when the next plane launches. Positions use the same
    object point as the aircraft: origin (25, 8) or (23, 8) at the plane's.
    The crash's explosions and splashes are ordinary bursts (weapons art).
    """
    from decode_shapes import decode_record
    root = Path(__file__).resolve().parents[1]
    mapping = {int(k): v for k, v in json.loads(
        (root / 'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index'].items()}
    decoded = []
    for name in CRASH_WRECK:
        path = next((root / CRASH_SOURCE).glob(f'*_{name}.bin'))
        raw = path.read_bytes()
        indices, meta = decode_record(raw)
        decoded.append((name, path, raw, indices, meta))
    def inked(indices, meta):
        width = meta['width']
        opaque = [(i % width, i // width) for i, v in enumerate(indices) if v]
        x0, x1 = min(p[0] for p in opaque), max(p[0] for p in opaque) + 1
        y0, y1 = min(p[1] for p in opaque), max(p[1] for p in opaque) + 1
        return (x1 - x0 + 1) // 2 * 2, y1 - y0
    need_w = max(inked(i, m)[0] for _, _, _, i, m in decoded)
    need_h = max(inked(i, m)[1] for _, _, _, i, m in decoded)
    hosts = [(i, f) for i, f in enumerate(frames[:53]) if not f.get('streamed') and not f.get('unused')]
    host_index, host = min(((i, f) for i, f in hosts if f['width'] >= need_w and f['height'] >= need_h),
                           key=lambda item: item[1]['width'] * item[1]['height'])
    records = []
    for name, path, raw, indices, meta in decoded:
        width, height = meta['width'], meta['height']
        ox, oy = meta['origin_candidate']
        colors = [0 if v == 0 else mapping[v] for v in indices]
        opaque = [(i % width, i // width) for i, c in enumerate(colors) if c]
        x0, x1 = min(p[0] for p in opaque), max(p[0] for p in opaque) + 1
        y0, y1 = min(p[1] for p in opaque), max(p[1] for p in opaque) + 1
        crop_width = (x1 - x0 + 1) // 2 * 2
        if crop_width > host['width'] or y1 - y0 > host['height']:
            raise ValueError('crash frame exceeds its host rectangle')
        crop = [colors[row * width + col] if col < width else 0
                for row in range(y0, y1) for col in range(x0, x0 + crop_width)]
        packed = pack_pixels(crop)
        records.append(dict(name=name, source=str(CRASH_SOURCE / path.name),
            source_sha256=hashlib.sha256(raw).hexdigest(), drawing_origin=[ox, oy],
            dx=25 + x0 - ox, dy=16 + y0 - oy, width=crop_width, height=y1 - y0,
            atlas_x=host['atlas_x'], atlas_y=host['atlas_y'], data_offset=len(pixels), bytes=len(packed),
            packed_sha256=hashlib.sha256(packed).hexdigest()))
        pixels.extend(packed)
    return records, host_index


def animation_assets(source, destination, base_manifest):
    facts = mapping()
    original = {r['name']: r for r in json.loads((source / 'manifest.json').read_text())['records']}
    names = [f'hc{n:02x}' for n in range(1, 11)] + [f'hc{n:02x}' for n in range(0x22, 0x40)]
    names += [f'hc{n:02x}-left' for n in range(1, 11) if n != 5]
    names += ['hc40', 'hc41']  # Original right/left wheels-down side views (unused: see UNUSED_FRAMES).
    names += ['hc21', 'hcoc']  # Tail-down resting / slow ground-roll poses.
    names += ['hc1b','hc1c','hc1d','hc1e','hc1f']
    names += ['hc1c-left','hc1d-left','hc1e-left','hc1f-left']
    index = {name: i for i, name in enumerate(names)}
    records, files, pixels = [], {}, bytearray()
    color_map = base_manifest['source_index_to_msx_index']
    with Image.open(source / 'hc05.png') as reference:
        source_palette = reference.getpalette()[:96]
    for key in names:
        mirrored = key.endswith('-left')
        name = key.removesuffix('-left')
        path = source / (name + '.png')
        with Image.open(path) as image:
            if image.mode != 'P' or image.info.get('transparency') != 0:
                raise ValueError('animation source must be indexed with transparent zero')
            if image.getpalette()[:96] != source_palette or not set(image.tobytes()) <= color_map.keys():
                raise ValueError('animation source requires a different shared palette')
            ox, oy = original[name]['origin_candidate']
            if mirrored:
                ox = image.width - ox
                image = ImageOps.mirror(image)
            box = image.getbbox()
            if not box:
                raise ValueError('empty aircraft frame')
            x0, y0, x1, y1 = box
            dx = (25 + x0 - ox) // 2 * 2
            right = (25 + x1 - ox + 1) // 2 * 2
            dy = 16 + y0 - oy
            width, height = right - dx, y1 - y0
            if not (-128 <= dx <= 127 and -128 <= dy <= 127 and 0 < width <= 64 and 0 < height <= 40):
                raise ValueError('animation frame exceeds renderer limits')
            crop_x = dx - 25 + ox
            crop = image.crop((crop_x, y0, crop_x + width, y1))
            packed = pack_pixels([color_map[v] for v in crop.tobytes()])
        # Bank 11 holds water, so avoid crossing the bank-10/bank-14 gap.
        if len(pixels) < 24576 < len(pixels)+len(packed):
            pixels.extend(bytes(24576-len(pixels)))
        filename = f'animation/{key}.sc5'
        files[destination / filename] = packed
        records.append(dict(id=index[key], name=key, source=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            mirrored=mirrored, drawing_origin=[ox, oy], crop_origin=[crop_x, y0], dx=dx, dy=dy,
            width=width, height=height, data_offset=len(pixels), bytes=len(packed),
            file=filename, packed_sha256=hashlib.sha256(packed).hexdigest()))
        pixels.extend(packed)
    for record in records:
        if record['name'] in UNUSED_FRAMES:
            record['unused'] = True
    pitch_right = [index[f'hc{n:02x}'] for n in range(1, 11)]
    # Pages 2/3: reserve rows 180..211 for the clean scenery strip.
    ax, ay, shelf, page = 0, 0, 0, 2
    for record in (r for r in records if r['name'] not in ('hc21', 'hcoc','hc1b','hc1c','hc1d','hc1e','hc1f','hc1c-left','hc1d-left','hc1e-left','hc1f-left')+UNUSED_FRAMES):
        if ax + record['width'] > 256:
            ax, ay, shelf = 0, ay + shelf, 0
        if ay + record['height'] > 180:
            page, ax, ay, shelf = page + 1, 0, 0, 0
        if page > 3:
            raise ValueError('aircraft atlas exceeds reserved VRAM')
        record['atlas_x'], record['atlas_y'] = ax, page * 256 + ay
        ax += record['width']
        shelf = max(shelf, record['height'])
    # Fill shelf gaps without displacing the shared cockpit/effects caches.
    # Starting another shelf would fragment the remaining cockpit atlas space.
    occupied=set()
    for record in (r for r in records if r['name'] not in ('hc21', 'hcoc','hc1b','hc1c','hc1d','hc1e','hc1f','hc1c-left','hc1d-left','hc1e-left','hc1f-left')+UNUSED_FRAMES):
        occupied.update((x,y) for y in range(record['atlas_y'],record['atlas_y']+record['height'])
                        for x in range(record['atlas_x'],record['atlas_x']+record['width']))
    for record in (r for r in records if r['name'] in ('hc21', 'hcoc')):
        found=False
        for page in (2,3):
            for y in range(page*256,page*256+181-record['height']):
                for x in range(0,257-record['width'],2):
                    area={(xx,yy) for yy in range(y,y+record['height']) for xx in range(x,x+record['width'])}
                    if occupied.isdisjoint(area):
                        record['atlas_x'],record['atlas_y']=x,y
                        occupied.update(area);found=True;break
                if found:break
            if found:break
        if not found:raise ValueError('resting aircraft frames exceed atlas gaps')
    # Only one ground-turn pose is displayed at once. Stream these poses into
    # the unused lower 18 rows of the third reduced-aircraft reservation.
    from convert_dashboard import atlas_slots
    slot=atlas_slots(27,frames=records[:53])[26]
    taxi_cache=dict(x=slot[0],y=slot[1]+6,width=46,height=15)
    for record in records[53:]:
        record['atlas_x'],record['atlas_y']=taxi_cache['x'],taxi_cache['y']
        record['streamed']=True
    flashes = gun_flash_assets(pixels)
    crashes, crash_host = crash_assets(pixels, records)
    wheels, wheel_first, wheel_cells, rope_backups, wheel_sizes = wheel_assets(pixels, color_map, records[:53])
    smoke, smoke_first, smoke_boxes, planes = smoke_assets(pixels, color_map, records[:53], wheel_sizes)
    pitch_left = [index['hc28' if n == 5 else f'hc{n:02x}-left'] for n in range(1, 11)]
    taxi = [index[name] for name in ('hcoc','hc1f-left','hc1e-left','hc1d-left','hc1c-left','hc1b','hc1c','hc1d','hc1e','hc1f','hc21')]
    # The original's air-turn shapes by turn frame 1..25 (DATA -$52ee facing
    # left, -$5286 facing right; frame 0 is not a turn and shows the level pose).
    # The heading flips at frame 14, so a turn plays frames 1..13 of one table
    # and 14..25 of the other.
    air_left = [index['hc28']] + [index[n] for n in AIR_TURN_LEFT]
    air_right = [index['hc05']] + [index[n] for n in AIR_TURN_RIGHT]
    ltr = [index[name] for name in facts['msx_transitions']['left_to_right']]
    rtl = [index[name] for name in facts['msx_transitions']['right_to_left']]
    header = f"""/* Generated by tools/convert_hellcat.py; do not edit. */
#pragma once
#define HELLCAT_WIDTH 48
#define HELLCAT_HEIGHT 32
#define AIRCRAFT_SHAPE_COUNT {len(records)}
#define AIRCRAFT_STATIC_SHAPES 53
#define AIRCRAFT_TURN_STEPS {len(ltr)}
typedef struct AircraftShape {{
    const unsigned char* data;
    signed char dx, dy;
    unsigned char width, height;
    unsigned char atlas_x;
    unsigned short atlas_y;
}} AircraftShape;
extern const unsigned char g_HellcatPalette[32];
#ifdef MISSION_TERRAIN
extern AircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT];
#else
extern const AircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT];
#endif
extern const unsigned char g_PitchRight[10], g_PitchLeft[10];
extern const unsigned char g_GearFrame[2], g_TailDownFrame[2];
extern const unsigned char g_TaxiTurn[11];
extern const unsigned char g_AirTurnLeft[26], g_AirTurnRight[26];
extern const unsigned char g_TurnLeftToRight[AIRCRAFT_TURN_STEPS];
extern const unsigned char g_TurnRightToLeft[AIRCRAFT_TURN_STEPS];
/* Original cannon flash/tracer overlays: variant * 20 + (left ? 10 : 0) + pitch.
 * Each variant streams into one VRAM slot (atlas_x/atlas_y) when its pose changes. */
#define GUN_FLASH_COUNT {len(flashes)}
#ifdef MISSION_TERRAIN
extern const AircraftShape g_GunFlash[GUN_FLASH_COUNT];
#endif
/* The player's wreck (hcr5 right, hcrf left), streamed into the atlas
 * rectangle of static shape CRASH_HOST_SHAPE while it is shown. */
#define CRASH_WRECK_RIGHT 0
#define CRASH_WRECK_LEFT 1
#define CRASH_HOST_SHAPE {crash_host}
#ifdef MISSION_TERRAIN
extern const AircraftShape g_CrashShapes[{len(crashes)}];
#endif
/* Original landing-gear overlays (wh01..wh14) as small static atlas pieces:
 * sprite = (left ? 10 : 0) + pitch pose 0..9; its pieces are
 * g_WheelPieces[g_WheelFirst[sprite] .. g_WheelFirst[sprite + 1]). Drawn
 * behind the plane, (5 - gear position) px higher while the gear moves. */
#define WHEEL_PIECE_COUNT {len(wheels)}
#ifdef MISSION_TERRAIN
extern const AircraftShape g_WheelPieces[WHEEL_PIECE_COUNT];
#endif
extern const unsigned char g_WheelFirst[21];
/* Hidden 128x2 strips (atlas pages 2/3) that save the playfield under the
 * arresting rope, one per display page. */
#define ROPE_BACKUP_WIDTH 128
#define ROPE_BACKUP0_X {rope_backups[0][0]}
#define ROPE_BACKUP0_Y {rope_backups[0][1]}
#define ROPE_BACKUP1_X {rope_backups[1][0]}
#define ROPE_BACKUP1_Y {rope_backups[1][1]}
/* Original smoke and ground-fire frames as atlas pieces, offsets from the
 * shape's origin: frame = stage - 1 (near smk0..smk4) or 5 + (far
 * smk0/smk1); then the hit spark smk5, barrels gun0..gun6, flashes
 * gnf0..gnf6, the far flash expl, the soldiers guy0..gy11 and the far
 * soldiers; pieces
 * g_SmokePieces[g_SmokeFirst[frame] .. g_SmokeFirst[frame + 1]). */
#define SMOKE_PIECE_COUNT {len(smoke)}
#define SMOKE_FRAME_FIRE 7
#define SMOKE_FRAME_GUN 8
#define SMOKE_FRAME_FAR_FLASH 22
#define SMOKE_FRAME_SOLDIER 23      /* guy0..: + 9 facing left */
#define SMOKE_FRAME_FAR_SOLDIER 41  /* 8thscale guy0, guy1 */
#define SMOKE_FRAME_FLAG 43         /* the flag's cloth, flg0..flg2 */
#define SMOKE_FRAME_ROCKET 46       /* lit rc01..rc14: + 10 facing left */
#define SMOKE_FRAME_ROCKET_UNLIT 66 /* before ignition, ro01..ro14 */
#define SMOKE_FRAME_FAR_ROCKET 86   /* 8thscale bumb */
#define SMOKE_FRAME_SPLASH 87       /* + life - 1: spl1..spl6 */
#define SMOKE_FRAME_RICOCHET 93     /* ric0 */
#define SMOKE_FRAME_FAR_SPLASH 94   /* + life - 1, lives 1..3: 8thscale spl1..spl3 */
#define SMOKE_FRAME_TORPEDO 97      /* falling: tor2, + 1 facing left (tor7) */
#define SMOKE_FRAME_PLANE 99        /* enemy planes: jp10..jp1f, jt10, jt1a, jc10, jc1a, jp21, jp22 (parked), fc10, fd10, fc1a, fd1a */
#define SMOKE_FRAME_FLASH 121       /* + 0..3: fc10, fd10 (facing right), fc1a, fd1a (left) */
#define SMOKE_FRAME_FAR_PLANE 125   /* 8thscale zpn*, in convert_hellcat.py PLANE_FAR's order */
#define PLANE_STREAMED_FRAMES 22    /* SMOKE_FRAME_PLANE.. (jp, jt, jc, parked): from ROM into a frame slot */
#define SMOKE_FRAME_COUNT {SMOKE_FRAME_COUNT}
/* In smoke_frames.c, banked (segment 22): use from that segment only. */
#ifdef MISSION_TERRAIN
extern const AircraftShape g_SmokePieces[SMOKE_PIECE_COUNT];
extern const unsigned char g_SmokeFirst[{SMOKE_FRAME_COUNT + 1}];
extern const signed char g_SmokeBox[{SMOKE_FRAME_COUNT * 4}];   /* per frame: dx, dy, width, height */
extern const AircraftShape g_PlaneFrames[PLANE_STREAMED_FRAMES];   /* in ROM; drawn through a frame slot */
#endif
"""
    code = '/* Generated by tools/convert_hellcat.py; do not edit. */\n#include "hellcat_frames.h"\n\n'
    # Palette bytes are generated by the legacy/reference conversion using the same source indices.
    palette_rgb3 = base_manifest['palette_rgb3']
    palette = bytes(v for r, g, b in palette_rgb3 for v in ((r << 4) | b, g))
    code += c_array('g_HellcatPalette', palette, '[32]') + '\n'
    if len(pixels) > 8192 * len(AIRCRAFT_BANKS):
        raise ValueError('aircraft pixels overflow the aircraft banks')
    for segment, offset in enumerate(range(0, len(pixels), 8192)):
        files[destination / f'mission_bank_{aircraft_bank(segment)}.bin'] = bytes(pixels[offset:offset + 8192])
    code += '#ifdef MISSION_TERRAIN\n' + '\n#define AIRCRAFT_DATA(offset) ((const unsigned char*)(offset))\n#else\n' + c_array('g_AircraftPixels', pixels, f'[{len(pixels)}]') + '\n#define AIRCRAFT_DATA(offset) (g_AircraftPixels + (offset))\n#endif\n'
    code += '#ifdef MISSION_TERRAIN\nAircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT];\n#else\nconst AircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT] = {\n'
    for r in records:
        if r.get('unused'):
            r['atlas_x'] = r['atlas_y'] = 0
    code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {0 if r.get('unused') else r['width']}, {0 if r.get('unused') else r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']}{' (unused)' if r.get('unused') else ''} */" for r in records) + '\n};\n#endif\n'
    code += '#ifdef MISSION_TERRAIN\nconst AircraftShape g_GunFlash[GUN_FLASH_COUNT] = {\n'
    code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']} */" for r in flashes) + '\n};\n#endif\n'
    code += f'#ifdef MISSION_TERRAIN\nconst AircraftShape g_CrashShapes[{len(crashes)}] = {{\n'
    code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']} */" for r in crashes) + '\n};\n#endif\n'
    code += f'#ifdef MISSION_TERRAIN\nconst AircraftShape g_WheelPieces[WHEEL_PIECE_COUNT] = {{\n'
    code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']} */" for r in wheels) + '\n};\n#endif\n'
    # The smoke-path tables go to their own module, linked into the effects
    # segment (22) with the code that uses them: resident space is short.
    smoke_code = ('/* Generated by tools/convert_hellcat.py; do not edit. */\n#include "hellcat_frames.h"\n'
                  '#include "../msx/banking.h"\nWINGS_CODE_SEGMENT(WINGS_SEGMENT_EFFECTS)\n'
                  '#ifdef MISSION_TERRAIN\n#define AIRCRAFT_DATA(offset) ((const unsigned char*)(offset))\n'
                  'const AircraftShape g_SmokePieces[SMOKE_PIECE_COUNT] = {\n')
    smoke_code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']} */" for r in smoke) + '\n};\n'
    smoke_code += f'const signed char g_SmokeBox[{SMOKE_FRAME_COUNT * 4}] = {{' + ', '.join(str(v) for v in smoke_boxes) + '};\n'
    erase_code = ('/* Generated by tools/convert_hellcat.py; do not edit.\n * The smoke path\'s box table again, in the erase\'s segment (msx/smoke_erase.c). */\n'
                  '#include "../msx/banking.h"\nWINGS_CODE_SEGMENT(WINGS_SEGMENT_PATCH)\n#ifdef MISSION_TERRAIN\n'
                  f'const signed char g_SmokeEraseBox[{SMOKE_FRAME_COUNT * 4}] = {{' + ', '.join(str(v) for v in smoke_boxes) + '};\n#endif\n')
    smoke_code += c_array('g_SmokeFirst', smoke_first, f'[{len(smoke_first)}]') + '\n'
    smoke_code += 'const AircraftShape g_PlaneFrames[PLANE_STREAMED_FRAMES] = {\n'
    smoke_code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, 0, 0}} /* {r['name']} */" for r in planes) + '\n};\n#endif\n'
    for symbol, table in [('g_WheelFirst', wheel_first), ('g_PitchRight', pitch_right), ('g_PitchLeft', pitch_left),
                          ('g_TurnLeftToRight', ltr), ('g_TurnRightToLeft', rtl),
                          ('g_GearFrame', [index['hc40'], index['hc41']]),
                          ('g_TailDownFrame', [index['hc21'], index['hcoc']]),
                          ('g_TaxiTurn', taxi),
                          ('g_AirTurnLeft', air_left), ('g_AirTurnRight', air_right)]:
        code += '\n' + c_array(symbol, table, f'[{len(table)}]')
    # Last: everything after the marker goes to smoke_frames.c (banked).
    code += '\n/*SMOKE_FRAMES*/' + smoke_code + '\n/*ERASE_BOX*/' + erase_code
    metadata = dict(taxi_cache=taxi_cache, taxi_turn=taxi, taxi_artwork='Original front/right gear-down poses; four left-quarter views explicitly reflected. Five increments per quarter selected for MSX; exact original playback/timing unverified.', frames=records, pixel_bytes=len(pixels), reference_pivot=[25, 16],
        placement='logical position + dx/dy; signed source drawing origins preserved; X packed on even byte boundary',
        gear_frames=[index['hc40'], index['hc41']], tail_down_frames=[index['hc21'], index['hcoc']], evidence=facts, pitch_right=pitch_right, pitch_left=pitch_left, left_to_right=ltr, right_to_left=rtl,
        wheels=wheels, wheel_first=wheel_first, wheel_cell=WHEEL_CELL, rope_backups=rope_backups,
        smoke=smoke, smoke_first=smoke_first, plane_frames=planes,
        gun_flash=flashes, gun_flash_slots=FLASH_SLOTS, gun_flash_slot_size=FLASH_SLOT_SIZE,
        crash=crashes, crash_host_shape=crash_host, crash_evidence='hellcat.shp hcr5 / hcrf: the mode-8 wreck (0xc7c6, docs/research/amiga-player-crash.md)',
        gun_flash_order='variant (fa, fb) * 20 + (left ? 10 : 0) + pitch pose 0..9',
        gun_flash_evidence='executable player renderer draws hellcat shape pose-5+0x43/0x57 (+10 left) while firing; pattern [0,1,0,2]')
    files[destination / 'animation/mapping.json'] = (json.dumps(facts, indent=2) + '\n').encode()
    return files, metadata, header, code


def artifacts(source, destination, generated):
    paths = [source / f'{name}.png' for name in FRAMES]
    frames, palette, manifest = convert(paths)
    # Wheels add source dark gray 25; fit it to the existing gray slot.
    manifest['source_index_to_msx_index'][25] = 6
    mirrored = [mirror_frame(frame) for frame in frames]
    files = {destination / f'{name}.sc5': data for name, data in zip(FRAMES, frames)}
    files.update({destination / f'{name}-left.sc5': data for name, data in zip(FRAMES, mirrored)})
    manifest['left_facing'] = dict(method='legacy reference reflections; runtime uses the animation frame metadata below',
        frames=[dict(name=name, file=f'{name}-left.sc5', packed_sha256=hashlib.sha256(data).hexdigest())
                for name, data in zip(FRAMES, mirrored)])
    files[destination / 'palette.bin'] = palette
    extra, animation, header, code = animation_assets(source, destination, manifest)
    files.update(extra)
    manifest['animation'] = animation
    files[destination / 'manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    files[generated / 'hellcat_frames.h'] = header.encode()
    code, smoke_code = code.split('\n/*SMOKE_FRAMES*/')
    smoke_code, erase_code = smoke_code.split('\n/*ERASE_BOX*/')
    files[generated / 'hellcat_frames.c'] = code.encode()
    files[generated / 'smoke_frames.c'] = smoke_code.encode()
    files[generated / 'smoke_erase_box.c'] = erase_code.encode()
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('assets_src/hellcat'))
    parser.add_argument('--output', type=Path, default=Path('assets_msx/hellcat'))
    parser.add_argument('--generated', type=Path, default=Path('src/generated'))
    parser.add_argument('--check', action='store_true', help='verify generated artifacts without writing')
    args = parser.parse_args()
    for path, data in artifacts(args.source, args.output, args.generated).items():
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                parser.error(f'generated artifact is missing or stale: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print('SCREEN 5 assets verified' if args.check else 'Generated cropped aircraft orientations, reference frames and a shared palette')


if __name__ == '__main__':
    main()
