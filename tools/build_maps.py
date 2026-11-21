#!/usr/bin/env python3
"""Pack the maps into the ROM's map records (docs/map-records.md).

Reads each map's converted tables (src/generated/map_<x>/*.h, *.c, from
tools/convert_mission.py and tools/convert_cockpit.py) and writes:

- src/generated/map_rom/: the ROM build's headers, under the same names as
  the per-map ones (mission_island.h...), which turn the tables into fields
  of g_Map, the map record in RAM (map_record.h);
- assets_msx/maps/record_<x>.bin: each map's record: the RAM part, then the
  tables that stay in ROM (the surface and height runs), read through
  window 3 by resident code;
- assets_msx/maps/maps.json: the banks of every map (its tile strips, its
  column map, its record), for mission-flight.js and the verifiers.

The host tests keep compiling one map's own headers; only the ROM reads
records.

  python3 tools/build_maps.py            # every converted map
  python3 tools/build_maps.py --check
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_mission import decode_column  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / 'src/generated'
OUT = ROOT / 'assets_msx/maps'
ROM_HEADERS = GENERATED / 'map_rom'
FIRST_BANK = 64          # the 1 MiB ROM's upper half
WINDOW3 = 0xA000
BANK = 8192
MAP_ORDER = 'abcdefghijklmno'   # map number = index (rank x 4 + mission)

# Capacities (every map converted so far, measured 2026-11-21, with room for
# h and m, which do not convert yet). Huts and dugouts: the island state's
# (core/island.h ISLAND_MAX_HUTS, _DUGOUTS), as the 20 soldiers; maps e..o
# need more (release plan phase 3).
ISLAND_GARRISON, ISLAND_MAX_SOLDIERS = 5, 20
MAX = dict(ISLANDS=4, HUTS=8, DUGOUTS=8, SHIPS=4, SHIP_GUNS=40, LISTS=4, PARKED_PLANES=16,
           WATER=28, BLOCKS=112, CLASS_RUNS=24, LANDS=6, TREES=16, OBJECTS=64)
# The same on every map: compile-time constants in the ROM build too.
FIXED = dict(TERRAIN_UNIFORM_COUNT=2, TERRAIN_MAP_ROWS=19, TERRAIN_SLOTS=40, TERRAIN_SINK_STAGES=15,
             PARKED_MAX=2)


def parse(folder):
    """{name: int or [ints]} from a map's generated tables."""
    text = '\n'.join(p.read_text() for p in sorted(folder.glob('*.[ch]')))
    art = (GENERATED / 'cockpit_art.h').read_text()
    symbols = {n: int(v) for n, v in re.findall(r'#define (COCKPIT_\w+) (\d+)', art)}
    values = {n: int(v) for n, v in re.findall(r'#define (\w+) (\d+)u?\b', text)}
    for name, body in re.findall(r'(?:static )?const (?:unsigned )?\w+ (\w+)\[[^\]]*\] = \{([^}]*)\};', text):
        items = [v.strip() for v in body.replace('\n', ' ').split(',') if v.strip()]
        values[name] = [symbols[v] if v in symbols else int(v, 0) for v in items]
    # Arrays of structs: one {..} per line.
    for name in ('g_MissionSurfaceRuns', 'g_MissionWaterBands'):
        body = re.search(rf'{name}\[\w+\] = \{{\n(.*?)\n\}};', text, re.S).group(1)
        values[name] = [tuple(int(v) for v in row.strip(' {},').split(',')) for row in body.splitlines()]
    # Mission_Surface: "if (x < end) return class;" or "return g_ShipsGone & bit ? 0 : 1;".
    runs = []
    for end, result in re.findall(r'if \(x < (\d+)\) return ([^;]+);', text):
        gone = re.match(r'g_ShipsGone & (\d+) \? 0 : 1', result)
        runs.append((int(end), 1 if gone else int(result), int(gone.group(1)) if gone else 0))
    values['class_runs'] = runs
    return values


