"""Convert recovered aircraft poses and mapped turn frames to SCREEN 5 assets."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps
from map_aircraft import mapping

FRAMES = ('hc01', 'hc05', 'hc09')
WIDTH, HEIGHT = 48, 32


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


def animation_assets(source, destination, base_manifest):
    facts = mapping()
    original = {r['name']: r for r in json.loads((source / 'manifest.json').read_text())['records']}
    names = [f'hc{n:02x}' for n in range(1, 11)] + [f'hc{n:02x}' for n in range(0x22, 0x40)]
    names += [f'hc{n:02x}-left' for n in range(1, 11) if n != 5]
    names += ['hc40', 'hc41']  # Original right/left wheels-down side views.
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
    pitch_right = [index[f'hc{n:02x}'] for n in range(1, 11)]
    # Pages 2/3: reserve rows 180..211 for the clean scenery strip.
    ax, ay, shelf, page = 0, 0, 0, 2
    for record in (r for r in records if r['name'] not in ('hc21', 'hcoc','hc1b','hc1c','hc1d','hc1e','hc1f','hc1c-left','hc1d-left','hc1e-left','hc1f-left')):
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
    for record in (r for r in records if r['name'] not in ('hc21', 'hcoc','hc1b','hc1c','hc1d','hc1e','hc1f','hc1c-left','hc1d-left','hc1e-left','hc1f-left')):
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
    pitch_left = [index['hc28' if n == 5 else f'hc{n:02x}-left'] for n in range(1, 11)]
    taxi = [index[name] for name in ('hcoc','hc1f-left','hc1e-left','hc1d-left','hc1c-left','hc1b','hc1c','hc1d','hc1e','hc1f','hc21')]
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
extern const unsigned char g_TurnLeftToRight[AIRCRAFT_TURN_STEPS];
extern const unsigned char g_TurnRightToLeft[AIRCRAFT_TURN_STEPS];
"""
    code = '/* Generated by tools/convert_hellcat.py; do not edit. */\n#include "hellcat_frames.h"\n\n'
    # Palette bytes are generated by the legacy/reference conversion using the same source indices.
    palette_rgb3 = base_manifest['palette_rgb3']
    palette = bytes(v for r, g, b in palette_rgb3 for v in ((r << 4) | b, g))
    code += c_array('g_HellcatPalette', palette, '[32]') + '\n'
    for bank, offset in enumerate(range(0, len(pixels), 8192), 8):
        files[destination / f'mission_bank_{bank if bank < 11 else bank + 3}.bin'] = bytes(pixels[offset:offset + 8192])
    code += '#ifdef MISSION_TERRAIN\n' + '\n#define AIRCRAFT_DATA(offset) ((const unsigned char*)(offset))\n#else\n' + c_array('g_AircraftPixels', pixels, f'[{len(pixels)}]') + '\n#define AIRCRAFT_DATA(offset) (g_AircraftPixels + (offset))\n#endif\n'
    code += '#ifdef MISSION_TERRAIN\nAircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT];\n#else\nconst AircraftShape g_AircraftShapes[AIRCRAFT_SHAPE_COUNT] = {\n'
    code += ',\n'.join(f"    {{AIRCRAFT_DATA({r['data_offset']}), {r['dx']}, {r['dy']}, {r['width']}, {r['height']}, {r['atlas_x']}, {r['atlas_y']}}} /* {r['name']} */" for r in records) + '\n};\n#endif\n'
    for symbol, table in [('g_PitchRight', pitch_right), ('g_PitchLeft', pitch_left),
                          ('g_TurnLeftToRight', ltr), ('g_TurnRightToLeft', rtl),
                          ('g_GearFrame', [index['hc40'], index['hc41']]),
                          ('g_TailDownFrame', [index['hc21'], index['hcoc']]),
                          ('g_TaxiTurn', taxi)]:
        code += '\n' + c_array(symbol, table, f'[{len(table)}]')
    metadata = dict(taxi_cache=taxi_cache, taxi_turn=taxi, taxi_artwork='Original front/right gear-down poses; four left-quarter views explicitly reflected. Five increments per quarter selected for MSX; exact original playback/timing unverified.', frames=records, pixel_bytes=len(pixels), reference_pivot=[25, 16],
        placement='logical position + dx/dy; signed source drawing origins preserved; X packed on even byte boundary',
        gear_frames=[index['hc40'], index['hc41']], tail_down_frames=[index['hc21'], index['hcoc']], evidence=facts, pitch_right=pitch_right, pitch_left=pitch_left, left_to_right=ltr, right_to_left=rtl)
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
    files[generated / 'hellcat_frames.c'] = code.encode()
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
