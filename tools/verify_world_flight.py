"""Verify aircraft composition and bounded camera following in two scrolling pages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
from PIL import Image
from aircraft_scene import AircraftScene

from convert_hellcat import aircraft_bank
ROOT = Path(__file__).resolve().parents[1]


def vram_image(vram, palette, camera, page, heave=0, fine=0):
    """A linear RGB3 preview reconstructed from VRAM, not a rendered raster check."""
    indices = bytearray(256 * 212)
    for row in range(212):
        for col in range(8, 256):
            ring = (col if row >= 172 else camera + col) % 256
            source_row = vram_row(row, fine, heave) if row < 172 else row
            packed = vram[page * 32768 + source_row * 128 + ring // 2]
            indices[row * 256 + col] = packed & 15 if ring % 2 else packed >> 4
    image = Image.frombytes('P', (256, 212), bytes(indices))
    colors = bytes(channel * 255 // 7 for i in range(16)
                   for channel in ((palette[i * 2] >> 4) & 7, palette[i * 2 + 1] & 7, palette[i * 2] & 7))
    image.putpalette(colors + bytes(768 - len(colors)))
    from convert_dashboard import dashboard_palette
    panel = Image.frombytes('P', (256, 40), bytes(indices[172*256:]))
    p = dashboard_palette()
    panel.putpalette(bytes(v*255//7 for i in range(16)
        for v in (p[i*2]>>4, p[i*2+1], p[i*2]&7)) + bytes(720))
    image = image.convert('RGB')
    image.paste(panel.convert('RGB'), (0, 172))
    return image


def gun_flash_shape(scene, frame, flash):
    """Original cannon overlay record and packed pixels for a drawn pitch frame, or None."""
    meta = scene.metadata
    if not flash or 'gun_flash' not in meta:
        return None
    for side, table in ((0, meta['pitch_right']), (10, meta['pitch_left'])):
        if frame in table:
            record = meta['gun_flash'][(flash - 1) * 20 + side + table.index(frame)]
            bank = record['data_offset'] // 8192
            data = (scene.folder / f'mission_bank_{aircraft_bank(bank)}.bin').read_bytes()
            offset = record['data_offset'] % 8192
            return record, data[offset:offset + record['bytes']]
    return None


def wheel_pieces(scene, sprite):
    """Landing-gear overlay pieces (records and packed pixels) for a published sprite."""
    meta = scene.metadata
    if sprite == 255 or 'wheels' not in meta:
        return []
    out = []
    for record in meta['wheels'][meta['wheel_first'][sprite]:meta['wheel_first'][sprite + 1]]:
        bank = record['data_offset'] // 8192
        data = (scene.folder / f'mission_bank_{aircraft_bank(bank)}.bin').read_bytes()
        offset = record['data_offset'] % 8192
        out.append((record, data[offset:offset + record['bytes']]))
    return out


def crash_shape(scene, index):
    """Original crash art record and packed pixels (streamed into the host slot)."""
    record = scene.metadata['crash'][index]
    bank = record['data_offset'] // 8192
    data = (scene.folder / f'mission_bank_{aircraft_bank(bank)}.bin').read_bytes()
    offset = record['data_offset'] % 8192
    return record, data[offset:offset + record['bytes']]


def island_background(background, scale, island, lives=3):
    """The scene with wrecked huts (g_Island dump: 8-byte hut records,
    wrecked at +3) and the deck's spare planes (lives - 1, at most 2)
    showing the converter's variant columns."""
    meta = json.loads((ROOT / 'assets_msx/mission_a/manifest.json').read_text())
    variants, height = meta['hut_variants'], meta['height']
    width = meta['width'] if scale == 1 else meta['far_width']
    stripes, data = [], (ROOT / 'assets_msx/mission_a/hut-variants.indices').read_bytes()
    for key in ('near_count', 'far_count'):
        for v in variants:
            size = 8 * v[key] * height
            stripes.append(data[:size]); data = data[size:]
    pixels = bytearray(background)
    for i, v in enumerate(variants):
        if not island[8 * i + 3]: continue
        first, count = (v['near_first'], v['near_count']) if scale == 1 else (v['far_first'], v['far_count'])
        stripe, w = stripes[i if scale == 1 else len(variants) + i], 8 * count
        for y in range(height):
            pixels[y * width + first * 8:y * width + first * 8 + w] = stripe[y * w:(y + 1) * w]
    parked = meta['parked']
    shown = min(max(lives - 1, 0), parked['max'])
    if shown < parked['max']:
        data = (ROOT / 'assets_msx/mission_a/parked-variants.indices').read_bytes()
        near, far = 8 * parked['near_count'] * height, 8 * parked['far_count'] * height
        index = parked['max'] - 1 - shown
        if scale == 1:
            first, w, stripe = parked['near_first'], 8 * parked['near_count'], data[index * near:(index + 1) * near]
        else:
            base = parked['max'] * near
            first, w, stripe = parked['far_first'], 8 * parked['far_count'], data[base + index * far:base + (index + 1) * far]
        for y in range(height):
            pixels[y * width + first * 8:y * width + first * 8 + w] = stripe[y * w:(y + 1) * w]
    return bytes(pixels)


