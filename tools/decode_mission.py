"""Bounded decoding of original eight-pixel mission strips, backed by executable evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image
from decode_shapes import decode_record, read_palette
from extract_audio import read_hunks
from unpack_shapes import read_ppkc, unpack_rpck

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury'


def executable_evidence(blob):
    # File offsets, checked directly. Disassembly was exploratory, not a runtime dependency.
    guards = {
        0x2a0: '303c0097397c04b89f34',  # distant player baseline 1208, shifted by three
        0x3ea2: '7000323c0097343c013f363c00a2780a',  # distant sea rectangle, color 10
        0x4ec: '342cbf7e4442e442b47cfffe6c00000474fe',  # reduced pitch selection
        0x10bca: '1c2d000ccc056746266cc150504b3d430040426e0072',  # header byte 12 clears selected destination planes
        0x10c18: '1c2d000dcc056748266cc150504b3d4300403d7cffff0072',  # header byte 13 sets selected destination planes
        0x10d0a: 'b2fc00006600fe243f003010c0e80002b0acc43c6306301f6000fe10',  # transparent wrapper uses mask buffer size limit
        0x28b6: '43faff8f203c000004102940c43c',  # mask buffer is 1040 bytes
        0x10d6c: 'e248640e3218825a32c160062218829a22c151c8fff86066',  # raw bitmap planes OR into transparency mask
        0x524: '303c00a0322cbe624441d26c9f34342c9f36e461',  # player anchor is baseline minus altitude, before source origins
        0xc98e: '397c0008a3b2206ccdee0c5000ba6f06397c0001a3b2',  # altitude above 186 selects reduced-scale mode
        0x1086: '532ca36a6a000016532ca3906a000008197c000ba390197c0001a36a',  # wave phase decrements through twelve frames
        0x3ec8: '322ca3a2d27c000a206cbe4c7400142ca390d47c004ed442d442',  # normal-view wave baseline and frame table
        0x459e: '303c01027207343c017c762078022c6cb93a4eac8344303c0102322ca3e8343c017c762078014eac8344',  # pilot window clipping, sky and ground fills
        0x3826: '3c2cbe583a2cbe62e845da7c0018',  # pilot horizon follows aircraft altitude
        0x2b8c: '202cbef6d080d08051403940a394',  # header word -> reset X
        0x3604: '396ca394a07c',  # reset X -> aircraft position
        0x36ea: '397c0097a3a2',  # normal side-view baseline 151
        0x3876: '32003400e449c47c000336010881000d',
        0x388a: 'e549c27c07fc',  # shape ID bits 2..10
        0x38ae: '3203ee49c27c001cd245',  # depth bits -> 4-pixel Y offset
        0x38c6: '51409068000492680006',  # drawing origins
        0x50f0: '48e700804a406b00000ab06c96326500000c720070004cdf01004e75206c962ae648d040323000003001e449c27c01ffc07c00034cdf01004e75',  # bounded X query -> class and nine-bit object ID
        0x130e6: '4ef9000050c8',  # relocated jump-table entry to query
        0x2d76: '504251cfff84',  # one map word advances eight world pixels
        0x538e: '226cbe4c266cbe78303c00b7',  # first 184 shape slots
    }
    for offset, expected in guards.items():
        if blob[offset:offset + len(bytes.fromhex(expected))] != bytes.fromhex(expected):
            raise ValueError(f'executable instruction evidence differs at {offset:#x}')
    segments = read_hunks(blob)
    data = segments[1]
    table = b'barfbchlbchrdugohutahutbtre1tre2tre3bumbLIVE'
    start = data['payload'].find(table)
    if start < 0 or data['payload'].find(table, start + 1) >= 0:
        raise ValueError('missing or ambiguous world shape table')
    raw = data['payload'][start:start + 184 * 4]
    if len(raw) != 184 * 4 or data['payload'][start + 184 * 4:start + 184 * 4 + 4] != bytes(4):
        raise ValueError('world shape table length differs')
    names = [raw[i:i + 4].decode('ascii') for i in range(0, len(raw), 4)]
    if any(len(n) != 4 or not n.isalnum() for n in names):
        raise ValueError('invalid world shape name table')
    return dict(view_rules=dict(close_baseline=151, far_scale=8, far_altitude_exclusive=186, wave_frames=12, wave_direction=-1), executable_sha256=hashlib.sha256(blob).hexdigest(),
                shape_table_file_offset=data['file_offset'] + start, shape_names=names,
                instruction_guards=[dict(file_offset=o, bytes=h) for o,h in guards.items()])


def parse_map(blob):
    if len(blob) < 10 or len(blob) > 65536 or len(blob) % 2:
        raise ValueError('invalid/truncated mission length')
    declared, start = struct.unpack_from('>II', blob)
    if declared != len(blob):
        raise ValueError('mission declared byte size differs from file')
    words = struct.unpack('>' + str((len(blob) - 8) // 2) + 'H', blob[8:])
    spawn = start * 4 - 8
    width = len(words) * 8
    if not 0 <= spawn < width:
        raise ValueError('mission reset position outside decoded strip')
    cells = []
    for index, word in enumerate(words):
        if word & 0x4000 or word & 3 == 3:
            raise ValueError('unsupported reserved-bit or surface variant')
        cells.append(dict(index=index, file_offset=8 + index * 2, x=index * 8,
                          raw_word=word, draw=bool(word & 0x8000), shape_id=(word >> 2) & 511,
                          surface=word & 3, depth=(word >> 11) & 7, y_offset=((word >> 11) & 7) * 4))
    runs = []
    for cell in cells:
        if not runs or cell['surface'] != runs[-1]['surface']:
            runs.append(dict(start=cell['x'], end=cell['x'] + 8, surface=cell['surface']))
        else:
            runs[-1]['end'] = cell['x'] + 8
    return dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(), reset_header=start,
                reset_x=spawn, width=width, columns=len(cells), cells=cells, surface_runs=runs)


def reconstruct(map_data, evidence, baseline=201, height=212, reduced=False):
    """Return a static side-view adaptation; report every unresolved flagged entry.

    Object X/depth/shape/origins follow the source. Baseline translation, ground
    fill and static carrier treatment are explicit MSX rendering choices.
    """
    records = {name: (offset, record) for name, offset, record in read_ppkc(
        unpack_rpck((SOURCE / ('shapes/8thscale.shp' if reduced else 'shapes/world.shp')).read_bytes()))}
    source_width = (map_data['width'] + 7) // 8 if reduced else map_data['width']
    width = (source_width + 15) // 16 * 16
    pixels = bytearray([1]) * (width * height)
    # The sea shares the cyan backdrop. Sand is a foreground layer, so tree
    # roots and other depth-offset scenery cannot paint over the beach.
    ground = bytearray(width * height)
    _, beach_meta = decode_record(records['bchl'][1], allow_reduced_flag=reduced, plane_constants=True)
    sand_height = beach_meta['height'] - beach_meta['origin_candidate'][1]
    # Low-two-bit class 2 is the island region. The solid fill is authored,
    # not a recovered height profile. Carrier surfaces are supplied by hull art.
    for run in map_data['surface_runs']:
        if run['surface'] == 2:
            for y in range(baseline, min(height, baseline + sand_height)):
                start, end = (run['start'] // 8, (run['end'] + 7) // 8) if reduced else (run['start'], run['end'])
                ground[y * width + start:y * width + end] = bytes([17]) * (end - start)
    placed, unresolved = [], []
    for cell in map_data['cells']:
        if not cell['draw']:
            continue
        ident = cell['shape_id']
        name = evidence['shape_names'][ident] if ident < len(evidence['shape_names']) else None
        if ident == 0x113 and not reduced:
            # The island flag (0x3b52, close view only): its pole is baked
            # into the scenery as POST; the waving cloth is drawn over it at
            # run time while the island holds out.
            name = 'POST'
        if name not in records:
            unresolved.append(dict(**cell, name=name, reason='not present in normal-scale world shape archive' if name else 'outside fixed 184-entry world table; special marker or other archive'))
            continue
        offset, raw = records[name]
        data, meta = decode_record(raw, allow_reduced_flag=reduced, plane_constants=True)
        ox, oy = meta['origin_candidate']
        x, y = (cell['x'] // 8 if reduced else cell['x']) - ox, baseline + (0 if reduced else cell['y_offset']) - oy
        if name in ('bchl', 'bchr'):
            # Replace the flat fill at each shore with its original silhouette.
            # Keep the source shape's actual height; water continues below it.
            for dy in range(baseline, min(height, baseline + sand_height)):
                sy = dy - y
                for sx in range(meta['width']):
                    if 0 <= x + sx < width:
                        ground[dy * width + x + sx] = (data[sy * meta['width'] + sx]
                            if 0 <= sy < meta['height'] else 0)
            if reduced:
                # Reduced beach records sit slightly inside the coarse class
                # interval. Clear fill beyond their outer edges, otherwise the
                # two transparent shore pixels leave detached sand fragments.
                for run in map_data['surface_runs']:
                    if run['surface'] != 2 or not run['start'] <= cell['x'] < run['end']:
                        continue
                    start,end=run['start']//8,(run['end']+7)//8
                    clear_start,clear_end=(start,min(end,x)) if name=='bchl' else (max(start,x+meta['width']),end)
                    if clear_end>clear_start:
                        for dy in range(baseline,min(height,baseline+sand_height)):
                            ground[dy*width+clear_start:dy*width+clear_end]=bytes(clear_end-clear_start)
        visible = 0
        for sy in range(meta['height']):
            for sx in range(meta['width']):
                dx, dy = x + sx, y + sy
                color = data[sy * meta['width'] + sx]
                if (color or meta['opaque_rectangle']) and 0 <= dx < width and 0 <= dy < height:
                    pixels[dy * width + dx] = color
                    visible += 1
        placed.append(dict(**cell, name=name, drawing_x=x, drawing_y=y,
                           shape_offset=offset, shape_sha256=hashlib.sha256(raw).hexdigest(),
                           width=meta['width'], height=meta['height'], visible_pixels=visible))
    for pos, color in enumerate(ground):
        if color:
            pixels[pos] = color
    # Clip waves per scanline to the sand silhouette, including odd pixels.
    # Identical intervals merge vertically, except at the transparency split.
    water_bands, previous = [], {}
    for row in range(height - baseline):
        intervals = []
        for x in range(source_width):
            if ground[(baseline + row) * width + x]: continue
            if intervals and intervals[-1][1] == x: intervals[-1][1] = x + 1
            else: intervals.append([x, x + 1])
        current = {}
        for start, end in intervals:
            key = (start, end)
            if row != 2 and key in previous:
                band = previous[key]; band['height'] += 1
            else:
                band = dict(row=row, height=1, start=start, end=end)
                water_bands.append(band)
            current[key] = band
        previous = current
    return bytes(pixels), dict(width=width, height=height, source_width=map_data['width'],
        baseline=baseline, baseline_semantics='MSX canvas baseline 201; viewport crop 40 yields 161, eleven lines above dashboard',
        fill='foreground source-color-17 island sand with original beach silhouettes; cyan sky/sea index 1',
        sand_height=sand_height, water_bands=water_bands,
        source_sha256=map_data['sha256'], reset_x=map_data['reset_x'],
        placed=placed, unresolved=unresolved,
        scope='static normal-scale world shapes; special markers, dynamic ship parts and mission behavior are not emulated')


def artifacts():
    executable = (SOURCE / 'wings').read_bytes()
    evidence = executable_evidence(executable)
    maps = {p.name: parse_map(p.read_bytes()) for p in sorted((SOURCE / 'maps').glob('*.map'))}
    mission = maps['a.map']
    pixels, scene = reconstruct(mission, evidence)
    summary = {name: dict(bytes=m['bytes'], sha256=m['sha256'], width=m['width'], columns=m['columns'],
                           reset_x=m['reset_x'], draw_entries=sum(c['draw'] for c in m['cells']),
                           surface_runs=m['surface_runs']) for name,m in maps.items()}
    return evidence, mission, scene, pixels, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets_src/missions')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    evidence, mission, scene, pixels, summary = artifacts()
    from io import BytesIO
    palette = bytes((v >> 4) * 17 for v in read_palette((SOURCE / 'shapes/wingspalette').read_bytes()))
    image = Image.frombytes('P', (scene['width'], scene['height']), pixels)
    image.putpalette(palette + bytes(768 - len(palette)))
    buffer = BytesIO(); image.save(buffer, format='PNG')
    files = {'a-source.png': buffer.getvalue(), 'a.indices': pixels}
    for name, data in [('evidence.json', evidence), ('inventory.json', summary), ('a-map.json', mission), ('a-scene.json', scene)]:
        files[name] = (json.dumps(data, indent=2) + '\n').encode()
    for name, data in files.items():
        path = args.output / name
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                parser.error(f'missing or stale mission artifact: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps(dict(width=mission['width'], reset_x=mission['reset_x'],
                          placed=len(scene['placed']), unresolved=len(scene['unresolved']),
                          unresolved_shapes=dict(Counter(str(c['name'] or c['shape_id']) for c in scene['unresolved']))), indent=2))


if __name__ == '__main__':
    main()
