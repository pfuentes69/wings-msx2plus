"""Fuel, oil, failure and instrument rules recovered from the Amiga executable."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAMP_OIL, LAMP_FUEL = 1, 2


class Sortie(C.Structure):
    _fields_ = [('weapon', C.c_uint8), ('stock', C.c_uint8), ('oil', C.c_uint8), ('fuel', C.c_uint8)]


class Engine(C.Structure):
    _fields_ = [('fuel_ticks', C.c_uint8), ('leak_ticks', C.c_uint8),
                ('dry', C.c_uint8), ('failed', C.c_uint8), ('oil_blink', C.c_int8), ('fuel_blink', C.c_int8),
                ('oil_needle', C.c_uint8), ('fuel_needle', C.c_uint8), ('lamps', C.c_uint8), ('random', C.c_uint8),
                ('hits', C.c_uint8)]


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'engine.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT / 'src/core/engine.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Engine_Tick.restype = C.c_uint8
        cls.core.Engine_OilFrame.restype = C.c_uint8
        cls.core.Engine_FuelFrame.restype = C.c_uint8

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def fresh(self):
        engine, sortie = Engine(), Sortie()
        self.core.Engine_Reset(C.byref(engine), C.byref(sortie))
        return engine, sortie

    def ticks(self, engine, sortie, count, flying=1, throttle=0, warnings=1):
        failed = 0
        for _ in range(count):
            failed |= self.core.Engine_Tick(C.byref(engine), C.byref(sortie), flying, throttle, warnings)
        return failed

    def test_new_plane_matches_the_executable(self):
        engine, sortie = self.fresh()
        self.assertEqual((sortie.fuel, sortie.oil), (192, 128))
        # Full tanks: FUEL at ndln (22) and OIL at ndlg (16), as on the reference panel.
        self.assertEqual((engine.fuel_needle, engine.oil_needle), (22, 16))

    def test_fuel_burns_one_unit_per_28_ticks_only_in_flight(self):
        engine, sortie = self.fresh()
        self.ticks(engine, sortie, 28 * 10, flying=0)
        self.assertEqual(sortie.fuel, 192)
        self.ticks(engine, sortie, 28 * 10 - 1)
        self.assertEqual(sortie.fuel, 192 - 9)
        self.ticks(engine, sortie, 1)
        self.assertEqual(sortie.fuel, 192 - 10)

    def test_a_full_tank_lasts_7_2_minutes_then_the_engine_fails(self):
        engine, sortie = self.fresh()
        self.assertFalse(self.ticks(engine, sortie, 192 * 28))
        self.assertEqual(sortie.fuel, 0)
        self.assertFalse(engine.failed)
        self.assertTrue(self.ticks(engine, sortie, 28))  # the original's fuel < 0
        self.assertTrue(engine.failed)
        self.assertAlmostEqual(193 * 28 / 12.5 / 60, 7.2, places=1)

    def test_oil_leaks_once_damaged_and_seizes_below_96(self):
        engine, sortie = self.fresh()
        self.ticks(engine, sortie, 400)
        self.assertEqual(sortie.oil, 128)  # an undamaged engine does not leak
        self.core.Engine_Damage(C.byref(engine), C.byref(sortie), 1, 0)
        self.ticks(engine, sortie, 1)
        self.assertEqual(sortie.oil, 126)  # leak timer starts expired, as in the original
        self.ticks(engine, sortie, 80)
        self.assertEqual(sortie.oil, 125)
        self.assertFalse(engine.failed)
        failed = self.ticks(engine, sortie, 80 * 30)
        self.assertTrue(failed)
        self.assertEqual(sortie.oil, 95)
        before = (sortie.oil, sortie.fuel)
        self.ticks(engine, sortie, 200)
        self.assertEqual((sortie.oil, sortie.fuel), before)  # a dead engine burns nothing

    def test_heavy_hit_can_empty_the_tank_and_fail_the_engine(self):
        engine, sortie = self.fresh()
        sortie.fuel = 5
        self.core.Engine_Damage(C.byref(engine), C.byref(sortie), 8, 31)
        self.assertEqual((sortie.oil, sortie.fuel, engine.dry), (120, 0, 1))
        self.assertTrue(self.ticks(engine, sortie, 1))

    def test_instrument_targets(self):
        sortie = Sortie(oil=128, fuel=192)
        frame = self.core.Engine_OilFrame
        self.assertEqual([frame(C.byref(Sortie(oil=o)), 0) for o in (128, 116, 100, 97, 96, 90)], [16, 10, 2, 0, 0, 0])
        self.assertEqual(frame(C.byref(sortie), 1), 22)  # under throttle
        self.assertEqual([self.core.Engine_FuelFrame(C.byref(Sortie(fuel=f))) for f in (255, 192, 176, 64, 7, 0)],
                         [22, 22, 22, 8, 0, 0])

    def test_needles_sweep_one_frame_per_tick(self):
        engine, sortie = self.fresh()
        sortie.fuel = 64
        seen = []
        for _ in range(16):
            self.ticks(engine, sortie, 1, flying=0)
            seen.append(engine.fuel_needle)
        self.assertEqual(seen[:14], list(range(21, 7, -1)))
        self.assertEqual(seen[14:], [8, 8])
        self.ticks(engine, sortie, 1, flying=0, throttle=1)
        self.assertEqual(engine.oil_needle, 17)

    def test_lamps_blink_with_the_original_counters(self):
        engine, sortie = self.fresh()
        sortie.fuel, sortie.oil = 64, 115
        pattern = []
        for _ in range(24):
            self.ticks(engine, sortie, 1, flying=0)
            pattern.append(engine.lamps)
        oil = [bool(p & LAMP_OIL) for p in pattern]
        fuel = [bool(p & LAMP_FUEL) for p in pattern]
        self.assertEqual(oil[:13], [False] + [True] * 9 + [False, False, True])
        self.assertEqual(fuel[:11], [False] + [True] * 7 + [False, False, True])
        self.ticks(engine, sortie, 1, flying=0, warnings=0)
        self.assertEqual(engine.lamps, 0)
        sortie.fuel, sortie.oil = 65, 116
        self.ticks(engine, sortie, 3, flying=0)
        self.assertEqual(engine.lamps, 0)

    def test_an_empty_tank_needle_twitches_between_frames_0_and_1(self):
        engine, sortie = self.fresh()
        sortie.fuel = 0
        seen = set()
        for _ in range(60):
            self.ticks(engine, sortie, 1, flying=0)
            seen.add(engine.fuel_needle)
        self.assertEqual(seen & {0, 1}, {0, 1})


if __name__ == '__main__':
    unittest.main()
