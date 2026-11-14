"""Compile the source-backed static a.map adaptation into cached bitmap tiles."""
import argparse
import hashlib
from io import BytesIO
import itertools
import json
from pathlib import Path
import struct
from PIL import Image
from convert_hellcat import c_array, pack_pixels
from decode_mission import artifacts as mission_artifacts, reconstruct, ROOT
from extract_iff import iff_img



# Amiga 0x5710: static scenery heights by object class, minus map-word bits
# 11..13 (docs/research/amiga-fuel-oil.md). The carrier (ids 0x1f..0x27,
# 0x9f) and moving objects take their height from live object records; the
# port handles the deck in core/landing.c and has no ships yet, so they are 0.
STATIC_HEIGHT_CLASSES = ((6,), (7,), (8, 11), (3,), (4,), tuple(range(15, 31)))
STATIC_HEIGHTS = (36, 35, 35, 9, 13, 12)


def static_surface_height(raw_word):
    object_id = (raw_word >> 2) & 0x1ff
    for ids, height in zip(STATIC_HEIGHT_CLASSES, STATIC_HEIGHTS):
        if object_id in ids:
            return max(0, height - ((raw_word >> 11) & 7))
    return 0

def compile_scene(pixels, width, size, top=64, height=212):
    if size not in (8, 16) or width % size or len(pixels) != width * height:
        raise ValueError('invalid tile scene geometry')
    if not 0 <= top < height:
        raise ValueError('invalid tile band')
    rows = (height - top + size - 1) // size
    lookup, tiles, columns = {}, [], []
    for x in range(0, width, size):
        column = []
        for row in range(rows):
            indices = b''.join(pixels[y * width + x:y * width + x + size] if y < height else bytes(size)
                               for y in range(top + row * size, top + (row + 1) * size))
            packed = pack_pixels(indices)
            if packed not in lookup:
                lookup[packed] = len(tiles)
                tiles.append(packed)
            column.append(lookup[packed])
        columns.append(tuple(column))
    # 16-bit offsets address deduplicated column runs. Each run is count:u8,
    # tile:u16le; decoded row count determines the record's exact end.
    unique, payload, offsets = {}, bytearray(), []
    table_bytes = len(columns) * 2
    for column in columns:
        if column not in unique:
            unique[column] = table_bytes + len(payload)
            for tile, group in itertools.groupby(column):
                count = len(list(group))
                if count > 255:
                    raise ValueError('terrain run exceeds byte count')
                payload.extend(struct.pack('<BH', count, tile))
        offsets.append(unique[column])
    if table_bytes + len(payload) > 65535 or len(tiles) > 65535:
        raise ValueError('terrain exceeds 16-bit format limits')
    map_data = b''.join(struct.pack('<H', offset) for offset in offsets) + payload
    tile_data = b''.join(tiles)
    return tile_data, map_data, dict(size=size, tile_count=len(tiles), tile_bytes=len(tile_data),
        columns=len(columns), rows=rows, unique_columns=len(unique),
        dense_map_bytes=len(columns) * rows * 2, compressed_map_bytes=len(map_data),
        total_bytes=len(tile_data) + len(map_data))


def decode_column(data, column, columns, rows, tile_count):
    if not 0 <= column < columns or len(data) < columns * 2:
        raise ValueError('invalid terrain column/table')
    pos = struct.unpack_from('<H', data, column * 2)[0]
    if pos < columns * 2 or pos >= len(data):
        raise ValueError('terrain run offset outside payload')
    decoded = []
    while len(decoded) < rows:
        if pos + 3 > len(data):
            raise ValueError('truncated terrain column run')
        count, tile = struct.unpack_from('<BH', data, pos)
        pos += 3
        if not count or len(decoded) + count > rows or tile >= tile_count:
            raise ValueError('invalid terrain run/count/tile')
        decoded.extend([tile] * count)
    return decoded


