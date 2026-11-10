import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from map_aircraft import mapping
from decode_shapes import decode_record
from aircraft_scene import AircraftScene


class Aircraft(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint8) for name in ('facing_left', 'target_left', 'turning', 'step', 'tick', 'shape')]


class AircraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name) / 'aircraft.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT / 'src/core/aircraft.c'), str(ROOT / 'src/generated/hellcat_frames.c'),
                        '-o', str(library)], capture_output=True, check=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.Aircraft_Reset.argtypes = [ctypes.POINTER(Aircraft)]
        cls.core.Aircraft_Reset.restype = None
        cls.core.Aircraft_Step.argtypes = [ctypes.POINTER(Aircraft), ctypes.c_int16, ctypes.c_int16]
        cls.core.Aircraft_Step.restype = None
        cls.core.Aircraft_RequestTurn.argtypes = [ctypes.POINTER(Aircraft)]
        cls.core.Aircraft_RequestTurn.restype = None
        cls.core.Aircraft_Pitch.argtypes = [ctypes.c_int16, ctypes.c_int16]
        cls.core.Aircraft_Pitch.restype = ctypes.c_uint8
        cls.meta = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def state(self):
        state = Aircraft()
        self.core.Aircraft_Reset(ctypes.byref(state))
        return state

    def step(self, state, vx, vy, count=1):
        for _ in range(count):
            self.core.Aircraft_Step(ctypes.byref(state), vx, vy)
        return state

    def test_source_table_evidence(self):
        facts = mapping(ROOT / 'reference_assets/original_files/Wings_of_Fury/wings')
        tables = facts['source_tables']
        self.assertEqual([tables[n]['file_offset'] for n in ('left_bank', 'right_bank', 'pitch')], [0x15d00, 0x15d68, 0x15dd0])
        self.assertEqual([len(tables[n]['names']) for n in ('left_bank', 'right_bank', 'pitch')], [26, 26, 20])
        self.assertEqual(len(self.meta['frames']), 49)

    def test_pitch_response_is_monotonic_and_direction_symmetric(self):
        previous = 0
        for vy in range(-154, 155):
            pitch = self.core.Aircraft_Pitch(150, vy)
            self.assertGreaterEqual(pitch, previous)
            self.assertLess(pitch, 10)
            self.assertEqual(pitch, self.core.Aircraft_Pitch(-150, vy))
            previous = pitch
        self.assertEqual(self.core.Aircraft_Pitch(0, 0), 4)

    def test_turn_plays_data_sequence_and_finishes_in_110_ticks(self):
        state = self.state()
        observed = []
        for _ in range(110):
            self.step(state, -120, 0)
            observed.append(state.shape)
        expected = [index for index in self.meta['right_to_left'] for _ in range(5)]
        self.assertEqual(observed, expected)
        self.assertEqual((state.turning, state.facing_left), (0, 1))
        self.step(state, -120, 0)
        self.assertEqual(state.shape, self.meta['pitch_left'][4])
        observed = []
        for _ in range(110):
            self.step(state, 120, 0)
            observed.append(state.shape)
        self.assertEqual(observed, [i for i in self.meta['left_to_right'] for _ in range(5)])
        self.assertEqual((state.turning, state.facing_left), (0, 0))

    def test_reversal_is_queued_without_restarting_current_turn(self):
        state = self.step(self.state(), -120, 0, 40)
        self.assertEqual(state.step, 8)
        self.step(state, 120, 0, 70)
        self.assertEqual((state.turning, state.facing_left), (0, 1))
        self.step(state, 120, 0)
        self.assertEqual((state.turning, state.facing_left, state.step), (1, 1, 0))
        self.core.Aircraft_Reset(ctypes.byref(state))
        self.assertEqual(bytes(state), bytes(self.state()))

    def test_deadband_does_not_trigger_facing_jitter(self):
        state = self.state()
        for vx in (-16, 0, 16, -5, 5):
            self.step(state, vx, 0, 20)
            self.assertEqual((state.turning, state.facing_left), (0, 0))

    def test_in_place_request_and_queued_request(self):
        state = self.state()
        self.core.Aircraft_RequestTurn(ctypes.byref(state))
        self.step(state, 0, 0, 50)
        self.core.Aircraft_RequestTurn(ctypes.byref(state))
        self.step(state, 0, 0, 60)
        self.assertEqual((state.turning, state.facing_left), (0, 1))
        self.step(state, 0, 0, 110)
        self.assertEqual((state.turning, state.facing_left), (0, 0))

    def test_crops_preserve_opaque_pixels_and_original_pivot_placement(self):
        palette_map = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['source_index_to_msx_index']
        for frame in self.meta['frames']:
            packed = (ROOT / 'assets_msx/hellcat' / frame['file']).read_bytes()
            self.assertEqual(hashlib.sha256(packed).hexdigest(), frame['packed_sha256'])
            decoded = [n for b in packed for n in (b >> 4, b & 15)]
            self.assertEqual(len(decoded), frame['width'] * frame['height'])
            with Image.open(ROOT / frame['source']) as image:
                if frame['mirrored']: image = ImageOps.mirror(image)
                ox, oy = frame['drawing_origin']
                expected = {(25 + x - ox, 16 + y - oy): int(palette_map[str(image.getpixel((x, y)))])
                            for y in range(image.height) for x in range(image.width) if image.getpixel((x, y))}
            actual = {(frame['dx'] + x, frame['dy'] + y): decoded[y * frame['width'] + x]
                      for y in range(frame['height']) for x in range(frame['width']) if decoded[y * frame['width'] + x]}
            self.assertEqual(actual, expected, frame['name'])
            self.assertEqual(frame['dx'] % 2, 0)

    def test_stored_pairs_validate_mirror_origin_rule(self):
        folder = ROOT / 'reference_assets/unpacked_shapes/hellcat'
        for group in ('fa', 'fb'):
            for i in range(1, 11):
                a, ma = decode_record(next(folder.glob(f'*_{group}{i:02x}.bin')).read_bytes())
                b, mb = decode_record(next(folder.glob(f'*_{group}{i+10:02x}.bin')).read_bytes())
                width = ma['width']
                self.assertEqual(b, b''.join(a[y * width:(y + 1) * width][::-1] for y in range(ma['height'])))
                self.assertEqual(ma['origin_candidate'][0] + mb['origin_candidate'][0], width)

    def test_screen_corner_clipping_matches_original_source_pixels(self):
        scene = AircraftScene()
        color_map = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['source_index_to_msx_index']
        for frame in scene.frames:
            with Image.open(ROOT / frame['source']) as image:
                if frame['mirrored']: image = ImageOps.mirror(image)
                ox, oy = frame['drawing_origin']
                points = [(25 + x - ox, 16 + y - oy, int(color_map[str(image.getpixel((x, y)))]))
                          for y in range(image.height) for x in range(image.width) if image.getpixel((x, y))]
            for px, py in ((0, 0), (208, 0), (0, 180), (208, 180)):
                expected = bytearray(32768)
                for x, y, color in points:
                    x, y = x + px, y + py
                    if 0 <= x < 256 and 0 <= y < 212:
                        expected[y * 128 + x // 2] |= color if x & 1 else color << 4
                self.assertEqual(scene.page(frame['id'], px, py), expected, (frame['name'], px, py))
