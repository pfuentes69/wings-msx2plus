"""Verify aircraft composition and bounded camera following in two scrolling pages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from PIL import Image
from aircraft_scene import AircraftScene
from verify_hardware_scroll import world_pixel

ROOT = Path(__file__).resolve().parents[1]


def vram_image(vram, palette, camera, page, mission=False, heave=0):
    """A linear RGB3 preview reconstructed from VRAM, not a rendered raster check."""
    indices = bytearray(256 * 212)
    for row in range(212):
        for col in range(8, 256):
            ring = (col if mission and row >= 172 else camera + col) % 256
            source_row = (row-heave)&255 if mission and row < 172 else row
            packed = vram[page * 32768 + source_row * 128 + ring // 2]
            indices[row * 256 + col] = packed & 15 if ring % 2 else packed >> 4
    image = Image.frombytes('P', (256, 212), bytes(indices))
    colors = bytes(channel * 255 // 7 for i in range(16)
                   for channel in ((palette[i * 2] >> 4) & 7, palette[i * 2 + 1] & 7, palette[i * 2] & 7))
    image.putpalette(colors + bytes(768 - len(colors)))
    return image


def expected_pixels(scene, frame, world, y, camera, background=None, background_width=4096, mission=False, scale=1, wave=0, pilot=0, heave=0, ship_frame=0):
    if background is None:
        pixels = [[world_pixel(camera + x, row) for x in range(256)] for row in range(212)]
    else:
        pixels = [list(background[row * background_width + camera:row * background_width + camera + 256]) for row in range(212)]
    if mission:
        from convert_dashboard import panel
        dashboard = panel()
        pixels = pixels[40:] + [list(dashboard[row * 256:(row + 1) * 256]) for row in range(40)]
    if mission:
        from convert_dashboard import waves, pilot_frame
        if scale == 1:
            for x in range(256):
                wx = camera + x
                if 6592 <= wx < 7368:
                    for row in range(172):
                        pixels[row][x] = background[(row+40-heave)*background_width+wx]
            ship = (ROOT/'assets_msx/ship/frames.indices').read_bytes()[ship_frame*1344:(ship_frame+1)*1344]
            for row in range(42):
                for col in range(32):
                    x = 6906 + col - camera
                    if 0 <= x < 256: pixels[46+heave+row][x] = ship[row*32+col]
            water = waves()[wave]
            water_bands = json.loads((ROOT / 'assets_src/missions/a-scene.json').read_text())['water_bands']
            for x in range(256):
                wx = camera + x
                for band in water_bands:
                    if not band['start'] <= wx < band['end']: continue
                    for row in range(band['row'], band['row'] + band['height']):
                        color = water[row * 96 + wx % 96]
                        if color: pixels[161 + row][x] = color
        cockpit = pilot_frame(pilot // 8, pilot % 8)
        for row in range(24): pixels[183 + row][108:156] = cockpit[row * 48:(row+1)*48]
    shape = scene.frames[frame]
    if mission and scale == 8:
        meta = json.loads((ROOT / 'assets_src/dashboard/manifest.json').read_text())
        index = meta['far_pose_for_frame'][frame]
        far = meta['far_poses'][index]
        shape = dict(width=far['width'], height=far['height'], dx=-far['origin_candidate'][0], dy=-far['origin_candidate'][1])
        source = (ROOT / 'assets_msx/dashboard/far-plane.indices').read_bytes()[index*80:index*80+80]

    else:
        source = (scene.folder / shape['file']).read_bytes()
    pivot = (161 - ((1200-y)//8) if scale == 8 else max(14,y-1055)) if mission else y
    for sy in range(shape['height']):
        dy = pivot + shape['dy'] + sy
        if not 0 <= dy < (172 if mission else 212): continue
        for sx in range(shape['width']):
            dx = world // scale + shape['dx'] + sx - camera - (25 if mission and scale == 1 else 0)
            if not 0 <= dx < 256: continue
            if mission and scale == 8: pixel = source[sy * shape['width'] + sx]
            else:
                packed = source[sy * (shape['width']//2) + sx//2]
                pixel = packed & 15 if sx%2 else packed >> 4
            if pixel: pixels[dy][dx] = pixel
    if mission: pixels[171] = [1]*256
    return pixels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/world-flight')
    parser.add_argument('--project', choices=['world-flight', 'tile-flight', 'mission-flight'], default='world-flight')
    parser.add_argument('--headless', action='store_true', help='disable graphics; verify VRAM and timing without raster screenshots')
    args = parser.parse_args()
    if not args.emulator:
        parser.error('openmsx is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'verification.json').unlink(missing_ok=True)
    (output / 'emulator-report.txt').unlink(missing_ok=True)
    personal = Path(os.environ.get('OPENMSX_HOME', Path.home() / '.openMSX'))
    env = dict(os.environ, OPENMSX_HOME=str(output / 'openmsx-home'), WINGS_ROOT=str(ROOT), WINGS_PROJECT=args.project,
               WINGS_TEST_OUT=str(output), SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA', str(personal / 'share'))
    env['WINGS_HEADLESS'] = '1' if args.headless else '0'
    rom = ROOT / f'out/{args.project}/{args.project}.rom'
    rom_bytes = rom.read_bytes()
    background = terrain = None
    if args.project in ('tile-flight', 'mission-flight'):
        import re
        symbols = dict((name, int(value, 16)) for name, value in re.findall(
            r'DEF _(\w+) (0x[0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text()))
        if args.project == 'mission-flight':
            assert 0x4000 <= symbols['Scenery_Read'] < symbols['Scenery_ReadEnd'] < 0x6000
        else:
            assert 0x4000 <= symbols['Terrain_Load'] < symbols['Terrain_LoadEnd'] < 0x6000
            assert not 0x6000 <= symbols['VDP_WriteVRAM_128K'] < 0x8000
        folder = ROOT / ('assets_msx/mission_a' if args.project == 'mission-flight' else 'assets_msx/terrain')
        terrain = json.loads((folder / 'manifest.json').read_text())
        background = (folder / 'scene.indices').read_bytes()
        bundle = (folder / 'tiles.sc5').read_bytes() + (folder / 'map.bin').read_bytes()
        assert len(rom_bytes) == (131072 if args.project == 'mission-flight' else 65536)
        assert rom_bytes[32768:32768 + len(bundle)] == bundle, 'incorrect ROM asset bank placement'
        if args.project == 'mission-flight':
            for bank in range(8,11):
                data = (ROOT / f'assets_msx/hellcat/mission_bank_{bank}.bin').read_bytes()
                assert rom_bytes[bank*8192:bank*8192+len(data)] == data
            assert rom_bytes[11*8192:11*8192+6336] == (ROOT / 'assets_msx/dashboard/waves.sc5').read_bytes()
    with (output / 'openmsx.log').open('w') as log:
        cartridge = ['-cart', str(rom)] + (['-romtype', 'ASCII8'] if terrain else [])
        settings = []
        if args.headless:
            config = output / 'headless.xml'
            config.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings><setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting></settings></settings>')
            settings = ['-setting', str(config)]
        subprocess.run([args.emulator, *settings, '-machine', args.machine, *cartridge,
                        '-script', str(ROOT / 'tools/world_flight_smoke.tcl')],
                       env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                       timeout=150, check=True)
    assert rom.read_bytes() == rom_bytes, 'ROM changed during verification; rebuild first, then rerun'
    report = (output / 'emulator-report.txt').read_text()
    assert report.rstrip().endswith('PASS'), report[-2000:]
    scene = AircraftScene()
    if terrain:
        scene.palette = (folder / 'palette.bin').read_bytes()
    mission = args.project == 'mission-flight'
    world_width = terrain['source_width'] if mission else 4096
    initial_x = terrain['reset_x'] if mission else 104
    snapshots, renders, intervals, colors = {}, [], [], {}
    views = {p[1]: tuple(map(int,p[2:])) for line in report.splitlines() if (p := line.split()) and p[0] == 'view'}
    ships = {p[1]: tuple(map(int,p[2:])) for line in report.splitlines() if (p := line.split()) and p[0] == 'ship'}
    transitions = []
    hidden_checks = 0
    for line in report.splitlines():
        parts = line.split()
        if parts[0] == 'render_ms':
            renders.append(float(parts[1]))
        elif parts[0] == 'transition_ms':
            transitions.append(float(parts[1]))
        elif parts[0] == 'interval_ms':
            intervals.append(float(parts[1]))
        elif parts[0] == 'hidden_checks':
            hidden_checks = int(parts[1])
        elif parts[0] == 'snapshot':
            name, camera, world, x, y, frame, pair, turning = parts[1], *map(int, parts[2:])
            scale, wave, pilot = views[name] if mission else (1,0,0)
            view_world = world // scale
            assert camera == max(0, min((world_width + scale - 1) // scale - 256, view_world - 128)), name
            assert x == view_world - camera and pair in (0, 1), name
            snapshots[name] = dict(camera=camera, world=world, x=x, y=y, frame=frame, pair=pair, turning=turning, scale=scale, wave=wave, pilot=pilot)
            heave, ship_frame = ships[name] if mission else (0,0)
            if mission: snapshots[name].update(heave=heave,ship_frame=ship_frame)
            regs = (output / f'{name}.regs').read_bytes()
            assert regs[0] & 14 == 6 and regs[1] & 64 and regs[9] & 128, (name, 'SCREEN 5 display/212-line mode')
            assert regs[25] & 3 == 2 and (regs[2] >> 5) & 3 == pair, name
            assert regs[26] == (((camera & 255) + 7) // 8) & 63 and regs[27] == (-camera) % 8, name
            assert (output / f'{name}.palette').read_bytes() == scene.palette, name
            vram = (output / f'{name}.vram').read_bytes()
            if terrain:
                assert (output / f'{name}.rom').read_bytes() == rom_bytes[:32768], (name, 'cartridge bank restoration')
                tiles = (folder / 'tiles.sc5').read_bytes()
                size = terrain['selected']['size']
                per_row = 256 // size
                per_page = terrain['vram'].get('tiles_per_page', 64)
                tile_bytes = size * size // 2
                for tile in range(terrain['selected']['tile_count']):
                    sy = (tile // per_page + 2) * 256 + 180 + (tile % per_page // per_row) * size
                    sx = (tile % per_row) * size
                    if mission:
                        sy = (tile // 288 + 2) * 256 + 180 + (tile % 9) * 8
                        sx = (tile % 288 // 9) * 8
                    for row in range(size):
                        address = (sy + row) * 128 + sx // 2
                        stride = size // 2
                        assert vram[address:address + stride] == tiles[tile * tile_bytes + row * stride:tile * tile_bytes + (row + 1) * stride], (name, 'terrain cache corrupted')
            for shape in scene.frames:
                source = (scene.folder / shape['file']).read_bytes()
                stride = shape['width'] // 2
                for row in range(shape['height']):
                    address = (shape['atlas_y'] + row) * 128 + shape['atlas_x'] // 2
                    assert vram[address:address + stride] == source[row * stride:(row + 1) * stride], (name, 'atlas corrupted')
            if mission:
                far_meta = json.loads((ROOT / 'assets_src/dashboard/manifest.json').read_text())
                water = (ROOT/'assets_msx/dashboard/waves.sc5').read_bytes()
                for phase in range(12):
                    for row in range(11):
                        if (phase & 3) == 3 and row >= 9:
                            sx,sy = far_meta['wave_tail_slots'][phase >> 2]; sy += row-9
                        else:
                            sx = 144 if 4 <= phase < 8 else 48
                            sy = 212+(phase&3)*11+(256 if phase >= 8 else 0)+row
                        address=sy*128+sx//2
                        offset=phase*528+row*48
                        assert vram[address:address+48] == water[offset:offset+48], (name,'wave cache',phase,row)
                for display_page in (0,1):
                    assert not any(vram[(display_page*256+254)*128:(display_page*256+256)*128]), (name,'heave wrap rows')
                ship_meta=json.loads((ROOT/'assets_msx/ship/manifest.json').read_text())
                ship_pixels=(ROOT/'assets_msx/ship/frames.indices').read_bytes()
                for phase,record in enumerate(ship_meta['frames']):
                    for piece,(sx,sy) in enumerate(record['parts']):
                        for row in range(14):
                            offset=phase*1344+((piece//2)*14+row)*32+(piece&1)*16
                            line=ship_pixels[offset:offset+16]
                            packed=bytes((line[x]<<4)|line[x+1] for x in range(0,16,2))
                            address=(sy+row)*128+sx//2
                            assert vram[address:address+8] == packed, (name,'ship cache',phase,piece,row)
                far_pixels = (ROOT / 'assets_msx/dashboard/far-plane.indices').read_bytes()
                for index, pose in enumerate(far_meta['far_poses']):
                    for row in range(5):
                        address = (pose['atlas_y'] + row)*128 + pose['atlas_x']//2
                        pixels = far_pixels[index*80+row*16:index*80+(row+1)*16]
                        packed = bytes((pixels[x]<<4)|pixels[x+1] for x in range(0,16,2))
                        assert vram[address:address+8] == packed, (name,'reduced aircraft atlas',pose['name'])
            expected = expected_pixels(scene, frame, world, y, camera, (folder / 'far.indices').read_bytes() if mission and scale == 8 else background, terrain['far_width'] if mission and scale == 8 else terrain['width'] if terrain else 4096, mission, scale, wave, pilot, heave, ship_frame)
            if mission:
                assert regs[0] & 16 and regs[19] == (169-heave if heave else 171), (name, 'dashboard split IRQ')
            for row in range(212):
                for col in range(8, 256):
                    ring = (col if mission and row >= 172 else camera + col) % 256
                    source_row = (row-heave)&255 if mission and row < 172 else row
                    address = pair * 32768 + source_row * 128 + (ring % 256) // 2
                    actual = vram[address] & 15 if ring % 2 else vram[address] >> 4
                    assert actual == expected[row][col], (name, 'VRAM', col, row, actual, expected[row][col])
            if args.headless:
                vram_image(vram, scene.palette, camera, pair, mission, heave).save(output / f'{name}-vram.png')
                continue
            image = Image.open(output / f'{name}.png').convert('RGB')
            assert image.size == (320, 240), (name, image.size)
            pixels = image.load()
            for row in range(212):
                for col in range(256):
                    index = expected[row][col] if col >= 8 else 0
                    rgb = pixels[32 + col, 14 + row]
                    if index not in colors:
                        for known, existing in colors.items():
                            if existing == rgb:
                                assert scene.palette[known * 2:known * 2 + 2] == scene.palette[index * 2:index * 2 + 2], (name, 'collapsed palette')
                        colors[index] = rgb
                    assert rgb == colors[index], (name, 'raster', col, row, index, rgb)
    required = {'initial', 'terrain_flight', 'aircraft_page_seam', 'aircraft_ring_seam',
                'right_bound', 'left_climb', 'top_clipped', 'left_bound', 'reset', 'stationary_turn'}
    required.update(f'fine_{phase}' for phase in range(8))
    assert required <= snapshots.keys(), required - snapshots.keys()
    assert snapshots['initial']['world'] == initial_x
    assert snapshots['initial']['camera'] == max(0, min(world_width - 256, initial_x - 128))
    assert snapshots['terrain_flight']['y'] == (1200 if mission else 180)
    assert snapshots['right_bound']['world'] == world_width - 1
    assert snapshots['left_bound']['world'] == 0
    assert snapshots['top_clipped']['y'] == 0
    assert snapshots['reset']['world'] == (world_width - 1 if mission else 0) and snapshots['reset']['y'] == (1108 if mission else 88)
    assert {s['pair'] for s in snapshots.values()} == {0, 1}
    if terrain and not mission:
        assert any(s['turning'] and 128 < s['world'] < 3900 and s['y'] == 180 for s in snapshots.values()), 'missing terrain-overlap turn'
    if mission:
        assert {'carrier_tower', 'dugout_1', 'hut_1', 'hut_2', 'dugout_2', 'island_coast'} <= snapshots.keys(), 'missing source-backed map landmarks'
    if mission:
        assert {s['scale'] for s in snapshots.values()} == {1,8}
        assert {s['heave'] for s in snapshots.values()} == {0,1,2}
        assert {s['ship_frame'] for s in snapshots.values()} == {0,1,2,3}
        # At 24 PAL simulation steps/presentation, the 12-step wave clock
        # advances exactly two phases: six displayed phases, all twelve cached.
        assert len({s['wave'] for s in snapshots.values()}) >= (6 if args.machine == 'C-BIOS_MSX2+_EU' else 8)
        assert {'distant_climb','distant_bank_1','distant_bank_2','distant_bank_3'} <= snapshots.keys()
        assert all(snapshots[n]['scale'] == 8 for n in ('distant_bank_1','distant_bank_2','distant_bank_3'))
        assert len({far_meta['far_pose_for_frame'][snapshots[n]['frame']] for n in
                    ('distant_bank_1','distant_bank_2','distant_bank_3')}) >= 2
        for s in snapshots.values():
            assert s['scale'] == (8 if 1200-s['y'] > 186 else 1)
            assert s['pilot'] % 8 == min(255,1200-s['y']) // 32
        source = json.loads((ROOT / 'assets_src/missions/a-map.json').read_text())
        surfaces = {p[1]: int(p[2]) for line in report.splitlines()
                    if (p := line.split()) and p[0] == 'surface'}
        assert surfaces.keys() == snapshots.keys()
        for name, snapshot in snapshots.items():
            expected_word = source['cells'][snapshot['world'] // 8]['raw_word'] & 0x7ff
            assert surfaces[name] == expected_word, (name, 'source surface/object query')
            snapshot['surface'] = surfaces[name] & 3
            snapshot['object_id'] = surfaces[name] >> 2
        assert {s['surface'] for s in snapshots.values()} == {0, 1, 2}
    pal = bool((output / 'initial.regs').read_bytes()[9] & 2)
    period_ticks = 8 if mission else 2
    target_fps = (50 if pal else 60) / period_ticks
    target = 1000 / target_fps
    assert len(intervals) > (int(target_fps * 110) if mission else 1800) and len(renders) > (int(target_fps * 90) if mission else 1000)
    assert hidden_checks == len(renders) + len(transitions)
    assert min(intervals) > target - 2 and max(intervals) < target + 2
    assert max(renders) < target
    summary = dict(machine=args.machine, project=args.project, raster_checked=not args.headless, rom_sha256=hashlib.sha256(rom_bytes).hexdigest(),
                   target_fps=target_fps, presentation_vblanks=period_ticks, publication_samples=len(intervals),
                   publication_ms=dict(min=min(intervals), median=statistics.median(intervals), max=max(intervals)),
                   redraw_samples=len(renders), view_transition_ms=transitions,
                   redraw_ms=dict(min=min(renders), median=statistics.median(renders), max=max(renders)),
                   missed_deadlines=0, hidden_page_checks=hidden_checks, snapshots=snapshots,
                   checks=['full visible VRAM and completed raster', 'transparent aircraft and trail restoration',
                           'bounded world flight and camera following', 'all fine-scroll phases',
                           'aircraft page/ring seams', 'turns and vertical clipping',
                           'both world bounds and reset', 'immutable visible page during every redraw',
                           'immutable aircraft atlas', f'{target_fps:g} Hz VBlank publication'])
    if terrain:
        summary['terrain_bundle_sha256'] = terrain['bundle_sha256']
        summary['checks'] += ['immutable terrain tile cache', 'actual mapper-bank restoration',
                              'original-art authored scene at every visible pixel']
    if mission:
        summary['source_map_sha256'] = terrain['source_sha256']
        summary['checks'] += ['source-backed a.map landmarks and reset position', 'compressed 16-bit tile-ID columns', 'runtime source surface/object queries',
                              'fixed original-art dashboard and split scrolling', 'aircraft clipped above dashboard',
                              'startup aircraft banks 8-10 and wave bank 11', 'altitude-selected 1:8 original scenery',
                              'original twelve-frame water animation', 'forward pilot display with fixed reticle']
    if args.headless:
        summary['checks'][0] = 'full visible VRAM; raster screenshots not checked (headless renderer)'
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: {len(snapshots)} snapshots; max redraw {max(renders):.2f} ms')


if __name__ == '__main__':
    main()
