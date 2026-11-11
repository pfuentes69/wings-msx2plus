"""Decode representative world shapes and compile an authored SCREEN 5 tile scene.

Original mission maps are not interpreted. Transparency zero and nonzero base
color OR behavior retain the decoder's documented hypotheses.
"""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from PIL import Image
from convert_hellcat import c_array, pack_pixels, rgb3
from decode_shapes import decode_record, make_sheet, read_palette
from unpack_shapes import read_ppkc, unpack_rpck

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('bchl', 'bchr', 'tre1', 'tre2', 'tre3', 'huta', 'hutb', 'dugo', 'wava')
WIDTH, HEIGHT, TOP = 4096, 212, 128


def tile_scene(pixels, size):
    if size not in (8, 16) or len(pixels) != WIDTH * HEIGHT:
        raise ValueError('expected 4096x212 pixels and 8/16-pixel tiles')
    tiles, lookup, columns = [], {}, []
    rows = (HEIGHT - TOP + size - 1) // size
    for x in range(0, WIDTH, size):
        column = []
        for row in range(rows):
            values = bytearray()
            for y in range(TOP + row * size, TOP + (row + 1) * size):
                values.extend(pixels[y * WIDTH + x:y * WIDTH + x + size] if y < HEIGHT else bytes(size))
            packed = pack_pixels(values)
            if packed not in lookup:
                lookup[packed] = len(tiles)
                tiles.append(packed)
            column.append(lookup[packed])
        columns.append(column)
    if len(tiles) > 256:
        raise ValueError('scene exceeds byte-sized tile IDs')
    map_data = bytes(index for column in columns for index in column)
    data = b''.join(tiles)
    return dict(size=size, rows=rows, columns=len(columns), tile_count=len(tiles),
                map_bytes=len(map_data), tile_bytes=len(data), total_bytes=len(map_data) + len(data)), data, map_data