def fields(v):
    """The record's RAM part: (name, C type, count or None, value). u16
    fields first so that every u16 is at an even offset (the host's layout
    is then SDCC's). Two bytes first: the banks, read by the Z80 code at
    _g_Map and _g_Map + 1."""
    n = lambda name, count: (v[name] + [0] * count)[:count] if name in v else [0] * count
    ships = v['SHIP_COUNT']
    out = [
        ('tile_bank', 'uint8_t', None, v['tile_bank']), ('map_bank', 'uint8_t', None, v['map_bank']),
        ('width', 'uint16_t', None, v['MISSION_SURFACE_WIDTH']), ('start', 'uint16_t', None, v['reset_x']),
        ('carrier_x', 'uint16_t', None, v['reset_x']),
        ('sea_column', 'uint16_t', None, v['sea_column']), ('far_sea_column', 'uint16_t', None, v['far_sea_column']),
        ('far_column', 'uint16_t', None, v['TERRAIN_FAR_COLUMN']), ('far_columns', 'uint16_t', None, v['TERRAIN_FAR_COLUMNS']),
        ('sink_table', 'uint16_t', None, v['TERRAIN_SINK_TABLE']),
        ('runs_at', 'uint16_t', None, v['runs_at']), ('heights_at', 'uint16_t', None, v['heights_at']),
        ('carrier_left', 'uint16_t', None, v['SHIP_CARRIER_LEFT']), ('carrier_right', 'uint16_t', None, v['SHIP_CARRIER_RIGHT']),
        ('parked_near_first', 'uint16_t', None, v['PARKED_NEAR_FIRST']), ('parked_far_first', 'uint16_t', None, v['PARKED_FAR_FIRST']),
        ('cockpit_reach', 'uint16_t', None, v['COCKPIT_OBJECT_REACH']),
        ('cockpit_carrier_first', 'uint16_t', None, v['COCKPIT_CARRIER_FIRST']),
        ('cockpit_carrier_last', 'uint16_t', None, v['COCKPIT_CARRIER_LAST']),
        ('hut_x', 'uint16_t', MAX['HUTS'], n('s_HutX', MAX['HUTS'])),
        ('hut_near_first', 'uint16_t', MAX['HUTS'], n('s_HutNearFirst', MAX['HUTS'])),
        ('hut_near_variant', 'uint16_t', MAX['HUTS'], n('s_HutNearVariant', MAX['HUTS'])),
        ('hut_far_first', 'uint16_t', MAX['HUTS'], n('s_HutFarFirst', MAX['HUTS'])),
        ('hut_far_variant', 'uint16_t', MAX['HUTS'], n('s_HutFarVariant', MAX['HUTS'])),
        ('dugout_x', 'uint16_t', MAX['DUGOUTS'], n('s_DugoutX', MAX['DUGOUTS'])),
        ('island_left', 'uint16_t', MAX['ISLANDS'], n('s_IslandLeft', MAX['ISLANDS'])),
        ('island_right', 'uint16_t', MAX['ISLANDS'], n('s_IslandRight', MAX['ISLANDS'])),
        ('island_bonus', 'uint16_t', MAX['ISLANDS'], n('s_IslandBonus', MAX['ISLANDS'])),
        ('island_flag_x', 'uint16_t', MAX['ISLANDS'], n('s_IslandFlagX', MAX['ISLANDS'])),
        ('parked_near', 'uint16_t', 2, n('s_ParkedNear', 2)), ('parked_far', 'uint16_t', 2, n('s_ParkedFar', 2)),
        ('ship_left', 'uint16_t', MAX['SHIPS'], n('s_ShipLeft', MAX['SHIPS'])),
        ('ship_right', 'uint16_t', MAX['SHIPS'], n('s_ShipRight', MAX['SHIPS'])),
        ('ship_bonus', 'uint16_t', MAX['SHIPS'], n('s_ShipBonus', MAX['SHIPS'])),
        ('ship_gun_x', 'uint16_t', MAX['SHIP_GUNS'], n('s_ShipGunX', MAX['SHIP_GUNS'])),
        ('ship_near_left', 'uint16_t', MAX['SHIPS'], n('s_ShipNearLeft', MAX['SHIPS'])),
        ('ship_near_right', 'uint16_t', MAX['SHIPS'], n('s_ShipNearRight', MAX['SHIPS'])),
        ('ship_sink_entry', 'uint16_t', MAX['SHIPS'], n('s_ShipSinkEntry', MAX['SHIPS'])),
        ('list_lo', 'int16_t', MAX['LISTS'], n('s_ListLo', MAX['LISTS'])),
        ('list_hi', 'int16_t', MAX['LISTS'], n('s_ListHi', MAX['LISTS'])),
        ('parked_x', 'int16_t', MAX['PARKED_PLANES'], n('s_ParkedX', MAX['PARKED_PLANES'])),
        ('parked_alt', 'int16_t', MAX['PARKED_PLANES'], n('s_ParkedAlt', MAX['PARKED_PLANES'])),
        ('class_end', 'uint16_t', MAX['CLASS_RUNS'], [r[0] for r in v['class_runs']] + [0] * (MAX['CLASS_RUNS'] - len(v['class_runs']))),
        ('land_first', 'uint16_t', MAX['LANDS'], n('s_LandFirst', MAX['LANDS'])),
        ('land_last', 'uint16_t', MAX['LANDS'], n('s_LandLast', MAX['LANDS'])),
        ('tree_first', 'uint16_t', MAX['TREES'], n('s_TreeFirst', MAX['TREES'])),
        ('tree_last', 'uint16_t', MAX['TREES'], n('s_TreeLast', MAX['TREES'])),
        ('object_first', 'uint16_t', MAX['OBJECTS'], n('s_ObjectFirst', MAX['OBJECTS'])),
        ('object_last', 'uint16_t', MAX['OBJECTS'], n('s_ObjectLast', MAX['OBJECTS'])),
        ('water', 'MissionWaterBand', MAX['WATER'], v['g_MissionWaterBands'] + [(0, 0, 0, 0)] * (MAX['WATER'] - len(v['g_MissionWaterBands']))),
        # bytes
        ('strips', 'uint8_t', None, v['TERRAIN_STRIPS']), ('blocks', 'uint8_t', None, v['TERRAIN_BLOCKS']),
        ('surface_runs', 'uint8_t', None, v['MISSION_SURFACE_RUNS']), ('height_runs', 'uint8_t', None, v['MISSION_HEIGHT_RUNS']),
        ('water_regions', 'uint8_t', None, v['MISSION_WATER_REGIONS']), ('class_count', 'uint8_t', None, len(v['class_runs'])),
        ('islands', 'uint8_t', None, v['ISLAND_COUNT']), ('huts', 'uint8_t', None, v['ISLAND_HUTS']),
        ('dugouts', 'uint8_t', None, v['ISLAND_DUGOUTS']), ('guns', 'uint8_t', None, v['ISLAND_GUNS']),
        ('parked_near_count', 'uint8_t', None, v['PARKED_NEAR_COUNT']), ('parked_far_count', 'uint8_t', None, v['PARKED_FAR_COUNT']),
        ('ships', 'uint8_t', None, ships), ('ship_guns', 'uint8_t', None, v['SHIP_GUNS']),
        ('ship_sinking', 'uint8_t', None, v['SHIP_SINKING']),
        ('plane_lists', 'uint8_t', None, v['PLANE_LISTS']), ('plane_parked', 'uint8_t', None, v['PLANE_PARKED']),
        ('cockpit_lands', 'uint8_t', None, v['COCKPIT_LANDS']), ('cockpit_trees', 'uint8_t', None, v['COCKPIT_TREES']),
        ('cockpit_objects', 'uint8_t', None, v['COCKPIT_OBJECTS']),
        ('palette', 'uint8_t', 32, v['g_TerrainPalette']),
        ('uniform_color', 'uint8_t', FIXED['TERRAIN_UNIFORM_COUNT'], v['g_TerrainUniformColor']),
        ('block_top', 'uint8_t', MAX['BLOCKS'], n('g_TerrainBlockTop', MAX['BLOCKS'])),
        ('class_surface', 'uint8_t', MAX['CLASS_RUNS'], [r[1] for r in v['class_runs']] + [0] * (MAX['CLASS_RUNS'] - len(v['class_runs']))),
        ('class_ship', 'uint8_t', MAX['CLASS_RUNS'], [r[2] for r in v['class_runs']] + [0] * (MAX['CLASS_RUNS'] - len(v['class_runs']))),
        ('hut_island', 'uint8_t', MAX['HUTS'], n('s_HutIsland', MAX['HUTS'])),
        ('hut_near_count', 'uint8_t', MAX['HUTS'], n('s_HutNearCount', MAX['HUTS'])),
        ('hut_far_count', 'uint8_t', MAX['HUTS'], n('s_HutFarCount', MAX['HUTS'])),
        ('dugout_island', 'uint8_t', MAX['DUGOUTS'], n('s_DugoutIsland', MAX['DUGOUTS'])),
        ('dugout_side', 'uint8_t', MAX['DUGOUTS'], n('s_DugoutSide', MAX['DUGOUTS'])),
        ('ship_kind', 'uint8_t', MAX['SHIPS'], n('s_ShipKind', MAX['SHIPS'])),
        ('ship_deck', 'uint8_t', MAX['SHIPS'], n('s_ShipDeck', MAX['SHIPS'])),
        ('ship_hits', 'uint8_t', MAX['SHIPS'], n('s_ShipHits', MAX['SHIPS'])),
        ('ship_first_gun', 'uint8_t', MAX['SHIPS'] + 1, n('s_ShipFirstGun', MAX['SHIPS'] + 1)),
        ('ship_gun_rise', 'uint8_t', MAX['SHIP_GUNS'], n('s_ShipGunRise', MAX['SHIP_GUNS'])),
        ('ship_sink_first', 'uint8_t', MAX['SHIPS'], n('s_ShipSinkFirst', MAX['SHIPS'])),
        ('ship_far_first', 'uint8_t', MAX['SHIPS'], n('s_ShipFarFirst', MAX['SHIPS'])),
        ('ship_far_count', 'uint8_t', MAX['SHIPS'], n('s_ShipFarCount', MAX['SHIPS'])),
        ('ship_view', 'uint8_t', MAX['SHIPS'], n('s_ShipView', MAX['SHIPS'])),
        ('list_ship', 'uint8_t', MAX['LISTS'], n('s_ListShip', MAX['LISTS'])),
        ('list_max', 'uint8_t', MAX['LISTS'], n('s_ListMax', MAX['LISTS'])),
        ('list_first', 'uint8_t', MAX['LISTS'] + 1, n('s_ListFirst', MAX['LISTS'] + 1)),
        ('parked_dir', 'int8_t', MAX['PARKED_PLANES'], n('s_ParkedDir', MAX['PARKED_PLANES'])),
        ('object_kind', 'uint8_t', MAX['OBJECTS'], n('s_ObjectKind', MAX['OBJECTS'])),
        ('object_index', 'uint8_t', MAX['OBJECTS'], n('s_ObjectIndex', MAX['OBJECTS'])),
    ]
    return out


