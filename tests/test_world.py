import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_flight import Flight

ROOT = Path(__file__).resolve().parents[1]


class World(ctypes.Structure):
    _fields_ = [('flight', Flight), ('x', ctypes.c_uint32), ('camera', ctypes.c_uint16)]


class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name) / 'world.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-fPIC', str(ROOT / 'src/core/flight.c'),
                        str(ROOT / 'src/core/world.c'), '-o', str(library)], check=True, capture_output=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.World_Reset.argtypes = [ctypes.POINTER(World)]
        cls.core.World_Step.argtypes = [ctypes.POINTER(World), ctypes.c_uint8]
        cls.core.World_Reset.restype = cls.core.World_Step.restype = None
        cls.core.World_StepSample.argtypes = [ctypes.POINTER(World), ctypes.c_uint8, ctypes.c_uint8]
        cls.core.World_StepSample.restype = None

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def state(self):
        state = World()
        self.core.World_Reset(ctypes.byref(state))
        return state

    def advance(self, state, input, count):
        for _ in range(count):
            self.core.World_Step(ctypes.byref(state), input)
            self.assertLessEqual(state.camera, 3840)
            self.assertEqual(state.flight.x >> 8, (state.x >> 8) - state.camera)

    def test_crosses_8bit_and_ring_coordinates_without_wrapping(self):
        state = self.state()
        self.advance(state, 2, 1500)
        self.assertGreater(state.x >> 8, 1024)
        self.assertEqual(state.flight.x >> 8, 128)
        self.assertGreater(state.camera, 512)

    def test_both_world_bounds_stop_outward_motion(self):
        state = self.state()
        self.advance(state, 2, 6000)
        self.assertEqual((state.x, state.camera, state.flight.vx), (4095 * 256, 3840, 0))
        self.advance(state, 8, 6000)
        self.assertEqual((state.x, state.camera, state.flight.vx), (0, 0, 0))

    def test_pal_ntsc_grouping_is_identical_and_camera_does_not_jump(self):
        ntsc, pal = self.state(), self.state()
        for controls in (3, 2, 12, 8, 0):
            for _ in range(60):
                old = ntsc.camera
                self.advance(ntsc, controls, 5)
                self.assertLessEqual(abs(ntsc.camera - old), 5)
            for _ in range(50):
                old = pal.camera
                self.advance(pal, controls, 6)
                self.assertLessEqual(abs(pal.camera - old), 5)
            self.assertEqual((ntsc.x, ntsc.camera, bytes(ntsc.flight)),
                             (pal.x, pal.camera, bytes(pal.flight)))

    def test_sampled_view_matches_every_tick_including_boundary_reversals(self):
        for start in (0, 64, 128, 256, 104 * 256, 4095 * 256 - 64, 4095 * 256):
            normal, sampled = self.state(), self.state()
            normal.x = sampled.x = start
            for group in (7, 8, 9, 12, 13, 15, 18):
                for frame in range(400):
                    for tick in range(group):
                        controls = (8, 9, 0, 2, 6, 0)[(frame // 13 + tick // 3) % 6]
                        self.core.World_Step(ctypes.byref(normal), controls)
                        self.core.World_StepSample(ctypes.byref(sampled), controls, tick == group - 1)
                    self.assertEqual((normal.x, normal.camera, bytes(normal.flight)),
                                     (sampled.x, sampled.camera, bytes(sampled.flight)))
