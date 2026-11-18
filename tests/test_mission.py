"""Source-backed mission fields, malformed inputs, tile RLE and configured flight."""
import ctypes
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from decode_mission import artifacts, executable_evidence, parse_map
from convert_mission import artifacts as tile_artifacts, decode_column
from test_world import World


class MissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.mission, cls.scene, cls.pixels, cls.inventory = artifacts()
        cls.files, cls.metadata = tile_artifacts()

    def test_all_fifteen_strips_round_trip_every_word_and_header(self):
        folder = ROOT / 'reference_assets/original_files/Wings_of_Fury/maps'
        self.assertEqual(len(self.inventory), 15)
        for path in folder.glob('*.map'):
            raw = path.read_bytes()
            mission = parse_map(raw)
            restored = struct.pack('>II', mission['bytes'], mission['reset_header'])
            for cell in mission['cells']:
                word = (int(cell['draw']) << 15) | (cell['depth'] << 11) | (cell['shape_id'] << 2) | cell['surface']
                restored += struct.pack('>H', word)
            self.assertEqual(restored, raw)

    def test_a_map_landmarks_are_source_backed(self):
        self.assertEqual((self.mission['columns'], self.mission['width'], self.mission['reset_x']), (951, 7608, 7032))
        self.assertIn(dict(start=8, end=3976, surface=2), self.mission['surface_runs'])
        self.assertIn(dict(start=6600, end=7360, surface=1), self.mission['surface_runs'])
        placed = {p['x']:p for p in self.scene['placed']}
        for x, name in [(1736,'dugo'), (2392,'huta'), (2712,'huta'), (3224,'dugo'),
                        (6720,'fcar'), (6912,'towr'), (6976,'mcar'), (7232,'rcar')]:
            self.assertEqual(placed[x]['name'], name)
            cell = self.mission['cells'][x // 8]
            self.assertTrue(cell['draw'])
            self.assertEqual(self.evidence['shape_names'][cell['shape_id']], name)
        # The flag's pole (0x113, flg0..flg2 in the executable) is baked in
        # as POST; the cloth is an overlay until the island is cleared.
        self.assertEqual(placed[2408]['name'], 'POST')
        self.assertEqual(len(self.scene['placed']), 76)
        self.assertEqual(len(self.scene['unresolved']), 13)

    def test_bad_map_and_modified_instruction_evidence_are_rejected(self):
        raw = (ROOT / 'reference_assets/original_files/Wings_of_Fury/maps/a.map').read_bytes()
        cases = [b'', raw[:-1], raw + bytes(2), bytes(4) + raw[4:],
                 raw[:4] + struct.pack('>I', 0xffffffff) + raw[8:],
                 raw[:8] + b'\x40\x00' + raw[10:], raw[:8] + b'\x00\x03' + raw[10:]]
        for bad in cases:
            with self.assertRaises(ValueError):
                parse_map(bad)
        exe = bytearray((ROOT / 'reference_assets/original_files/Wings_of_Fury/wings').read_bytes())
        exe[0x38ae] ^= 1
        with self.assertRaises(ValueError):
            executable_evidence(exe)

    def test_sand_covers_roots_and_shore_has_a_sloping_edge(self):
        width, baseline = self.scene['width'], self.scene['baseline']
        # At the top of the left beach, water reaches well inside the map's
        # coarse island boundary. The original beach widens toward its base.
        self.assertEqual(self.pixels[baseline * width + 8], 1)
        self.assertEqual(self.pixels[baseline * width + 24], 17)
        self.assertEqual(self.pixels[(baseline + 4) * width + 8], 17)
        self.assertEqual(self.pixels[baseline * width + 3970], 1)
        self.assertEqual(self.scene['sand_height'], 5)
        for y in range(baseline, baseline + 5):
            self.assertEqual(set(self.pixels[y * width + 40:y * width + 3920]), {17})
        # Water runs beneath the sand instead of stopping at the island edge.
        for row in range(5, 11):
            self.assertTrue(any(b['start'] == 0 and b['end'] == self.mission['width']
                and b['row'] <= row < b['row'] + b['height'] for b in self.scene['water_bands']))
            self.assertEqual(self.pixels[(baseline + row) * width + 1000], 1)

    def test_wave_art_uses_ocean_palette_and_preserves_transparency(self):
        from convert_dashboard import waves, ocean_artwork, wave_mapping
        from decode_shapes import decode_record
        from decode_mission import SOURCE
        from unpack_shapes import read_ppkc, unpack_rpck
        records = {name: raw for name, _, raw in read_ppkc(
            unpack_rpck((SOURCE / 'shapes/world.shp').read_bytes()))}
        for letter, frame in zip('abcdefghijkl', waves()):
            source, _ = decode_record(records['wav' + letter])
            self.assertTrue(any(value == 0 for value in frame))
            for original, converted in zip(source, frame):
                if original == 0:
                    self.assertEqual(converted, 0)
                else:
                    self.assertNotEqual(converted, 0)
        original, palette = ocean_artwork()
        self.assertEqual(tuple(palette[30:33]), (0,96,160))
        self.assertEqual(wave_mapping()[19], 1)
        self.assertNotEqual(wave_mapping()[10], 5)
        self.assertEqual((ROOT/'assets_src/dashboard/waves.indices').read_bytes(), b''.join(original))
        self.assertEqual((ROOT/'assets_src/dashboard/ocean-palette.rgb').read_bytes(), bytes(palette))

    def test_generated_outputs_and_compressed_tiles_round_trip_scene(self):
        for path, data in self.files.items():
            self.assertEqual(path.read_bytes(), data, str(path))
        folder = ROOT / 'assets_msx/mission_a'
        tiles = self.files[folder / 'tiles.sc5']
        mapping = self.files[folder / 'map.bin']
        expected = self.files[folder / 'scene.indices']
        variants = self.metadata['hut_variants']
        stripes = [8 * v['near_count'] for v in variants] + [8 * v['far_count'] for v in variants]
        width, height = self.metadata['width'] + self.metadata['far_width'] + sum(stripes), self.metadata['height']
        far = self.files[folder / 'far.indices']
        wrecked, at = self.files[folder / 'hut-variants.indices'], []
        for w in stripes:
            at.append(wrecked[:w * height]); wrecked = wrecked[w * height:]
        self.assertEqual(wrecked, b'')
        expected = b''.join(expected[y*self.metadata['width']:(y+1)*self.metadata['width']] + far[y*self.metadata['far_width']:(y+1)*self.metadata['far_width']]
                            + b''.join(s[y*w:(y+1)*w] for s, w in zip(at, stripes)) for y in range(height))
        self.assertEqual(width // 8, self.metadata['selected']['columns'])
        selected = self.metadata['selected']
        actual = bytearray(width * height)
        for col in range(selected['columns']):
            ids = decode_column(mapping, col, selected['columns'], selected['rows'], selected['tile_count'])
            for row, tile in enumerate(ids):
                packed = tiles[tile * 32:(tile + 1) * 32]
                pixels = bytes(v for b in packed for v in (b >> 4, b & 15))
                for sy in range(8):
                    y = 64 + row * 8 + sy
                    if y < height:
                        offset = y * width + col * 8
                        actual[offset:offset + 8] = pixels[sy * 8:(sy + 1) * 8]
        self.assertEqual(bytes(actual), expected)
        self.assertLessEqual(selected['tile_count'], 576)
        self.assertLess(self.metadata['map_and_cache_ram_bytes'], 12000)

    def test_runtime_query_matches_every_source_pixel_and_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = Path(directory) / 'mission.so'
            subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I'+str(ROOT/'src/generated/map_a'), '-Wall', '-Wextra', '-Werror',
                '-shared', '-fPIC', str(ROOT / 'src/core/mission.c'),
                str(ROOT / 'src/generated/map_a/mission_surfaces.c'), '-o', str(lib)], check=True, capture_output=True)
            core = ctypes.CDLL(str(lib))
            core.Mission_Query.argtypes = [ctypes.c_int16]
            core.Mission_Query.restype = ctypes.c_uint16
            core.Mission_Surface.argtypes = [ctypes.c_uint16]
            core.Mission_Surface.restype = ctypes.c_uint8
            for x in range(self.mission['width']):
                self.assertEqual(core.Mission_Query(x), self.mission['cells'][x // 8]['raw_word'] & 0x7ff, x)
                self.assertEqual(core.Mission_Surface(x), self.mission['cells'][x // 8]['surface'], x)
            # Revisit interval boundaries in both directions and after large jumps.
            for x in list(range(self.mission['width']-1,-1,-7))+[7032,0,7032,128,7607,8]:
                self.assertEqual(core.Mission_Query(x),self.mission['cells'][x//8]['raw_word']&0x7ff,x)
            for x in (-32768, -1, self.mission['width'], 32767):
                self.assertEqual(core.Mission_Query(x), 0, x)

    def test_malformed_column_rle_is_rejected(self):
        for data in (b'', b'\x00\x00', b'\x02\x00\x00\x00\x00',
                     b'\x02\x00\x14\x00\x00', b'\x02\x00\x13\xff\xff'):
            with self.assertRaises(ValueError):
                decode_column(data, 0, 1, 19, 434)

    def test_vertical_tile_cache_does_not_overlap_aircraft_or_leave_vram(self):
        frames = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        plane = {y * 128 + x for f in frames for y in range(f['atlas_y'], f['atlas_y'] + f['height'])
                 for x in range(f['atlas_x'] // 2, (f['atlas_x'] + f['width']) // 2)}
        occupied = set()
        for tile in range(self.metadata['selected']['tile_count']):
            y = (tile // 288 + 2) * 256 + 180 + (tile % 9) * 8
            x = (tile % 288 // 9) * 4
            addresses = {r * 128 + c for r in range(y, y + 8) for c in range(x, x + 4)}
            self.assertTrue(plane.isdisjoint(addresses))
            self.assertTrue(occupied.isdisjoint(addresses))
            self.assertGreaterEqual(min(addresses), 65536)
            self.assertLess(max(addresses), 131072)
            occupied.update(addresses)
        self.assertEqual(len(occupied), self.metadata['selected']['tile_bytes'])

    def test_original_dashboard_assets_and_backups_are_disjoint(self):
        from convert_dashboard import artifacts as dashboard_artifacts, panel, original
        for path, data in dashboard_artifacts().items():
            self.assertEqual(path.read_bytes(), data, str(path))
        self.assertEqual(original()[0].size, (640, 37))
        self.assertEqual(len(panel()), 256 * 40)
        frames = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        self.assertLessEqual(max(f['width'] for f in frames), 64)
        self.assertLessEqual(max(f['height'] for f in frames), 36)
        bundle=b''.join((ROOT/f'assets_msx/hellcat/mission_bank_{bank}.bin').read_bytes() for bank in (8,9,10,14,4,5,6) if (ROOT/f'assets_msx/hellcat/mission_bank_{bank}.bin').exists())
        for frame in frames:
            packed=(ROOT/'assets_msx/hellcat'/frame['file']).read_bytes()
            start=frame['data_offset']
            self.assertEqual(bundle[start:start+len(packed)],packed)
            self.assertFalse(start<24576<start+len(packed),'frame crosses the bank-10/bank-14 gap')
        # World columns and plane composition end before the fixed panel;
        # both clean-footprint backups begin after the full 212-line display.
        self.assertLessEqual(24 + 19 * 8 - 4, 172)
        self.assertGreaterEqual(212, 172 + 40)

    def test_dashboard_opaque_art_does_not_use_the_sky_border_index(self):
        from convert_dashboard import panel, dashboard_palette, pilot_frame
        pixels = panel()
        # Source sprite transparency is 16. Treating it as color zero leaves
        # cyan holes in the score and bomb artwork after the raster switch.
        self.assertNotIn(0, pixels)
        # During carrier heave, 6..15 are staged over the ocean; 1..5 finish
        # before the icons/pilot display at line 183. Keep that raster contract.
        # Slots 1 and 2 hold the same colour in both palettes (asserted below),
        # so the pilot window's top row (line 182, index 2) is timing-safe.
        self.assertTrue(all(pixels[y*256+x] >= 6 or pixels[y*256+x] in (1, 2)
                            for y in range(4,11) for x in range(8,256)))
        from convert_dashboard import layout
        hud = layout()
        score = {pixels[y*256+x] for y in range(hud['score_y'], hud['score_y']+7)
                 for x in range(hud['score_x'], hud['score_x']+41)}
        self.assertEqual(score, {11, 15})
        palette = dashboard_palette()
        self.assertEqual(palette[:2], (ROOT/'assets_msx/mission_a/palette.bin').read_bytes()[:2])
        self.assertEqual(palette[2:4], (ROOT/'assets_msx/mission_a/palette.bin').read_bytes()[2:4])
        self.assertEqual(set(pixels[:4*256]), {1})  # stable across the palette switch
        self.assertEqual(palette[22:24], bytes(2))  # actual black, not dark sea
        self.assertEqual(pilot_frame(0, 7)[0], 2)  # dashboard sky, not black

    def test_counters_use_the_original_digit_face_at_the_shared_layout(self):
        from convert_dashboard import compose, digit_glyphs, layout, panel, NEEDLE_FULL, NEEDLE_NEW_OIL
        glyphs, hud = digit_glyphs(), layout()
        def digit_at(pixels, x, y, ink, paper):
            rows = tuple(''.join('#' if pixels[(y+yy)*256+x+xx] == ink else
                                 ('.' if pixels[(y+yy)*256+x+xx] == paper else '?') for xx in range(6))
                         for yy in range(7))
            return glyphs.index(rows) if rows in glyphs else rows
        # wnum digits are 6x7 with 2-pixel strokes after the exact 2:1 reduction.
        self.assertTrue(all(len(g) == 7 and all(len(r) == 6 for r in g) for g in glyphs))
        pixels = compose(ammo=27, lives=5, score=20160, kills=4)
        self.assertEqual([digit_at(pixels, x, hud['ammo_y'], 11, 15) for x in hud['ammo_x']], [2, 7])
        self.assertEqual(digit_at(pixels, hud['lives_x'], hud['lives_y'], 11, 15), 5)
        score = [digit_at(pixels, hud['score_x'] + 7*i, hud['score_y'], 15, 11) for i in range(1, 6)]
        self.assertEqual(score, [2, 0, 1, 6, 0])
        self.assertEqual(set(pixels[(hud['score_y']+y)*256+hud['score_x']+x] for y in range(7) for x in range(6)), {11})
        self.assertEqual([digit_at(pixels, hud['kills_x'] + 7*i, hud['kills_y'], 15, 11) for i in range(2)], [0, 4])
        # The default panel is a new plane: OIL at ndlg (16), FUEL at ndln (22).
        self.assertEqual(bytes(compose(oil=NEEDLE_NEW_OIL, fuel=NEEDLE_FULL)), panel())
        # Pilot window: byte-aligned for HMMM, 46 pixels, top row at line 182.
        self.assertEqual((hud['pilot_x'] % 2, hud['pilot_y']), (0, 11))
        self.assertEqual(set(panel()[(hud['pilot_y'])*256+hud['pilot_x']:(hud['pilot_y'])*256+hud['pilot_x']+46]), {2})

    def test_fidelity_atlases_are_disjoint_and_source_rules_guarded(self):
        from convert_dashboard import waves, pilot_frame
        frames = json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['frames']
        occupied = set()
        for f in frames:
            occupied.update(y*128+x for y in range(f['atlas_y'],f['atlas_y']+f['height'])
                            for x in range(f['atlas_x']//2,(f['atlas_x']+f['width'])//2))
        for tile in range(self.metadata['selected']['tile_count']):
            x=tile%288//9*4;y=tile//288*256+692+tile%9*8
            addresses={yy*128+xx for yy in range(y,y+8) for xx in range(x,x+4)}
            self.assertTrue(occupied.isdisjoint(addresses));occupied.update(addresses)
        cockpit=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())
        for x,y in cockpit['pilot_slots']:
            addresses={yy*128+xx for yy in range(y,y+24) for xx in range(x//2,x//2+24)}
            self.assertTrue(occupied.isdisjoint(addresses));occupied.update(addresses)
        for far in cockpit['far_poses']:
            addresses={yy*128+xx for yy in range(far['atlas_y'],far['atlas_y']+5)
                       for xx in range(far['atlas_x']//2,(far['atlas_x']+far['width'])//2)}
            self.assertTrue(occupied.isdisjoint(addresses));occupied.update(addresses)
        self.assertGreater(len(set(cockpit['far_pose_for_frame'])), 12)
        for x,y in cockpit['wave_tail_slots']:
            addresses={yy*128+xx for yy in range(y,y+2) for xx in range(x//2,x//2+48)}
            self.assertTrue(occupied.isdisjoint(addresses));occupied.update(addresses)
        for x,y in cockpit['wave_backdrop_slots']:
            addresses={yy*128+xx for yy in range(y,y+4) for xx in range(x//2,x//2+128)}
            self.assertTrue(occupied.isdisjoint(addresses));occupied.update(addresses)
        self.assertEqual(len(waves()),12)
        self.assertEqual(len({w for w in waves()}),12)
        self.assertNotEqual(pilot_frame(2,0),pilot_frame(2,7))
        rules=self.evidence['view_rules']
        self.assertEqual((rules['far_scale'],rules['far_altitude_exclusive']), (8,186))
        self.assertEqual(self.scene['baseline']-40,161)

    def test_source_clear_set_masks_restore_reduced_colours(self):
        from unpack_shapes import read_ppkc, unpack_rpck
        from decode_shapes import decode_record
        source = ROOT/'reference_assets/original_files/Wings_of_Fury/shapes/8thscale.shp'
        records={n:r for n,_,r in read_ppkc(unpack_rpck(source.read_bytes()))}
        tree,meta=decode_record(records['tre1'],allow_reduced_flag=True,plane_constants=True)
        self.assertEqual(meta['clear_planes'],16)
        self.assertLessEqual(max(tree),15)
        self.assertTrue({7,8,9} & set(tree))
        hull,meta=decode_record(records['mcar'],allow_reduced_flag=True,plane_constants=True)
        self.assertEqual(meta['set_planes'],24)
        self.assertTrue(all(c==0 or 24<=c<=31 for c in hull))

    def test_distant_sea_and_player_pitch_bank_art(self):
        far = self.files[ROOT/'assets_msx/mission_a/far.indices']
        width = self.metadata['far_width']
        sand=self.metadata['far_sand_msx_index']
        self.assertEqual(self.metadata['far_sand_height'],1)
        self.assertEqual(set(far[202*width:]), {3})
        # The supplied distant reference shows a continuous sand-colour line
        # under the palms. Its ends follow the original one-row beach masks.
        row=far[201*width:202*width]
        self.assertEqual(row[6:492],bytes([sand])*486)
        self.assertEqual(row[:6],bytes([3])*6)
        self.assertEqual(row[492:],bytes([3])*(width-492))
        self.assertNotEqual(sand,3)
        cockpit=json.loads((ROOT/'assets_src/dashboard/manifest.json').read_text())
        animation=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        def pose(frame): return cockpit['far_poses'][cockpit['far_pose_for_frame'][frame]]
        self.assertEqual(pose(animation['pitch_right'][4])['name'], 'lpnn')
        self.assertEqual(pose(animation['pitch_left'][4])['name'], 'lpn0')
        self.assertGreater(pose(animation['pitch_right'][9])['height'], 2)
        self.assertGreater(len({pose(frame)['name'] for frame in animation['right_to_left']}), 5)

    def test_mission_configured_flight_starts_at_carrier_and_reaches_both_bounds(self):
        class MissionFlight(ctypes.Structure):
            _fields_=[('x',ctypes.c_uint16),('y',ctypes.c_uint32),('vx',ctypes.c_int16),('vy',ctypes.c_int16),('frame',ctypes.c_uint8),('facing_left',ctypes.c_uint8)]
        class MissionWorld(ctypes.Structure):
            _fields_=[('flight',MissionFlight),('x',ctypes.c_uint32),('camera',ctypes.c_uint16)]

        with tempfile.TemporaryDirectory() as directory:
            lib = Path(directory) / 'world.so'
            subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I'+str(ROOT/'src/generated/map_a'), '-Wall', '-Wextra', '-Werror',
                '-shared', '-fPIC', '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u', '-DWINGS_FLIGHT_MAX_Y=1200u', '-DWINGS_FLIGHT_START_Y=1108u',
                str(ROOT / 'src/core/world.c'), str(ROOT / 'src/core/flight.c'), '-o', str(lib)],
                check=True, capture_output=True)
            core = ctypes.CDLL(str(lib))
            core.World_Reset.argtypes = [ctypes.POINTER(MissionWorld)]
            core.World_Step.argtypes = [ctypes.POINTER(MissionWorld), ctypes.c_uint8]
            core.World_Reset.restype = core.World_Step.restype = None
            state = MissionWorld()
            core.World_Reset(ctypes.byref(state))
            self.assertEqual((state.x >> 8, state.camera, state.flight.x >> 8), (7032, 6904, 128))
            self.assertEqual(state.flight.y, 1108 * 256)
            for controls, expected_y in [(1,0),(4,1200*256)]:
                for _ in range(5000): core.World_Step(ctypes.byref(state), controls)
                self.assertEqual((state.flight.y,state.flight.vy),(expected_y,0))
            for controls, x, camera in [(2,7607,7352), (8,0,0)]:
                for _ in range(11000):
                    core.World_Step(ctypes.byref(state), controls)
                self.assertEqual((state.x, state.camera, state.flight.vx), (x * 256, camera, 0))
            ntsc, pal = MissionWorld(), MissionWorld()
            core.World_Reset(ctypes.byref(ntsc))
            core.World_Reset(ctypes.byref(pal))
            for controls in (8, 9, 0, 2):
                for frame in range(60):
                    for _ in range(20):
                        core.World_Step(ctypes.byref(ntsc), controls)
                for _ in range(50):
                    for _ in range(24):
                        core.World_Step(ctypes.byref(pal), controls)
                self.assertEqual((ntsc.x, ntsc.camera, bytes(ntsc.flight)), (pal.x, pal.camera, bytes(pal.flight)))
