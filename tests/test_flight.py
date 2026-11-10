"""Exercise the same portable flight core compiled for the host C ABI."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Flight(ctypes.Structure):
    _fields_ = [('x', ctypes.c_uint16), ('y', ctypes.c_uint16),
                ('vx', ctypes.c_int16), ('vy', ctypes.c_int16),
                ('frame', ctypes.c_uint8), ('facing_left', ctypes.c_uint8)]


class FlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name) / 'flight.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-fPIC', str(ROOT / 'src/core/flight.c'), '-o', str(library)], check=True, capture_output=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.Flight_Reset.argtypes = [ctypes.POINTER(Flight)]
        cls.core.Flight_Step.argtypes = [ctypes.POINTER(Flight), ctypes.c_uint8]
        cls.core.Flight_Reset.restype = cls.core.Flight_Step.restype = None

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def state(self):
        state = Flight()
        self.core.Flight_Reset(ctypes.byref(state))
        return state

    def step(self, state, controls, count):
        for _ in range(count):
            self.core.Flight_Step(ctypes.byref(state), controls)
        return state

    def test_reset_and_rest(self):
        state = self.step(self.state(), 0, 500)
        self.assertEqual((state.x, state.y, state.vx, state.vy, state.frame), (104 * 256, 88 * 256, 0, 0, 1))
        self.step(state, 3, 50)
        self.core.Flight_Reset(ctypes.byref(state))
        self.assertEqual(bytes(state), bytes(self.state()))

    def test_acceleration_orientation_and_coasting(self):
        state = self.step(self.state(), 1 | 2, 20)
        self.assertGreater(state.x, 104 * 256)
        self.assertLess(state.y, 88 * 256)
        self.assertEqual((state.frame, state.facing_left), (0, 0))
        x, y = state.x, state.y
        self.step(state, 0, 1)
        self.assertGreater(state.x, x)
        self.assertLess(state.y, y)
        self.step(state, 0, 100)
        self.assertEqual((state.vx, state.vy, state.frame), (0, 0, 1))

    def test_reversal_requires_braking_and_changes_facing(self):
        state = self.step(self.state(), 2, 10)
        self.step(state, 8, 1)
        self.assertGreater(state.vx, 0)
        self.assertEqual(state.facing_left, 0)
        self.step(state, 8, 20)
        self.assertLess(state.vx, 0)
        self.assertEqual(state.facing_left, 1)

    def test_opposed_inputs_match_release(self):
        state = self.step(self.state(), 3, 10)
        other = Flight.from_buffer_copy(state)
        self.step(state, 15, 12)
        self.step(other, 0, 12)
        self.assertEqual(bytes(state), bytes(other))

    def test_bounds_do_not_wrap_and_stop_outward_velocity(self):
        for controls, x, y in ((3, 208 * 256, 0), (12, 0, 180 * 256)):
            state = self.step(self.state(), controls, 5000)
            self.assertEqual((state.x, state.y), (x, y))
            self.assertEqual((state.vx, state.vy), (0, 0))

    def test_pal_ntsc_grouping_advances_same_time(self):
        ntsc, pal = self.state(), self.state()
        for controls in (3, 12, 0):
            for _ in range(30):
                self.step(ntsc, controls, 5)
            for _ in range(25):
                self.step(pal, controls, 6)
            self.assertEqual(bytes(ntsc), bytes(pal))