FORMAT = {'uint8_t': 'B', 'int8_t': 'b', 'uint16_t': 'H', 'int16_t': 'h', 'MissionWaterBand': 'HHBB'}
SIZE = {k: struct.calcsize('<' + f) for k, f in FORMAT.items()}


def pack(record):
    data = bytearray()
    for name, kind, count, value in record:
        if SIZE[kind] > 1 and len(data) % 2:
            raise ValueError(f'{name}: u16 field at an odd offset')
        for item in ([value] if count is None else value):
            data += struct.pack('<' + FORMAT[kind], *(item if isinstance(item, tuple) else (item,)))
    if len(data) % 2: data += b'\0'
    return bytes(data)


def check(letter, v):
    for name, value in FIXED.items():
        if v.get(name, value) != value:
            raise ValueError(f'map {letter}: {name} is {v[name]}, not {value}')
    limits = dict(ISLAND_COUNT='ISLANDS', ISLAND_HUTS='HUTS', ISLAND_DUGOUTS='DUGOUTS', SHIP_COUNT='SHIPS',
                  SHIP_GUNS='SHIP_GUNS', PLANE_LISTS='LISTS', PLANE_PARKED='PARKED_PLANES',
                  MISSION_WATER_REGIONS='WATER', TERRAIN_BLOCKS='BLOCKS', COCKPIT_LANDS='LANDS',
                  COCKPIT_TREES='TREES', COCKPIT_OBJECTS='OBJECTS')
    for name, cap in limits.items():
        if v[name] > MAX[cap]:
            raise ValueError(f'map {letter}: {name} {v[name]} exceeds {cap} {MAX[cap]}')
    if ISLAND_GARRISON * (v['ISLAND_HUTS'] + v['ISLAND_DUGOUTS']) > ISLAND_MAX_SOLDIERS:
        raise ValueError(f'map {letter}: more than {ISLAND_MAX_SOLDIERS} soldiers')
    if len(v['class_runs']) > MAX['CLASS_RUNS']:
        raise ValueError(f'map {letter}: {len(v["class_runs"])} surface classes')
    if v['TERRAIN_STRIPS'] > 255 or v['MISSION_SURFACE_RUNS'] > 255 or v['MISSION_HEIGHT_RUNS'] > 255:
        raise ValueError(f'map {letter}: runs exceed a byte')