def artifacts():
    evidence, mission, scene, source_pixels, inventory = mission_artifacts()
    palette_manifest = json.loads((ROOT / 'assets_msx/terrain/manifest.json').read_text())
    mapping = {int(i): value for i, value in palette_manifest['source_to_msx_index'].items()}
    palette = bytearray((ROOT / 'assets_msx/terrain/palette.bin').read_bytes())
    ocean_path = ROOT / 'reference_assets/original_files/Wings_of_Fury/shapes/ocean.palette'
    ocean_palette = iff_img(ocean_path)[0].getpalette()
    # The prototype's blue-gray aircraft ramp erased most ocean detail. Retain
    # the dark blues/foam, but reserve two distinct ocean body/crest tones.
    for slot, source in ((3,10),(4,8)):
        r,g,b = (round(v*7/240) for v in ocean_palette[source*3:source*3+3])
        palette[slot*2:slot*2+2] = bytes(((r<<4)|b,g))
    palette = bytes(palette)
    # Opaque source hulls can contain black; palette index zero is our sky key.
    mapping[0] = mapping[6]
    pixels = bytes(mapping[v] for v in source_pixels)
    far_source, far_scene = reconstruct(mission, evidence, reduced=True)
    far_pixels = bytes(mapping[v] for v in far_source)
    # Original distant-view sea fill uses ocean color 10. The reduced beach
    # artwork supplies a one-pixel foreground strip in sand color 17; preserve
    # it, including the two shore silhouettes, instead of flooding it with sea.
    far_pixels = bytes(value if i < far_scene['baseline']*far_scene['width'] or far_source[i] == 17 else 3
                       for i,value in enumerate(far_pixels))
    combined_width = scene['width'] + far_scene['width']
    combined = b''.join(pixels[y * scene['width']:(y + 1) * scene['width']] +
                        far_pixels[y * far_scene['width']:(y + 1) * far_scene['width']] for y in range(212))
    comparisons = []
    for size in (8, 16):
        _, _, stats = compile_scene(pixels, scene['width'], size)
        comparisons.append(stats)
    tiles, tile_map, selected = compile_scene(combined, combined_width, 8)
    if tiles[:32] != bytes(32):
        raise ValueError('renderer requires tile zero to be uniform sky')
    if selected['tile_count'] > 576:
        raise ValueError('mission tile dictionary exceeds cached lower atlas bands')
    bundle = tiles + tile_map
    if len(bundle) > 32768:
        raise ValueError('mission bundle exceeds 64 KiB cartridge data segments')
    # Keep enough of the 16 KiB RAM page for the ISR, stack and BIOS workspace.
    ram_budget = len(tile_map) + 2 * 32 * selected['rows'] * 2 + 2 * 32 * 2 + selected['rows'] * 2
    if ram_budget > 12000:
        raise ValueError('mission map/cache exceeds conservative static RAM budget')
    output = ROOT / 'assets_msx/mission_a'
    metadata = dict(source_map='reference_assets/original_files/Wings_of_Fury/maps/a.map',
        source_sha256=mission['sha256'], executable_sha256=evidence['executable_sha256'],
        source_width=mission['width'], width=scene['width'], height=212, top=64,
        far_sand_height=far_scene['sand_height'],far_sand_source_index=17,far_sand_msx_index=mapping[17],
        far_width=far_scene['width'], far_source_width=(mission['width'] + 7) // 8, far_column_offset=scene['width'] // 8,
        reset_x=mission['reset_x'], camera_max=mission['width'] - 256,
        scene_scope=scene['scope'], baseline=scene['baseline'], fill=scene['fill'],
        placed=scene['placed'], unresolved=scene['unresolved'], comparisons=comparisons,
        selected=selected, bundle_bytes=len(bundle), tile_map_offset=len(tiles),
        bundle_sha256=hashlib.sha256(bundle).hexdigest(), palette_sha256=hashlib.sha256(palette).hexdigest(),
        ocean_palette_sha256=hashlib.sha256(ocean_path.read_bytes()).hexdigest(),
        palette_rgb3=[(palette[i*2]>>4,palette[i*2+1],palette[i*2]&7) for i in range(16)],
        mapper_banks=list(range(4, 4 + (len(bundle) + 8191) // 8192)),
        vram=dict(first_page=2, first_row=180, tiles_per_row=32, tiles_per_page=288,
                  ordering='column-major groups of 9 tiles'),
        map_format='u16le column offsets, deduplicated count:u8/tile:u16le runs; exactly 19 tile rows',
        map_and_cache_ram_bytes=ram_budget)
    files = {output / 'tiles.sc5': tiles, output / 'map.bin': tile_map,
             output / 'scene.indices': pixels, output / 'far.indices': far_pixels, output / 'palette.bin': palette,
             output / 'manifest.json': (json.dumps(metadata, indent=2) + '\n').encode()}
    for bank, offset in enumerate(range(0, len(bundle), 8192), 4):
        files[output / f'bank_{bank}.bin'] = bundle[offset:offset + 8192]
    header = f'''/* Generated by tools/convert_mission.py; do not edit. */
#pragma once
#define TERRAIN_TILE_COUNT {selected['tile_count']}
#define TERRAIN_MAP_BYTES {len(tile_map)}
#define TERRAIN_MAP_OFFSET {len(tiles)}
#define TERRAIN_MAP_ROWS {selected['rows']}
#define TERRAIN_MAP_COLUMNS {selected['columns']}
#define TERRAIN_BUNDLE_BYTES {len(bundle)}
#define TERRAIN_FAR_COLUMN {scene['width'] // 8}
extern const unsigned char g_MissionTileX[TERRAIN_TILE_COUNT], g_MissionTileLimit[TERRAIN_TILE_COUNT];
extern const unsigned short g_MissionTileY[TERRAIN_TILE_COUNT];
extern const unsigned char g_TerrainPalette[32];
extern const unsigned char g_MissionTileColors[TERRAIN_TILE_COUNT];
'''
    files[ROOT / 'src/generated/mission_tiles.h'] = header.encode()
    colors = bytes(tile[0] >> 4 if tile == bytes([tile[0]]) * 32 and tile[0] >> 4 == tile[0] & 15 else 255
                   for tile in (tiles[i:i + 32] for i in range(0, len(tiles), 32)))
    files[ROOT / 'src/generated/mission_tiles.c'] = ('/* Generated by tools/convert_mission.py; do not edit. */\n#include "mission_tiles.h"\n' + c_array('g_TerrainPalette', palette, '[32]') + c_array('g_MissionTileColors', colors, '[TERRAIN_TILE_COUNT]')).encode()
    # Collision queries use every strip word, including entries without draw flags.
    # Preserve exactly the fields returned by the executable's 0x50f0 query.
    runs = []
    for cell in mission['cells']:
        word = cell['raw_word'] & 0x7ff
        if runs and runs[-1][1] == word:
            runs[-1][0] = cell['x'] + 8
        else:
            runs.append([cell['x'] + 8, word])
    heights = []
    for cell in mission['cells']:
        height = static_surface_height(cell['raw_word'])
        if heights and heights[-1][1] == height:
            heights[-1][0] = cell['x'] + 8
        else:
            heights.append([cell['x'] + 8, height])
    if not 0 < len(heights) <= 255:
        raise ValueError('mission height lookup exceeds the runtime index')
    if not 0 < len(runs) <= 255 or mission['width'] > 32767:
        raise ValueError('mission surface lookup exceeds runtime index/coordinate limits')
    water = scene['water_bands']
    surface_header = f'''/* Generated by tools/convert_mission.py; do not edit. */
#pragma once
#include <stdint.h>
#define MISSION_SURFACE_WIDTH {mission['width']}
#define MISSION_SURFACE_RUNS {len(runs)}
#define MISSION_WATER_REGIONS {len(water)}
typedef struct MissionWaterBand {{ uint16_t start, end; uint8_t row, height; }} MissionWaterBand;
extern const MissionWaterBand g_MissionWaterBands[MISSION_WATER_REGIONS];
typedef struct MissionSurfaceRun {{ uint16_t end, word; }} MissionSurfaceRun;
extern const MissionSurfaceRun g_MissionSurfaceRuns[MISSION_SURFACE_RUNS];
'''
    surface_data = ('/* Generated by tools/convert_mission.py; do not edit. */\n'
                    '#include "mission_surfaces.h"\n'
                    'const MissionSurfaceRun g_MissionSurfaceRuns[MISSION_SURFACE_RUNS] = {\n' +
                    ''.join(f'    {{{end}, {word}}},\n' for end, word in runs) + '};\n')
    # Static scenery heights (Amiga 0x5710) live in the banked landing module.
    files[ROOT / 'src/generated/mission_heights.h'] = (
        '/* Generated by tools/convert_mission.py; do not edit.\n'
        ' * Static scenery height above the sea in pixels (Amiga 0x5710); the carrier\n'
        ' * deck and moving objects are handled separately. Include only from\n'
        ' * core/landing.c (banked). */\n#pragma once\n'
        f'#define MISSION_HEIGHT_RUNS {len(heights)}\n'
        'static const uint16_t s_MissionHeightEnd[MISSION_HEIGHT_RUNS] = {' + ', '.join(str(e) for e, _ in heights) + '};\n'
        'static const uint8_t s_MissionHeight[MISSION_HEIGHT_RUNS] = {' + ', '.join(str(h) for _, h in heights) + '};\n').encode()
    surface_data += 'const MissionWaterBand g_MissionWaterBands[MISSION_WATER_REGIONS] = {\n' + ''.join(
        f"    {{{band['start']}, {band['end']}, {band['row']}, {band['height']}}},\n" for band in water) + '};\n'
    surface_data += 'uint8_t Mission_Surface(uint16_t x) {\n' + ''.join(f"    if (x < {run['end']}) return {run['surface']};\n" for run in mission['surface_runs']) + '    return 0;\n}\n'
    files[ROOT / 'src/generated/mission_surfaces.h'] = surface_header.encode()
    files[ROOT / 'src/generated/mission_surfaces.c'] = surface_data.encode()
    files[ROOT / 'src/generated/mission_tiles.c'] += (c_array('g_MissionTileX', bytes((t % 288 // 9) * 8 for t in range(selected['tile_count'])), '[TERRAIN_TILE_COUNT]') +
        c_array('g_MissionTileLimit', bytes(9 - t % 9 for t in range(selected['tile_count'])), '[TERRAIN_TILE_COUNT]') +
        'const unsigned short g_MissionTileY[TERRAIN_TILE_COUNT] = {' + ','.join(str(512 + 180 + t % 9 * 8 + t // 288 * 256) for t in range(selected['tile_count'])) + '};\n').encode()
    im = Image.frombytes('P', (scene['width'], 212), pixels)
    colors = bytes(v * 255 // 7 for c in metadata['palette_rgb3'] for v in c)
    im.putpalette(colors + bytes(768 - len(colors)))
    stream = BytesIO(); im.save(stream, format='PNG')
    files[output / 'scene.png'] = stream.getvalue()
    return files, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files, metadata = artifacts()
    for path, data in files.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                parser.error(f'missing or stale mission artifact: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps({key:metadata[key] for key in ['comparisons','bundle_bytes','map_and_cache_ram_bytes']}, indent=2))


if __name__ == '__main__':
    main()
