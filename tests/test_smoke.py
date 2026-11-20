"""Engine smoke logic (src/core/smoke.c) after the Amiga emitter 0x1bfc,
spawner 0x54e0/0x5460 and effect update 0x0ee0."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_flight_model import Flight

ROOT = Path(__file__).resolve().parents[1]
COUNT, STAGES, STAGE_TICKS = 8, 5, 7


class Puff(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint16), ('xf', C.c_uint8), ('yf', C.c_uint8),
                ('vx', C.c_uint8), ('vy', C.c_uint8), ('stage', C.c_uint8), ('life', C.c_uint8)]


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'smoke.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
                        '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in ('core/smoke.c', 'core/flight.c', 'core/flight_model.c', '../tests/stubs/crash_stub.c')],
                        '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Smoke_Tick.argtypes = [C.POINTER(Flight), C.c_uint16, C.c_uint8, C.c_uint8]
        cls.puffs = (Puff * COUNT).in_dll(cls.core, 'g_Smoke')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.core.Smoke_Reset()

    def plane(self, y=900, left=True, turn=0):
        return Flight(y=y * 256, facing_left=left, mode=1, turn=turn)

    def live(self):
        return [p for p in self.puffs if p.stage]

    def tick(self, flight, oil, n=1, world=4000, emit=1):
        for _ in range(n):
            self.core.Smoke_Tick(C.byref(flight), world, oil, emit)

    def test_an_undamaged_engine_does_not_smoke(self):
        self.tick(self.plane(), 128, 200)
        self.assertEqual(self.live(), [])

    def test_heavy_damage_puffs_every_fourth_tick_from_the_nose(self):
        f = self.plane(left=True)
        self.tick(f, 100, 4)                  # damage 28 (> 19): always
        (p,) = self.live()
        self.assertEqual((p.x, p.y, p.stage), (4000 - 10, 900 - 13, STAGES))
        self.tick(f, 100, 4)
        self.assertEqual(len(self.live()), 2)
        self.core.Smoke_Reset()
        f = self.plane(left=False)
        self.tick(f, 100, 4)
        self.assertEqual(self.live()[0].x, 4000 + 10)

    def test_puffs_rise_and_drift_right_and_shrink_over_35_ticks(self):
        f = self.plane()
        self.tick(f, 100, 4)
        p = next(p for p in self.puffs if p.stage)
        x0, y0 = p.x, p.y
        stages = []
        for _ in range(STAGES * STAGE_TICKS):
            self.tick(f, 100, 1, emit=0)
            stages.append(p.stage)
        self.assertEqual(stages[:7], [5] * 6 + [4])
        self.assertEqual(stages[-1], 0)
        self.assertTrue(35 <= p.x - x0 - 0 <= 70 and 35 <= y0 - p.y <= 70)  # 1-2 px a tick each way

    def test_the_pool_holds_eight_puffs(self):
        f = self.plane()
        self.tick(f, 90, 4 * 30)
        self.assertLessEqual(len(self.live()), COUNT)
        self.assertGreaterEqual(len(self.live()), COUNT - 1)

    def test_light_damage_puffs_with_the_original_odds(self):
        f = self.plane()
        for damage, odds in ((1, 3 / 16), (10, 8 / 16), (19, 12 / 16)):
            puffs = 0
            for _ in range(800):
                self.core.Smoke_Reset()
                self.tick(f, 128 - damage, 4)
                puffs += len(self.live())
            self.assertAlmostEqual(puffs / 800, odds, delta=0.06)

    def test_smoke_starts_at_least_16_px_above_the_sea(self):
        f = self.plane(y=1199)                # 1 px up: 1 + 13 < 16
        self.tick(f, 100, 4)
        self.assertEqual(self.live()[0].y, 1200 - 16)

    def test_turn_offsets_shift_the_puff(self):
        for turn, left, offset in ((9, True, -3), (12, True, 12), (12, False, 12), (10, False, -7)):
            self.core.Smoke_Reset()
            f = self.plane(left=left, turn=turn)
            self.tick(f, 100, 4)
            base = 4000 - 10 if left else 4000 + 10
            self.assertEqual(self.live()[0].x, base + offset, (turn, left))

    def test_no_new_puffs_while_crashed_but_old_ones_drift_on(self):
        f = self.plane()
        self.tick(f, 100, 4)
        p = next(p for p in self.puffs if p.stage)
        x0 = p.x
        self.tick(f, 100, 8, emit=0)
        self.assertEqual(len(self.live()), 1)
        self.assertGreater(p.x, x0)


if __name__ == '__main__':
    unittest.main()