def sea_columns(letter, v, manifest):
    """Open-sea columns drawn beyond the map's ends (mission_streamer.c): the
    middle of the longest sea run, close (x / 8) and distant (x / 64, from
    TERRAIN_FAR_COLUMN); each must be plain sea, like its neighbours."""
    data = (ROOT / f'assets_msx/mission_{letter}/map.bin').read_bytes()
    selected = manifest['selected']
    decode = lambda c: decode_column(data, c, selected['columns'], selected['rows'], selected['tile_count'])
    best, start = (0, 0), 0
    for end, surface, ship in v['class_runs']:
        if surface == 0 and not ship and end - start > best[1] - best[0]: best = (start, end)
        start = end
    middle = sum(best) // 2
    near, far = middle // 8, middle // 64
    base = v['TERRAIN_FAR_COLUMN']
    if not decode(near) == decode(near - 8) == decode(near + 8) or \
            not decode(base + far) == decode(base + far - 2) == decode(base + far + 2):
        raise ValueError(f'map {letter}: no plain sea at x {middle}')
    return near, far


def banks(letter):
    """A packed map's first banks: dict(tiles=, column_map=, record=), from
    assets_msx/maps/maps.json (for the verifiers)."""
    for entry in json.loads((OUT / 'maps.json').read_text())['maps']:
        if entry['map'] == letter:
            return dict(tiles=entry['tiles'][0][0], column_map=entry['column_map'][0][0], record=entry['record'][0])
    raise KeyError(f'map {letter} is not packed (tools/build_maps.py)')