def pan_of(y, scale):
    """The close-view pan (original 0x26e): above altitude 131 the scene
    moves down with the plane, up to 55 px before the distant view."""
    return max(0, 1200 - y - 131) if scale == 1 else 0


def vram_row(row, fine, heave):
    """The VRAM row a play-area screen row shows: the top s lines keep the
    heave scroll, the rest add the fine pan (the published g_DisplayFine,
    0..11; whole tile rows of pan are drawn in VRAM). The split is requested
    up to 2 lines early; those lines show VRAM rows 254..255 (sky)."""
    scroll = heave + fine
    early = min(fine, 2) if fine > 0 else 0
    return (row - heave) % 256 if row < scroll - early else (row - scroll) % 256


def expected_pixels(scene, frame, world, y, camera, background, background_width, scale=1, wave=0, pilot=0, heave=0, ship_frame=0, projectiles=(), stock=30, weapon=0, lives=3, crew_phase=None, on_deck=False, elevator_depth=None, elevator_active=False, flash=0, gauges=(16, 22, 0), crash=255, wheel=255, gear=5, deck_level=False, rope=255, facing_left=True, smoke=(), score=0, fine=None, band=0, sink=None):
    # World x is a 16-bit ring read as signed; beyond the map the MSX draws a
    # column of open sea (map x 5000 near, far x 624 in the distant view).
    signed = lambda v: v - 65536 if v >= 32768 else v
    camera, world = signed(camera), signed(world)
    sea = 5000 if scale == 1 else 624
    def source_x(wx):
        return wx if 0 <= wx < background_width else sea + (wx & 7)
    pan = pan_of(y, scale)
    if fine is None: fine = pan & 7
    scroll = heave + fine
    # Overlays (plane, wheels, flash, weapons, rope) stay at VRAM rows from
    # g_TopClip (fine + 1 in the close-view pan, else 0): screen rows from here.
    # The message band (rows 0 .. band + 1 shown unscrolled): band + 2.
    clip = band + 2 if band else (fine + 1 if fine > 0 else 0) if scale == 1 else 0
    overlay_top = scroll + clip
    panned = pan - fine >= 8   # whole tile rows of pan: the wave strip is below the view
    def background_row(row):   # rows above the image are sky
        return max(row, 0) * background_width
    pixels = [[background[background_row(row - pan) + source_x(camera + x)] for x in range(256)] for row in range(212)]
    from convert_dashboard import compose, waves, pilot_frame, layout, PILOT_WIDTH
    # gauges: oil needle frame, fuel needle frame, lamp bits (1 oil, 2 fuel) as published.
    dashboard = compose(ammo=stock, weapon=weapon, lives=lives, oil=gauges[0], fuel=gauges[1],
                        oil_lamp=bool(gauges[2] & 1), fuel_lamp=bool(gauges[2] & 2), score=score)
    pixels = pixels[40:] + [list(dashboard[row * 256:(row + 1) * 256]) for row in range(40)]
    if scale == 1:
        for x in range(256):
            wx = camera + x
            if 6592 <= wx < 7368:
                for row in range(172):
                    pixels[row][x] = background[background_row(row+40-heave-pan)+source_x(wx)]
        ship = (ROOT/'assets_msx/ship/frames.indices').read_bytes()[ship_frame*1344:(ship_frame+1)*1344]
        for row in range(42):
            for col in range(32):
                x = 6906 + col - camera
                if 0 <= x < 256: pixels[46+heave+pan+row][x] = ship[row*32+col]
        if crew_phase is not None:
            crew=(ROOT/'assets_msx/ship/crew.indices').read_bytes()
            for man,anchor in enumerate((6968,7344)):
                pose=16 if man==0 and elevator_active else man*8+crew_phase
                patch=crew[pose*308:(pose+1)*308]
                for row in range(14):
                    for col in range(22):
                        x=anchor-10+col-camera
                        if 0<=x<256 and 116+row+pan<172:pixels[116+heave+pan+row][x]=patch[row*22+col]
        if elevator_depth is not None:
            from unpack_shapes import read_ppkc,unpack_rpck
            from decode_shapes import decode_record
            records={n:r for n,_,r in read_ppkc(unpack_rpck((ROOT/'reference_assets/original_files/Wings_of_Fury/shapes/world.shp').read_bytes()))}
            platform,_=decode_record(records['elev'],plane_constants=True)
            mapping=json.loads((ROOT/'assets_msx/terrain/manifest.json').read_text())['source_to_msx_index']
            for row in range(13):
                dy=129+elevator_depth+row+heave+pan
                if dy>=min(142+pan,172)+heave:continue  # the well's lower edge (CARRIER_WELL_BOTTOM)
                for col in range(64):
                    x=7004+col-camera;v=platform[row*64+col]
                    if v and 0<=x<256:pixels[dy][x]=mapping[str(v)]
        water = waves()[wave]
        water_bands = json.loads((ROOT / 'assets_src/missions/a-scene.json').read_text())['water_bands']
        for x in range(0 if panned else 256):
            wx = camera + x
            for band in water_bands:
                # Bands reaching either end of the map run on over the sea.
                if not (band['start'] <= wx or band['start'] == 0) or not (wx < band['end'] or band['end'] >= 7608): continue
                for row in range(band['row'], band['row'] + band['height']):
                    color = water[row * 96 + wx % 96]
                    if color and 161 + row + pan < 172: pixels[161 + row + pan][x] = color
    # pilot: the cockpit window's pixels (46 x 24, tools/convert_cockpit.py
    # compose), None when not known (not compared), or the old profile number.
    hud = layout()
    if isinstance(pilot, int):
        cockpit = pilot_frame(pilot // 8, pilot % 8)
        cockpit = [cockpit[row*48:row*48 + PILOT_WIDTH] for row in range(24)]
    else:
        cockpit = [pilot[row*PILOT_WIDTH:(row+1)*PILOT_WIDTH] if pilot else [None] * PILOT_WIDTH for row in range(24)]
    for row in range(24):
        pixels[172 + hud['pilot_y'] + row][hud['pilot_x']:hud['pilot_x'] + PILOT_WIDTH] = cockpit[row]
    shape = scene.frames[frame]
    if scale == 8:
        meta = json.loads((ROOT / 'assets_src/dashboard/manifest.json').read_text())
        index = meta['far_pose_for_frame'][frame]
        far = meta['far_poses'][index]
        shape = dict(width=far['width'], height=far['height'], dx=-far['origin_candidate'][0], dy=-far['origin_candidate'][1])
        source = (ROOT / 'assets_msx/dashboard/far-plane.indices').read_bytes()[index*80:index*80+80]

    else:
        source = (scene.folder / shape['file']).read_bytes()
    pivot = 161 - ((1200-y)//8) if scale == 8 else max(14,y-1055)
    # Engine smoke and dugout guns, behind the plane: published (x, screen
    # row, frame) per shape; x is in this view's scale. Clipped above the wave
    # strip (VRAM row 159), or above the sand row (161) in the distant view.
    meta = scene.metadata
    for sx_, row, frame in smoke:
        sx_ = signed(sx_)
        for record in meta['smoke'][meta['smoke_first'][frame]:meta['smoke_first'][frame + 1]]:
            bank = record['data_offset'] // 8192
            data = (scene.folder / f'mission_bank_{aircraft_bank(bank)}.bin').read_bytes()
            packed = data[record['data_offset'] % 8192:record['data_offset'] % 8192 + record['bytes']]
            vram_limit = min(142 if elevator_active else 172, 161 if scale == 8 else 172 if panned else 159)
            for yy in range(record['height']):
                r = row + record['dy'] + yy
                # VRAM rows 0 .. fine - 1 show in the top split: none drawn there.
                if not clip <= r - scroll < vram_limit or r >= 172: continue
                for xx in range(record['width']):
                    wx = sx_ + record['dx'] + xx
                    if not camera + 8 <= wx < camera + 256: continue
                    b = packed[yy * (record['width'] // 2) + xx // 2]
                    v = b & 15 if xx % 2 else b >> 4
                    if v: pixels[r][wx - camera] = v
    if on_deck and deck_level:
        # Rolling fast or held by a cable: the level pose at deck height on its
        # wheel overlay, riding the deck heave and the elevator.
        pivot += heave + (elevator_depth or 0)
    if scale == 1 and crash == 255:
        # The wheels go behind the plane, (5 - gear) px higher while moving.
        for record, wheel_source in wheel_pieces(scene, wheel):
            for sy in range(record['height']):
                dy = pivot + record['dy'] + gear - 5 + sy
                if elevator_active and dy >= 142 + heave: continue
                if not overlay_top <= dy < 172: continue
                for sx in range(record['width']):
                    dx = world + record['dx'] + sx - camera - 25
                    if not 0 <= dx < 256: continue
                    packed = wheel_source[sy * (record['width']//2) + sx//2]
                    pixel = packed & 15 if sx%2 else packed >> 4
                    if pixel: pixels[dy][dx] = pixel
    for sy in range(shape['height'] if crash == 255 else 0):
        dy = (129 - shape['height'] + sy + heave + (elevator_depth or 0)) if on_deck and not deck_level else pivot + shape['dy'] + sy
        if sink is not None:
            # Sinking (src/core/crash.c): sink px lower, hidden from the
            # wave strip's third row (VRAM 163 - heave).
            dy += sink
            if dy >= 163 + fine: continue
        if elevator_active and dy>=142+heave:continue
        if not overlay_top <= dy < 172: continue
        for sx in range(shape['width']):
            dx = (world >> 3 if scale == 8 else world) + shape['dx'] + sx - camera - (25 if scale == 1 else 0)
            if not 0 <= dx < 256: continue
            if scale == 8: pixel = source[sy * shape['width'] + sx]
            else:
                packed = source[sy * (shape['width']//2) + sx//2]
                pixel = packed & 15 if sx%2 else packed >> 4
            if pixel: pixels[dy][dx] = pixel
    overlay = gun_flash_shape(scene, frame, flash) if scale == 1 and not on_deck else None
    if crash != 255:
        overlay = crash_shape(scene, crash)  # the crash art replaces the plane
    if overlay:
        record, source = overlay
        for sy in range(record['height']):
            dy = pivot + record['dy'] + sy
            if not overlay_top <= dy < 172: continue
            for sx in range(record['width']):
                dx = world + record['dx'] + sx - camera - 25
                if not 0 <= dx < 256: continue
                packed = source[sy * (record['width']//2) + sx//2]
                pixel = packed & 15 if sx%2 else packed >> 4
                if pixel: pixels[dy][dx] = pixel
    if rope != 255 and scale == 1 and crash == 255:
        # The arresting rope (Amiga 0x05c0): cable on the deck to the hook,
        # 16 px behind the plane; cable half one row lower. Colour 13 is the
        # nearest playfield entry to the original's red.
        cable = 7032 + 70 + 56 * rope
        hook = world + 16 if facing_left else world - 16
        low, high = min(cable, hook), max(cable, hook)
        half = (high - low) // 2
        left, right = max(low & ~1, camera + 8), min((high + 2) & ~1, camera + 256)
        right = min(right, left + 128)
        origin = pivot + 16
        limit = 142 + heave if elevator_active else 172
        if cable >= hook:
            runs = ((cable - half, cable + 1, origin + 6), (hook, cable - half, origin + 5))
        else:
            runs = ((cable, cable + half + 1, origin + 6), (cable + half + 1, hook + 1, origin + 5))
        for start, end, row in runs:
            if not overlay_top <= row < limit: continue
            for wx in range(max(start, left), min(end, right)):
                pixels[row][wx - camera] = 13
    def mark(x,y,w,h,color):
        for yy in range(max(overlay_top,y),min(171+scroll,172,y+h)):   # VRAM rows < 171
            for xx in range(max(camera+8,x),min(camera+256,x+w)):
                pixels[yy][xx-camera] = color
    for p in projectiles:
        kind=p['kind']
        if not kind: continue
        x,y=p['x']//4,p['y']//4
        if scale == 8: x//=8; y=161-((1200-y)>>3)
        else: y=y-1039+pan
        if scale == 8: mark(x,y,1,2 if kind>=3 else 1,11)
        elif kind == 2:
            from convert_dashboard import bomb_frames
            bomb_art,pivots=bomb_frames()
            # The original tumble: bom3 moving left, bom9 right, a frame per
            # 4 weapon ticks of age (COMBAT_BOMB_LIFE 255).
            pose=((3 if p['vx']<0 else 9)+((255-p['life'])>>2))%12
            source=bomb_art[pose*48:(pose+1)*48]   # 8 x 6 cells
            px,py=pivots[pose]
            for row in range(6):
                for col in range(8):
                    color=source[row*8+col]
                    if color:mark(x-px+col,y-py+row,1,1,color)
        else:
            mark(x-3,y,7,1,5 if kind==4 else 14)
            mark(x,y-3,1,7,5 if kind==4 else 14)
            mark(x-1,y-1,3,3,11)
    pixels[170] = [1]*256   # the guard line (VRAM 170 - scroll .. 171)
    pixels[171] = [1]*256
    return pixels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/world-flight')
    # The world-flight and tile-flight prototypes are retired; only the mission
    # renderer remains. Its scenarios need the debug profile's R/T controls.
    parser.add_argument('--project', choices=['mission-flight'], default='mission-flight')
    parser.add_argument('--debug-profile', action='store_true', help='use mission-flight-debug ROM with renderer test controls (required)')
    parser.add_argument('--weapons', action='store_true', help='exercise gunfire, bombs, impacts and live ammunition')
    parser.add_argument('--headless', action='store_true', help='disable graphics; verify VRAM and timing without raster screenshots')
    args = parser.parse_args()
    if args.project=='mission-flight' and not args.debug_profile:
        parser.error('mission renderer scenarios require --debug-profile; build mission-flight-debug first')
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
    rom_project='mission-flight-debug' if args.debug_profile else args.project
    env['WINGS_ROM_PROJECT']=rom_project
    env['WINGS_WEAPONS'] = '1' if args.weapons else '0'
    env['WINGS_HEADLESS'] = '1' if args.headless else '0'
    rom = ROOT / f'out/{rom_project}/{rom_project}.rom'
    rom_bytes = rom.read_bytes()
    import re
    symbols = dict((name, int(value, 16)) for name, value in re.findall(
        r'DEF _(\w+) (0x[0-9A-Fa-f]+)', rom.with_suffix('.noi').read_text()))
    assert 0x4000 <= symbols['Scenery_Read'] < symbols['Scenery_ReadEnd'] < 0x6000
    folder = ROOT / 'assets_msx/mission_a'
    terrain = json.loads((folder / 'manifest.json').read_text())
    background = (folder / 'scene.indices').read_bytes()
    # The terrain (tools/convert_mission.py): tile strips from bank 32, the
    # column map from bank 40.
    tiles = (folder / 'tiles.sc5').read_bytes()
    assert len(rom_bytes) == 524288
    assert rom_bytes[terrain['tile_banks'][0] * 8192:][:len(tiles)] == tiles, 'incorrect tile bank placement'
    tile_map = (folder / 'map.bin').read_bytes()
    assert rom_bytes[terrain['map_banks'][0] * 8192:][:len(tile_map)] == tile_map, 'incorrect map bank placement'
    tables=(ROOT/'assets_msx/dashboard/bank_7.bin').read_bytes()
    assert rom_bytes[7*8192:7*8192+len(tables)]==tables
    # Aircraft pixels (convert_hellcat.AIRCRAFT_BANKS, as mission-flight.js).
    aircraft_bytes = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']['pixel_bytes']
    for segment in range((aircraft_bytes + 8191) // 8192):
        bank = aircraft_bank(segment)
        data = (ROOT / f'assets_msx/hellcat/mission_bank_{bank}.bin').read_bytes()
        assert rom_bytes[bank*8192:bank*8192+len(data)] == data, ('aircraft bank', bank)
    assert rom_bytes[11*8192:11*8192+6336] == (ROOT / 'assets_msx/dashboard/waves.sc5').read_bytes()
    with (output / 'openmsx.log').open('w') as log:
        cartridge = ['-cart', str(rom), '-romtype', 'ASCII8']
        settings = []
        if args.headless:
            config = output / 'headless.xml'
            config.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings><setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting></settings></settings>')
            settings = ['-setting', str(config)]
        with subprocess.Popen([args.emulator, '-control', 'stdio', *settings, '-machine', args.machine, *cartridge,
                        '-script', str(ROOT / 'tools/world_flight_smoke.tcl')],
                       env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                       stdin=subprocess.PIPE) as emulator:
            try:
                assert emulator.wait(timeout=150)==0, 'openMSX failed'
            except subprocess.TimeoutExpired:
                emulator.kill(); emulator.wait(); raise
    assert rom.read_bytes() == rom_bytes, 'ROM changed during verification; rebuild first, then rerun'
    report = (output / 'emulator-report.txt').read_text()
    assert report.rstrip().endswith('PASS'), report[-2000:]
    scene = AircraftScene()
    scene.palette = (folder / 'palette.bin').read_bytes()
    world_width = terrain['source_width']
    initial_x = terrain['reset_x']
    snapshots, renders, intervals, colors = {}, [], [], {}
    from convert_dashboard import dashboard_palette
    instrument_palette = dashboard_palette()
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
            scale, wave, pilot = views[name]
            view_world = world // scale
            assert camera == max(0, min((world_width + scale - 1) // scale - 256, view_world - 128)), name
            assert x == view_world - camera and pair in (0, 1), name
            snapshots[name] = dict(camera=camera, world=world, x=x, y=y, frame=frame, pair=pair, turning=turning, scale=scale, wave=wave, pilot=pilot)
            heave, ship_frame = ships[name]
            projectiles = []
            stock,weapon,lives = 30,0,3
            snapshots[name].update(heave=heave,ship_frame=ship_frame)
            combat=(output/f'{name}.combat').read_bytes()
            assert len(combat)==160
            for i in range(18):
                values=struct.unpack_from('<HHbbBB',combat,i*8)
                projectiles.append(dict(zip(('x','y','vx','vy','life','kind'),values)))
            game=(output/f'{name}.game').read_bytes()
            assert game[0]==3, (name,'renderer harness requires playing/debug profile')
            lives,weapon,stock=game[2:5]
            shots,dropped,impacts=struct.unpack_from('<HHH',combat,152)
            snapshots[name].update(stock=stock,weapon=weapon,lives=lives,shots=shots,dropped=dropped,impacts=impacts,
                                   projectiles=projectiles,flash=combat[158],aim_pitch=combat[151])
            assert stock+dropped==30 and lives==3

            regs = (output / f'{name}.regs').read_bytes()
            assert regs[0] & 14 == 6 and regs[1] & 64 and regs[9] & 128, (name, 'SCREEN 5 display/212-line mode')
            assert regs[25] & 3 == 2 and (regs[2] >> 5) & 3 == pair, name
            assert regs[26] == (((camera & 255) + 7) // 8) & 63 and regs[27] == (-camera) % 8, name
            assert (output / f'{name}.palette').read_bytes() == scene.palette, name
            vram = (output / f'{name}.vram').read_bytes()
            assert (output / f'{name}.rom').read_bytes() == rom_bytes[:32768], (name, 'cartridge bank restoration')
            # The tile cache: every loaded slot holds its strip of 8 tiles
            # (256 bytes) as 64 rows of 4 bytes at rows 180.. of page 2 or 3.
            if args.project == 'mission-flight':
                for slot, strip in enumerate((output / f'{name}.slots').read_bytes()):
                    if strip == 255: continue
                    got = b''.join(vram[0x10000 + ((slot >> 5) * 256 + 180 + row) * 128 + (slot & 31) * 4:][:4] for row in range(64))
                    assert got == tiles[strip * 256:strip * 256 + 256], (name, 'terrain cache corrupted', slot, strip)
            for shape in scene.frames:
                if shape.get('streamed') or shape.get('unused'):continue
                source = (scene.folder / shape['file']).read_bytes()
                stride = shape['width'] // 2
                for row in range(shape['height']):
                    address = (shape['atlas_y'] + row) * 128 + shape['atlas_x'] // 2
                    assert vram[address:address + stride] == source[row * stride:(row + 1) * stride], (name, 'atlas corrupted')
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
            bomb_pixels = (ROOT/'assets_msx/dashboard/bombs.indices').read_bytes()
            for index,(sx,sy) in enumerate(far_meta['bomb_slots']):
                for row in range(6):
                    line=bomb_pixels[index*48+row*8:index*48+(row+1)*8]
                    packed=bytes((line[x]<<4)|line[x+1] for x in range(0,8,2))
                    address=(sy+row)*128+sx//2
                    assert vram[address:address+4]==packed,(name,'bomb atlas',index,row)
            far_pixels = (ROOT / 'assets_msx/dashboard/far-plane.indices').read_bytes()
            for index, pose in enumerate(far_meta['far_poses']):
                for row in range(5):
                    address = (pose['atlas_y'] + row)*128 + pose['atlas_x']//2
                    pixels = far_pixels[index*80+row*16:index*80+(row+1)*16]
                    packed = bytes((pixels[x]<<4)|pixels[x+1] for x in range(0,16,2))
                    assert vram[address:address+8] == packed, (name,'reduced aircraft atlas',pose['name'])
            expected = expected_pixels(scene, frame, world, y, camera, (folder / 'far.indices').read_bytes() if scale == 8 else background, terrain['far_width'] if scale == 8 else terrain['width'], scale, wave, pilot, heave, ship_frame, projectiles, stock, weapon, lives, flash=snapshots[name].get('flash', 0))
            fine = 0   # the renderer harness never flies inside the pan band
            assert not pan_of(y, scale), (name, 'pan band snapshot needs the fine scroll')
            assert regs[0] & 16 and regs[19] in ({(170-heave-fine) % 256, 174} | ({fine - min(fine, 2)} if fine > 0 else set())), (name, 'dashboard split IRQ', regs[19])
            for row in range(212):
                for col in range(8, 256):
                    ring = (col if row >= 172 else camera + col) % 256
                    source_row = vram_row(row, fine, heave) if row < 172 else row
                    address = pair * 32768 + source_row * 128 + (ring % 256) // 2
                    actual = vram[address] & 15 if ring % 2 else vram[address] >> 4
                    assert actual == expected[row][col], (name, 'VRAM', col, row, actual, expected[row][col])
            if args.headless:
                vram_image(vram, scene.palette, camera, pair, heave).save(output / f'{name}-vram.png')
                continue
            image = Image.open(output / f'{name}.png').convert('RGB')
            assert image.size == (320, 240), (name, image.size)
            pixels = image.load()
            for row in range(212):
                for col in range(256):
                    # The 8-pixel scroll mask shows the border colour (R#7 = 1, TP set).
                    index = expected[row][col] if col >= 8 else 1
                    rgb = pixels[32 + col, 14 + row]
                    palette = scene.palette
                    if row >= 176:
                        palette = instrument_palette
                    # A palette entry can have different colors above/below
                    # the split. Track actual RGB3 values across both rasters.
                    color = palette[index*2:index*2+2]
                    if color not in colors:
                        assert rgb not in colors.values(), (name, 'collapsed palette', color, rgb)
                        colors[color] = rgb
                    assert rgb == colors[color], (name, 'raster', col, row, index, rgb)
    required = {'initial', 'terrain_flight', 'aircraft_page_seam', 'aircraft_ring_seam',
                'right_bound', 'left_climb', 'top_clipped', 'left_bound', 'reset', 'stationary_turn'}
    required.update(f'fine_{phase}' for phase in range(8))
    assert required <= snapshots.keys(), required - snapshots.keys()
    assert snapshots['initial']['world'] == initial_x
    assert snapshots['initial']['camera'] == max(0, min(world_width - 256, initial_x - 128))
    assert snapshots['terrain_flight']['y'] == 1200
    assert snapshots['right_bound']['world'] == world_width - 1
    assert snapshots['left_bound']['world'] == 0
    assert snapshots['top_clipped']['y'] == 0
    assert snapshots['reset']['world'] == world_width - 1 and snapshots['reset']['y'] == 1108
    assert {s['pair'] for s in snapshots.values()} == {0, 1}
    assert {'carrier_tower', 'dugout_1', 'hut_1', 'hut_2', 'dugout_2', 'island_coast','distant_island'} <= snapshots.keys(), 'missing source-backed map landmarks'
    assert {s['scale'] for s in snapshots.values()} == {1,8}
    assert snapshots['distant_island']['scale']==8
    assert 3880<=snapshots['distant_island']['world']<=4100
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
    period_ticks = 8
    target_fps = (50 if pal else 60) / period_ticks
    target = 1000 / target_fps
    assert len(intervals) > int(target_fps * 110) and len(renders) > int(target_fps * 90)
    assert hidden_checks == len(renders) + len(transitions)
    periods=[1000*(period_ticks+extra)/(50 if pal else 60) for extra in ((0,2) if args.weapons else (0,))]
    assert all(any(abs(interval-period)<2 for period in periods) for interval in intervals), (min(intervals),max(intervals),periods)
    assert max(renders) < target
    summary = dict(machine=args.machine, project=args.project, debug_profile=args.debug_profile, raster_checked=not args.headless, rom_sha256=hashlib.sha256(rom_bytes).hexdigest(),
                   target_fps=target_fps, presentation_vblanks=period_ticks, publication_samples=len(intervals),
                   publication_ms=dict(min=min(intervals), median=statistics.median(intervals), max=max(intervals)),
                   redraw_samples=len(renders), view_transition_ms=transitions,
                   redraw_ms=dict(min=min(renders), median=statistics.median(renders), max=max(renders)),
                   missed_deadlines=0, hidden_page_checks=hidden_checks, snapshots=snapshots,
                   checks=['full visible VRAM'+(' and completed raster' if not args.headless else ' (raster not captured)'), 'transparent aircraft and trail restoration',
                           'bounded world flight and camera following', 'all fine-scroll phases',
                           'aircraft page/ring seams', 'turns and vertical clipping',
                           'both world bounds and reset', 'immutable visible page during every redraw',
                           'immutable aircraft atlas', f'{target_fps:g} Hz VBlank publication'])
    summary['terrain_bundle_sha256'] = terrain['bundle_sha256']
    summary['checks'] += ['immutable terrain tile cache', 'actual mapper-bank restoration',
                          'original-art authored scene at every visible pixel']
    summary['source_map_sha256'] = terrain['source_sha256']
    summary['checks'] += ['source-backed a.map landmarks and reset position', 'compressed 16-bit tile-ID columns', 'runtime source surface/object queries',
                          'fixed original-art dashboard and split scrolling', 'aircraft clipped above dashboard',
                          'aircraft banks 8-10 and 14, wave bank 11', 'altitude-selected 1:8 original scenery',
                          'original twelve-frame water animation', 'forward pilot display with fixed reticle']
    if args.weapons:
        assert {'weapon_2','weapon_3','weapon_2_far'} <= snapshots.keys(), 'missing weapon coverage'
        flash_shots = [n for n in ('gun_flash_1', 'gun_flash_2') if n in snapshots]
        assert flash_shots, 'no cannon flash snapshot'
        for name in flash_shots:
            shot = snapshots[name]
            assert gun_flash_shape(scene, shot['frame'], shot['flash']), (name, 'flash overlay not drawn')
        # Publication log while firing: the renderer alternates fa/fb per presented frame.
        flashes = [tuple(map(int, line.split()[1:])) for line in report.splitlines() if line.startswith('flash ')]
        assert {v for _, v, _ in flashes} == {1, 2}, ('fa/fb overlays not both presented', flashes[:12])
        consecutive = [(a, b) for (n0, a, _), (n1, b, held) in zip(flashes, flashes[1:]) if n1 == n0 + 1 and not held]
        assert consecutive and all(a != b for a, b in consecutive), ('overlay did not alternate per frame', consecutive[:12])
        assert sum(p['kind']==2 for p in snapshots['bomb_salvo']['projectiles'])>=8
        assert {'bomb_pose_0','bomb_pose_1','bomb_pose_2'} <= snapshots.keys(), 'missing bomb orientation coverage'
        assert snapshots['reset']['stock']==30 and snapshots['reset']['weapon']==0
        summary['checks'] += ['original fa/fb cannon flash overlays on the drawn pose', 'gun strikes and bombs in close/distant views', 'terrain impact flashes',
                              'original horizontal/diagonal/vertical bomb poses and immutable cache',
                              'projectile trails, overlap and clipping', 'secondary stock and debug reset']
        summary['weapons'] = dict(max_shots=max(s['shots'] for s in snapshots.values()),
                                  max_impacts=max(s['impacts'] for s in snapshots.values()))
    if args.headless:
        summary['checks'][0] = 'full visible VRAM; raster screenshots not checked (headless renderer)'
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: {len(snapshots)} snapshots; max redraw {max(renders):.2f} ms')


if __name__ == '__main__':
    main()