def artifacts():
    archive = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes/world.shp'
    palette_path = archive.parent / 'wingspalette'
    raw, palette_raw = archive.read_bytes(), palette_path.read_bytes()
    source_palette = bytes((v >> 4) * 17 for v in read_palette(palette_raw))
    decoded, records, images = {}, [], []
    # Validate all records, but only export the inspected terrain subset.
    for name, offset, record in read_ppkc(unpack_rpck(raw)):
        pixels, meta = decode_record(record)
        if name not in NAMES:
            continue
        decoded[name] = (pixels, meta)
        im = Image.frombytes('P', (meta['width'], meta['height']), pixels)
        im.putpalette(source_palette + bytes(768 - len(source_palette)))
        im.info['transparency'] = 0
        images.append((name, im))
        records.append(dict(name=name, offset=offset, record_bytes=len(record),
                            record_sha256=hashlib.sha256(record).hexdigest(), **meta))
    if set(decoded) != set(NAMES):
        raise ValueError('terrain records are missing')
    scene = bytearray([1]) * (WIDTH * HEIGHT)
    scene[192 * WIDTH:] = bytes([19]) * (20 * WIDTH)
    placements = []

    def place(name, x, y):
        pixels, meta = decoded[name]
        placements.append(dict(name=name, x=x, y=y))
        for sy in range(meta['height']):
            for sx in range(meta['width']):
                dx, dy = x + sx, y + sy
                color = pixels[sy * meta['width'] + sx]
                if color and 0 <= dx < WIDTH and 0 <= dy < HEIGHT:
                    scene[dy * WIDTH + dx] = color

    islands = [(128, 608), (960, 1472), (1856, 2336), (2752, 3264), (3520, 3936)]
    for start, end in islands:
        for y in range(184, 198):
            scene[y * WIDTH + start + 32:y * WIDTH + end - 32] = bytes([14]) * (end - start - 64)
        for y in range(181, 184):
            scene[y * WIDTH + start + 32:y * WIDTH + end - 32] = bytes([7]) * (end - start - 64)
        place('bchl', start, 184)
        place('bchr', end - 32, 184)
        for name, anchor in [('tre1', start + 80), ('tre2', start + 128), ('tre3', end - 64),
                             ('huta', start + 208), ('hutb', start + 304), ('dugo', start + 368)]:
            ox, oy = decoded[name][1]['origin_candidate']
            place(name, anchor - ox, 184 - oy)
    for x in (0, 640, 1536, 2432, 3328, 3968):
        place('wava', x, 193)

    aircraft = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())
    palette3 = aircraft['palette_rgb3'][:12] + [[1,4,1], [4,2,0], [6,4,2], [0,2,0]]
    source3 = [tuple(rgb3(c) for c in source_palette[i * 3:i * 3 + 3]) for i in range(32)]
    mapping = {}
    for i, color in enumerate(source3):
        mapping[i] = min(range(16), key=lambda j: (sum((a-b)**2 for a,b in zip(color, palette3[j])), j))
    mapping[1] = mapping[24] = 0
    converted = bytes(mapping[v] for v in scene)
    comparisons = []
    for size in (8, 16):
        stats, _, _ = tile_scene(converted, size)
        comparisons.append(stats)
    stats, tile_data, map_data = tile_scene(converted, 16)
    if stats['tile_count'] > 128 or len(tile_data) + len(map_data) > 32768:
        raise ValueError('terrain exceeds reserved VRAM or 64 KiB mapper layout')
    if any(converted[y * WIDTH + x] != 0 for y in range(128, 144) for x in range(WIDTH)):
        raise ValueError('renderer expects uniform sky in rows 128..143')
    if any(converted[y * WIDTH + x] != 1 for y in range(208, 212) for x in range(WIDTH)):
        raise ValueError('renderer expects uniform ocean in rows 208..211')
    palette_bytes = bytes(v for r,g,b in palette3 for v in ((r << 4) | b, g))
    output = ROOT / 'assets_msx/terrain'
    files = {output / 'tiles.sc5': tile_data, output / 'map.bin': map_data,
             output / 'scene.indices': converted, output / 'palette.bin': palette_bytes}
    # Raw mapper banks 4 and later, read at 6000h during startup only.
    bundle = tile_data + map_data
    for bank, offset in enumerate(range(0, len(bundle), 8192), 4):
        files[output / f'bank_{bank}.bin'] = bundle[offset:offset + 8192]
    metadata = dict(source=str(archive.relative_to(ROOT)), source_sha256=hashlib.sha256(raw).hexdigest(),
        palette_source_sha256=hashlib.sha256(palette_raw).hexdigest(), records=records,
        placement='authored islands and object positions; not an original mission map',
        islands=islands, placements=placements, width=WIDTH, height=HEIGHT, top=TOP,
        transparency='source zero skipped when layering; selected records retain base-color OR hypothesis',
        source_to_msx_index=mapping, palette_rgb3=palette3,
        palette_conversion='nearest squared RGB3 distance; aircraft entries 0..11 unchanged',
        comparisons=comparisons, selected=stats, bundle_bytes=len(bundle),
        bundle_sha256=hashlib.sha256(bundle).hexdigest(), tile_map_offset=len(tile_data),
        vram=dict(first_page=2, first_row=180, rows_per_page=4, tiles_per_row=16),
        mapper_banks=list(range(4, 4 + (len(bundle) + 8191) // 8192)))
    files[output / 'manifest.json'] = (json.dumps(metadata, indent=2) + '\n').encode()
    header = f'''/* Generated by tools/convert_terrain.py; do not edit. */
#pragma once
#define TERRAIN_TILE_COUNT {stats['tile_count']}
#define TERRAIN_MAP_BYTES {len(map_data)}
#define TERRAIN_MAP_OFFSET {len(tile_data)}
#define TERRAIN_MAP_ROWS {stats['rows']}
#define TERRAIN_BUNDLE_BYTES {len(bundle)}
extern const unsigned char g_TerrainPalette[32];
'''
    files[ROOT / 'src/generated/terrain.h'] = header.encode()
    files[ROOT / 'src/generated/terrain.c'] = ('/* Generated by tools/convert_terrain.py; do not edit. */\n#include "terrain.h"\n' + c_array('g_TerrainPalette', palette_bytes, '[32]')).encode()
    source_meta = dict(source=metadata['source'], source_sha256=metadata['source_sha256'],
                       palette_source_sha256=metadata['palette_source_sha256'], records=records,
                       transparency=metadata['transparency'])
    files[ROOT / 'assets_src/world/manifest.json'] = (json.dumps(source_meta, indent=2) + '\n').encode()
    def png(image):
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        return buffer.getvalue()
    for name, image in images:
        files[ROOT / 'assets_src/world' / f'{name}.png'] = png(image)
    files[ROOT / 'assets_src/world/contact-sheet.png'] = png(make_sheet(images, columns=3, scale=3))
    for pixels, colors, filename in [(bytes(scene), source_palette, 'source-scene.png'),
                                     (converted, bytes(v * 255 // 7 for color in palette3 for v in color), 'msx-scene.png')]:
        image = Image.frombytes('P', (WIDTH, HEIGHT), pixels)
        image.putpalette(colors + bytes(768 - len(colors)))
        files[output / filename] = png(image)
    return files, images, bytes(scene), converted, source_palette, palette3, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, images, source, converted, palette, palette3, metadata = artifacts()
    if args.check:
        for path, data in files.items():
            if not path.is_file() or path.read_bytes() != data:
                parser.error(f'missing or stale generated artifact: {path}')
    else:
        for path, data in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps(dict(comparisons=metadata['comparisons'], selected=metadata['selected'],
                         bundle_bytes=metadata['bundle_bytes']), indent=2))


if __name__ == '__main__':
    main()