def maps_present():
    return [m for m in MAP_ORDER if (GENERATED / f'map_{m}/mission_tiles.h').exists()]


def build(letters):
    """{path: bytes} of every output."""
    files, table, bank = {}, [], FIRST_BANK
    layout = None
    for letter in letters:
        manifest = json.loads((ROOT / f'assets_msx/mission_{letter}/manifest.json').read_text())
        v = parse(GENERATED / f'map_{letter}')
        v['reset_x'] = manifest['reset_x']
        v['sea_column'], v['far_sea_column'] = sea_columns(letter, v, manifest)
        tiles = [(bank + i, f'assets_msx/mission_{letter}/bank_{b}.bin') for i, b in enumerate(manifest['tile_banks'])]
        bank += len(tiles)
        column_map = [(bank + i, f'assets_msx/mission_{letter}/bank_{b}.bin') for i, b in enumerate(manifest['map_banks'])]
        bank += len(column_map)
        v['tile_bank'], v['map_bank'], record_bank = tiles[0][0], column_map[0][0], bank
        bank += 1
        check(letter, v)
        # After the RAM part: the surface runs (end, word), then the height
        # runs' ends (u16) and heights (u8).
        ram_size = len(pack(fields(dict(v, runs_at=0, heights_at=0))))
        v['runs_at'] = WINDOW3 + ram_size
        v['heights_at'] = v['runs_at'] + 4 * v['MISSION_SURFACE_RUNS']
        rom = (b''.join(struct.pack('<HH', *r) for r in v['g_MissionSurfaceRuns'])
               + b''.join(struct.pack('<H', e) for e in v['s_MissionHeightEnd'])
               + bytes(v['s_MissionHeight']))
        record = fields(v)
        data = pack(record) + rom
        if len(data) > BANK:
            raise ValueError(f'map {letter}: record of {len(data)} bytes')
        layout = layout or record
        files[OUT / f'record_{letter}.bin'] = data
        table.append(dict(map=letter, number=MAP_ORDER.index(letter), tiles=tiles, column_map=column_map,
                          record=[record_bank, f'assets_msx/maps/record_{letter}.bin'], ram_bytes=ram_size,
                          record_bytes=len(data)))
    if bank > 128:
        raise ValueError(f'the maps reach bank {bank - 1}')
    files[OUT / 'maps.json'] = (json.dumps(dict(maps=table, first_bank=FIRST_BANK, last_bank=bank - 1), indent=1) + '\n').encode()
    files.update(headers(layout, table))
    return files


