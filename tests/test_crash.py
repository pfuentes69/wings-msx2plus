"""The player's crash (src/core/crash.c, docs/research/amiga-player-crash.md):
contact, the slide, sinking, the wreck, the hull side and the crash clock,
through the release step function on map a (land 8..3975, the carrier's
columns 6600..7359, sea elsewhere). tests/stubs/crash_world.c records the
ship, island and smoke calls."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_flight_model import CRASH_SOURCES, Flight, World, Aircraft
from test_island import Combat

ROOT = Path(__file__).resolve().parents[1]
TICK = 12
AIRBORNE, DEAD, SINKING, WRECK = 1, 3, 4, 5
IMPACT, SPLASH, CRASH_BURST = 3, 4, 5
WHITE, RED = 1, 2
GUNS = 2


class Crash(C.Structure):
    _fields_ = [('dx', C.c_int16), ('dy', C.c_int16), ('clock', C.c_uint8), ('next', C.c_uint8),
                ('sink', C.c_uint8), ('depth', C.c_uint8), ('puff', C.c_uint8)]


def slide(speed):
    """The original's slide (0xb2aa): ticks and px for a speed."""
    ticks = px = 0
    while speed:
        px += speed // 100
        speed -= 85
        if speed < 100: speed = 0
        ticks += 1
    return ticks, px


class CrashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'crash.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I' + str(ROOT / 'src/generated/map_a'),
                        '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
                        '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in CRASH_SOURCES], '-o', str(lib)],
                       check=True, capture_output=True)
        c = cls.core = C.CDLL(str(lib))
        c.World_Reset.argtypes = [C.POINTER(World)]
        c.World_StepSample.argtypes = [C.POINTER(World), C.c_uint8, C.c_uint8]
        c.Flight_EngineOut.argtypes = [C.POINTER(Flight)]
        c.Crash_Contact.argtypes = [C.POINTER(Flight), C.c_uint16]
        c.Aircraft_SyncFlight.argtypes = [C.POINTER(Aircraft), C.POINTER(Flight), C.c_uint16]
        cls.crash = Crash.in_dll(c, 'g_Crash')
        cls.combat = Combat.in_dll(c, 'g_Combat')
        import json
        meta = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']
        cls.names = {f['id']: f['name'] for f in meta['frames']}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        C.memset(C.byref(self.combat), 0, C.sizeof(self.combat))
        for name in ('g_Splashes', 'g_Kills', 'g_Bombed', 'g_Rockets', 'g_Puffs', 'g_LastContact'):
            C.c_uint8.in_dll(self.core, name).value = 0
        C.c_uint16.in_dll(self.core, 'g_BombPoints').value = 0

    def count(self, name):
        return C.c_uint8.in_dll(self.core, name).value

    def log(self, name, n, kind=C.c_int16):
        return list((kind * 128).in_dll(self.core, name)[:n])

    def plane(self, x, altitude, speed, left=True):
        """Flying level at speed px/100 a tick, then (the next tick's motion
        set) placed at x and altitude."""
        w = World()
        self.core.World_Reset(C.byref(w))
        w.x = x * 256
        w.flight.y = (1200 - 300) * 256
        w.flight.mode, w.flight.facing_left, w.flight.speed, w.flight.boost = AIRBORNE, left, speed, 4
        self.ticks(w)
        w.x = x * 256
        w.flight.y = (1200 - altitude) * 256
        return w

    def ticks(self, w, n=1, controls=0):
        for _ in range(n * TICK):
            self.core.World_StepSample(C.byref(w), controls, 1)
        return w

    def altitude(self, w):
        return 1200 - (w.flight.y >> 8)

    def contact(self, w):
        self.core.Crash_Contact(C.byref(w.flight), (w.x >> 8) & 0xFFFF)
        # The rest of the contact tick: level, no vertical motion.
        while w.flight.step:
            self.core.World_StepSample(C.byref(w), 0, 1)

    def bursts(self):
        return [(p.x // 4, p.y // 4, p.kind) for p in self.combat.projectile[GUNS:] if p.kind and p.vx == CRASH_BURST]

    def rest(self, w, limit=40):
        n = 0
        while w.flight.mode == DEAD:
            self.ticks(w)
            n += 1
            self.assertLess(n, limit)
        return n

    def shape(self, w):
        a = Aircraft()
        self.core.Aircraft_SyncFlight(C.byref(a), C.byref(w.flight), (w.x >> 8) & 0xFFFF)
        return self.names[a.shape]

    # The sea: 0xba80 (no burst), the slide (0xb2aa), sinking (0xc78c)

    def test_into_the_sea_the_plane_slides_splashing_then_sinks(self):
        w = self.plane(5800, 1, 1200, left=False)
        self.contact(w)
        self.assertEqual((w.flight.mode, w.flight.speed, self.bursts()), (DEAD, 1200, []))
        x0 = w.x >> 8
        n = self.rest(w)
        self.assertEqual((n, (w.x >> 8) - x0), slide(1200))     # 13 ticks, 84 px
        self.assertEqual(slide(1200), (13, 84))
        self.assertEqual((w.flight.mode, self.altitude(w), self.count('g_LastContact')), (SINKING, 2, 3))
        self.assertEqual(self.count('g_Splashes'), 2 * n)         # two a tick, ahead of the nose
        self.assertTrue(all(x > x0 for x in self.log('g_SplashX', 2 * n)))
        self.assertEqual(self.count('g_Bombed') + self.count('g_Kills') + self.count('g_Rockets'), 0)

    def test_the_sinking_plane_noses_down_and_goes_under_a_pixel_every_3_ticks(self):
        w = self.plane(5800, 1, 1000, left=False)
        self.contact(w)
        self.rest(w)
        x, shapes, depths = w.x, [], []
        for _ in range(150):
            self.ticks(w)
            shapes.append(self.shape(w))
            depths.append(self.crash.depth)
        self.assertEqual(w.x, x)
        self.assertEqual(self.altitude(w), 2)                     # drawn lower: g_Crash.depth
        self.assertEqual(depths[:7], [0, 0, 1, 1, 1, 2, 2])
        self.assertEqual(depths[-1], 50)
        self.assertEqual(shapes[:18], ['hc05'] * 2 + ['hc06'] * 2 + ['hc07'] * 4 + ['hc08'] * 4 + ['hc09'] * 4 + ['hc0a'] * 2)
        self.assertEqual(self.crash.clock, 150)

    def test_water_bursts_for_6_seconds_silent_within_8_px(self):
        w = self.plane(5800, 1, 1000, left=False)
        self.contact(w)
        self.rest(w)
        x, seen, late = w.x >> 8, [], []
        for t in range(110):
            self.ticks(w)
            for bx, by, kind in self.bursts():
                if t < 75:
                    seen.append((bx, by, kind))
                else:
                    late.append(t)
            for p in self.combat.projectile[GUNS:]:   # the weapon tick ages them
                if p.kind and p.vx == CRASH_BURST: p.kind = 0
        self.assertTrue(6 <= len(seen) <= 40, len(seen))   # every 1, 4, 8 or 12 ticks
        self.assertEqual({k for *_, k in seen}, {SPLASH})
        self.assertTrue(all(by == 1200 and (x - 8) & ~7 <= bx <= x + 7 for bx, by, _ in seen), seen)
        self.assertEqual(late, [])

    # Land: 0xba80's burst and impact, the slide's strikes, the wreck (0xc7c6)

    def test_into_the_island_bursts_strikes_and_burns(self):
        w = self.plane(3100, 1, 1100, left=True)
        C.c_uint16.in_dll(self.core, 'g_BombPoints').value = 150
        self.contact(w)
        self.assertEqual(self.bursts(), [((3100 - 16) & ~7, 1199, IMPACT)])
        self.assertEqual(self.log('g_BombedX', self.count('g_Bombed')), [3100])
        self.assertEqual((self.combat.sky_flash, self.combat.sky_color), (5, RED))   # it wrecked something
        x0, speed = w.x >> 8, w.flight.speed
        n = self.rest(w)
        self.assertEqual((n, x0 - (w.x >> 8)), slide(speed))
        self.assertEqual((w.flight.mode, self.altitude(w)), (WRECK, 2))
        # Each slide tick: a burst at the ground, a strike and soldiers within 8 px.
        self.assertEqual(self.count('g_Bombed'), 1 + n)
        self.assertEqual(self.count('g_Kills'), n)
        self.assertEqual(set(self.log('g_KillR', n, C.c_uint8)), {8})
        self.assertEqual(self.count('g_Splashes'), 0)

    def test_the_wreck_puffs_fire_every_4_ticks_and_bursts_with_booms(self):
        w = self.plane(3100, 1, 1000, left=True)
        self.contact(w)
        self.rest(w)
        x = w.x >> 8
        C.c_uint8.in_dll(self.core, 'g_Puffs').value = 0
        kinds = set()
        for _ in range(100):
            self.ticks(w)
            kinds |= {k for *_, k in self.bursts()}
        n = self.count('g_Puffs')
        self.assertIn(n, (24, 25, 26))
        self.assertEqual(set(self.log('g_PuffStage', n, C.c_uint8)), {6})
        self.assertEqual(set(self.log('g_PuffY', n, C.c_uint16)), {1200 - 19})
        self.assertTrue(all(x - 8 <= px <= x - 1 for px in self.log('g_PuffX', n, C.c_uint16)))
        self.assertEqual(kinds, {IMPACT})
        self.assertEqual((w.flight.mode, w.x >> 8, self.altitude(w)), (WRECK, x, 2))

    # The deck: a dead engine falls onto it and burns there

    def test_a_dead_engine_over_the_deck_comes_down_on_it_and_burns(self):
        w = self.plane(6800, 100, 1000, left=False)
        self.core.Flight_EngineOut(C.byref(w.flight))
        lowest = 100
        while w.flight.mode == DEAD:
            self.ticks(w)
            lowest = min(lowest, self.altitude(w))
        self.assertEqual((w.flight.mode, self.altitude(w), lowest), (WRECK, 35, 35))   # deck 33 + 2
        self.assertEqual(self.bursts(), [])                                         # a silent slide
        self.assertTrue(6600 <= w.x >> 8 < 7360)

    def test_the_hull_side_throws_the_plane_back_into_the_sea(self):
        w = self.plane(7350, 10, 1000, left=True)    # 10 px into the stern, below the deck
        self.contact(w)
        self.ticks(w)
        self.assertEqual((self.combat.sky_flash, self.combat.sky_color, w.flight.speed), (7, RED, 0))
        self.assertGreater(w.x >> 8, 7350)              # thrown back east
        self.rest(w)
        self.assertEqual(w.flight.mode, SINKING)

    def test_a_fall_into_the_sea_bursts_water_not_fire(self):
        w = self.plane(5000, 30, 1000, left=True)
        self.core.Flight_EngineOut(C.byref(w.flight))
        self.rest(w)
        self.assertEqual(w.flight.mode, SINKING)
        self.assertEqual({k for *_, k in self.bursts()}, {SPLASH})

    def test_the_wreck_bursts_stop_after_6_seconds_and_the_clock_runs_to_255(self):
        w = self.plane(3100, 1, 1000, left=True)
        self.contact(w)
        self.rest(w)
        self.ticks(w, 75)
        C.memset(C.byref(self.combat), 0, C.sizeof(self.combat))
        self.ticks(w, 200)
        self.assertEqual((self.bursts(), self.crash.clock), ([], 255))


if __name__ == '__main__':
    unittest.main()