GEN = '/* Generated by tools/build_maps.py; do not edit. */\n'


def headers(record, table):
    """The ROM build's headers: the record type and the per-map names."""
    lines = [GEN + '/* The map record (docs/map-records.md): loaded into RAM by Map_Load from',
             ' * its ROM bank; the surface and height runs stay in the bank (window 3). */',
             '#pragma once', '#include <stdint.h>',
             '#ifndef WINGS_MAP_RECORD', '#error "the ROM build defines WINGS_MAP_RECORD (mission-flight.js)"', '#endif']
    lines += [f'#define MAP_{k}_MAX {v}' for k, v in MAX.items()]
    lines += [f'#define {k} {v}' for k, v in FIXED.items()]
    lines += ['/* Map numbers 0..14 (a..o) with a record in this ROM: its bank, else 0. */',
              f'#define MAP_COUNT {len(MAP_ORDER)}',
              'extern const uint8_t g_MapRecordBank[MAP_COUNT];',
              'typedef struct MissionWaterBand { uint16_t start, end; uint8_t row, height; } MissionWaterBand;',
              'typedef struct MissionSurfaceRun { uint16_t end, word; } MissionSurfaceRun;',
              'typedef struct MapRecord {']
    for name, kind, count, _ in record:
        lines.append(f'    {kind} {name}{"" if count is None else f"[{count}]"};')
    size = len(pack(record))
    lines += ['} MapRecord;', f'#define MAP_RECORD_BYTES {size}',
              '/* Field offsets, for Z80 code: _g_Map + MAP_AT_<FIELD>. */']
    at = 0
    for name, kind, count, _ in record:
        lines.append(f'#define MAP_AT_{name.upper()} {at}')
        at += SIZE[kind] * (1 if count is None else count)
    lines += [
              'typedef char MapRecordSize[sizeof(MapRecord) == MAP_RECORD_BYTES ? 1 : -1];',
              'extern MapRecord g_Map;', 'extern uint8_t g_MapNumber;',
              '/* Load map number n (its record must be in the ROM). Resident. */',
              'void Map_Load(uint8_t n);',
              '/* The u16 or u8 at a record address (window 3) in ROM. Resident. */',
              'uint16_t Map_Word(uint16_t at);', 'uint8_t Map_Byte(uint16_t at);', '']
    out = {ROM_HEADERS / 'map_record.h': '\n'.join(lines)}
    def header(name, body, extra_comment):
        return GEN + f'/* {extra_comment} */\n#pragma once\n#include "map_record.h"\n' + body
    out[ROM_HEADERS / 'mission_tiles.h'] = header('mission_tiles.h', '''\
/* Tile ids are below 2048 (Terrain_TileY); the cache's markers are 65534+. */
#define TERRAIN_TILE_COUNT 2048   /* no u: Z80 code uses it */
#define TERRAIN_STRIPS_MAX 255
#define TERRAIN_STRIPS (g_Map.strips)
#define TERRAIN_TILE_BANK (g_Map.tile_bank)
#define TERRAIN_MAP_BANK (g_Map.map_bank)
#define TERRAIN_FAR_COLUMN (g_Map.far_column)
#define TERRAIN_FAR_COLUMNS (g_Map.far_columns)
#define TERRAIN_SINK_TABLE (g_Map.sink_table)
#define TERRAIN_SEA_COLUMN (g_Map.sea_column)
#define TERRAIN_FAR_SEA_COLUMN (g_Map.far_sea_column)
#define TERRAIN_BLOCKS (g_Map.blocks)
#define g_TerrainPalette (g_Map.palette)
#define g_TerrainUniformColor (g_Map.uniform_color)
#define TERRAIN_UNIFORM_COLOR_ASM _g_Map+MAP_AT_UNIFORM_COLOR   /* for Z80 code */
#define g_TerrainBlockTop (g_Map.block_top)
''', 'The terrain of the loaded map.')
    out[ROM_HEADERS / 'mission_surfaces.h'] = header('mission_surfaces.h', '''\
#define MISSION_SURFACE_WIDTH (g_Map.width)
#define MISSION_SURFACE_RUNS (g_Map.surface_runs)
#define MISSION_WATER_REGIONS (g_Map.water_regions)
#define g_MissionWaterBands (g_Map.water)
/* Bit i: enemy ship i has gone under (core/ships.c). */
extern uint8_t g_ShipsGone;
''', 'The surfaces of the loaded map (the runs: Mission_Query, in ROM).')
    out[ROM_HEADERS / 'mission_heights.h'] = header('mission_heights.h', '''\
#define MISSION_HEIGHT_RUNS (g_Map.height_runs)
/* The height at world x (msx/map_record.c, resident: the runs in ROM). */
uint8_t Mission_Height(uint16_t world);
''', 'Static scenery heights: Mission_Height (the runs in ROM).')
    island = {'ISLAND_COUNT': 'islands', 'ISLAND_HUTS': 'huts', 'ISLAND_DUGOUTS': 'dugouts', 'ISLAND_GUNS': 'guns',
              's_HutX': 'hut_x', 's_HutIsland': 'hut_island', 's_DugoutX': 'dugout_x', 's_DugoutIsland': 'dugout_island',
              's_DugoutSide': 'dugout_side', 's_IslandLeft': 'island_left', 's_IslandRight': 'island_right',
              's_IslandBonus': 'island_bonus', 's_IslandFlagX': 'island_flag_x', 's_HutNearFirst': 'hut_near_first',
              's_HutNearCount': 'hut_near_count', 's_HutNearVariant': 'hut_near_variant', 's_HutFarFirst': 'hut_far_first',
              's_HutFarCount': 'hut_far_count', 's_HutFarVariant': 'hut_far_variant', 'PARKED_NEAR_FIRST': 'parked_near_first',
              'PARKED_NEAR_COUNT': 'parked_near_count', 'PARKED_FAR_FIRST': 'parked_far_first',
              'PARKED_FAR_COUNT': 'parked_far_count', 's_ParkedNear': 'parked_near', 's_ParkedFar': 'parked_far'}
    ships = {'SHIP_COUNT': 'ships', 'SHIP_GUNS': 'ship_guns', 'SHIP_CARRIER_LEFT': 'carrier_left',
             'SHIP_CARRIER_RIGHT': 'carrier_right', 's_ShipKind': 'ship_kind', 's_ShipLeft': 'ship_left',
             's_ShipRight': 'ship_right', 's_ShipDeck': 'ship_deck', 's_ShipHits': 'ship_hits', 's_ShipBonus': 'ship_bonus',
             's_ShipFirstGun': 'ship_first_gun', 's_ShipGunX': 'ship_gun_x', 's_ShipGunRise': 'ship_gun_rise',
             's_ShipSinkFirst': 'ship_sink_first', 'SHIP_SINKING': 'ship_sinking', 's_ShipNearLeft': 'ship_near_left',
             's_ShipNearRight': 'ship_near_right', 's_ShipFarFirst': 'ship_far_first', 's_ShipFarCount': 'ship_far_count',
             's_ShipSinkEntry': 'ship_sink_entry'}
    planes = {'PLANE_LISTS': 'plane_lists', 'PLANE_PARKED': 'plane_parked', 's_ListShip': 'list_ship',
              's_ListMax': 'list_max', 's_ListLo': 'list_lo', 's_ListHi': 'list_hi', 's_ListFirst': 'list_first',
              's_ParkedX': 'parked_x', 's_ParkedAlt': 'parked_alt', 's_ParkedDir': 'parked_dir'}
    cockpit = {'COCKPIT_LANDS': 'cockpit_lands', 'COCKPIT_TREES': 'cockpit_trees', 'COCKPIT_OBJECTS': 'cockpit_objects',
               'COCKPIT_OBJECT_REACH': 'cockpit_reach', 'COCKPIT_CARRIER_FIRST': 'cockpit_carrier_first',
               'COCKPIT_CARRIER_LAST': 'cockpit_carrier_last', 's_LandFirst': 'land_first', 's_LandLast': 'land_last',
               's_TreeFirst': 'tree_first', 's_TreeLast': 'tree_last', 's_ObjectFirst': 'object_first',
               's_ObjectLast': 'object_last', 's_ObjectKind': 'object_kind', 's_ObjectIndex': 'object_index',
               's_ShipView': 'ship_view'}
    def macros(names):
        return ''.join(f'#define {k} (g_Map.{v})\n' for k, v in names.items())
    out[ROM_HEADERS / 'mission_island.h'] = header('mission_island.h', macros(island), 'Island targets of the loaded map.')
    out[ROM_HEADERS / 'mission_ships.h'] = header('mission_ships.h', macros(ships), 'Enemy ships of the loaded map.')
    out[ROM_HEADERS / 'mission_planes.h'] = header('mission_planes.h', macros(planes), "Ships' plane lists of the loaded map.")
    out[ROM_HEADERS / 'cockpit_map.h'] = header('cockpit_map.h', macros(cockpit), "The cockpit window's features of the loaded map.")
    banks = ['0'] * len(MAP_ORDER)
    for entry in table: banks[entry['number']] = str(entry['record'][0])
    out[ROM_HEADERS / 'map_table.c'] = (GEN + '#include "map_record.h"\n'
                                        f'const uint8_t g_MapRecordBank[MAP_COUNT] = {{{", ".join(banks)}}};\n')
    return {path: text.encode() for path, text in out.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('maps', nargs='*', help='map letters (default: every converted map)')
    args = parser.parse_args()
    files = build(args.maps or maps_present())
    for path, data in files.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                sys.exit(f'stale: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    for entry in json.loads(files[OUT / 'maps.json'])['maps']:
        print(f"map {entry['map']}: tiles {entry['tiles'][0][0]}-{entry['tiles'][-1][0]}, column map "
              f"{entry['column_map'][0][0]}-{entry['column_map'][-1][0]}, record {entry['record'][0]} "
              f"({entry['ram_bytes']} bytes RAM, {entry['record_bytes']} in all)")


if __name__ == '__main__':
    main()
