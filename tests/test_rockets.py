"""Rockets (src/core/rockets.c) and ship guns (src/core/ships.c) against a
model of the Amiga code written from the 68000 routines: launch 0x08fe, the
tick 0x0aa6, the aim 0x099a with 0x1a46 / 0x11a6 / 0x5ca6, the gun kill
0x49dc and the gun smoke 0x4c3e (docs/rockets.md). Built on map j, which
has a destroyer and a battleship."""
import ctypes as C
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import convert_rockets   # noqa: E402

MAP = ROOT / 'src/generated/map_j'
WORLD = 7944
STUB = r"""
#include <stdint.h>
uint16_t g_Puffs[64][2];
uint8_t g_PuffCount;
void Smoke_Emit(uint16_t x, uint16_t y)
{
    if (g_PuffCount < 64) { g_Puffs[g_PuffCount][0] = x; g_Puffs[g_PuffCount][1] = y; }
    ++g_PuffCount;
}
#include "ships.h"
#include "smoke.h"
uint16_t g_EngineHits;
void Smoke_Hit(const FlightState* flight, uint16_t world) { (void)flight; (void)world; }
void Engine_Hit(EngineState* engine, SortieState* sortie, uint8_t random) { (void)engine; (void)sortie; (void)random; ++g_EngineHits; }
"""


class Projectile(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint16), ('vx', C.c_int8), ('vy', C.c_int8),
                ('life', C.c_uint8), ('kind', C.c_uint8)]


class Rocket(C.Structure):
    _fields_ = [('x', C.c_int32), ('vx', C.c_int32), ('vy', C.c_int32), ('ax', C.c_int16),
                ('ay', C.c_int16), ('y', C.c_int16), ('delay', C.c_uint8), ('frame', C.c_uint8),
                ('angle', C.c_int8), ('speed', C.c_uint8), ('live', C.c_uint8)]


class Combat(C.Structure):
    _fields_ = [('projectile', Projectile * 18), ('phase', C.c_uint8), ('cooldown', C.c_uint8),
                ('secondary_cooldown', C.c_uint8), ('secondary_pending', C.c_uint8),
                ('primary_pending', C.c_uint8), ('secondary_phase', C.c_uint8),
                ('count', C.c_uint8), ('aim_pitch', C.c_uint8),
                ('shots_fired', C.c_uint16), ('secondary_fired', C.c_uint16), ('impacts', C.c_uint16),
                ('flash', C.c_uint8), ('flash_ticks', C.c_uint8),
                ('rocket', Rocket * 15), ('rockets', C.c_uint8), ('rocket_tick', C.c_uint8),
                ('path', C.c_int16), ('speed', C.c_int16), ('far', C.c_uint8), ('bob', C.c_uint8),
                ('sky_flash', C.c_uint8), ('sky_color', C.c_uint8), ('plane_x', C.c_int16)]


class Shown(C.Structure):
    _fields_ = [('x', C.c_uint16), ('altitude', C.c_uint8), ('frame', C.c_uint8)]


class Splash(C.Structure):
    _fields_ = [('x', C.c_int16), ('life', C.c_uint8), ('land', C.c_uint8)]


class Ships(C.Structure):
    _fields_ = [('down', C.c_uint8 * 40), ('puffs', C.c_uint8 * 40), ('timer', C.c_uint8 * 40),
                ('smoking', C.c_uint8), ('guns_down', C.c_uint16), ('shown', Shown * 16),
                ('shown_count', C.c_uint8), ('splash', Splash * 4), ('splashes', C.c_uint8),
                ('nearest', C.c_uint16), ('hits', C.c_uint16), ('present', C.c_uint8)]


class Flight(C.Structure):   # FlightState's head: ships.c reads y only
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint32), ('pad', C.c_uint8 * 64)]


GUN_NONE, GUN_FLASH, GUN_FAR = 255, 7, 14
# DATA -$63e2 - 17 .. +47 (0x4db8), as tests/test_island.py.
BARREL = bytes([2, 2, 3, 3, 3, 1, 2, 3, 3, 0, 1, 2, 3, 0, 1, 2, 3,
                0, 0, 0, 3, 3, 6, 6, 6, 0, 1, 1, 3, 3, 5, 5, 6, 1, 1, 2, 3, 3, 4, 5, 5,
                1, 2, 2, 3, 3, 4, 4, 5, 2, 2, 3, 3, 3, 3, 4, 4, 1, 2, 3, 2, 1, 2, 3, 2])


def s16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


class Original:
    """The Amiga rocket, in its own terms (68000 word and long arithmetic)."""
    def __init__(self, guns):
        parts = convert_rockets.hunks(convert_rockets.EXECUTABLE.read_bytes())
        data = next(h for k, h in parts if k == 0x3ea)
        at = lambda n, size: data[0x7ffe - n:0x7ffe - n + size]
        self.sine = [int.from_bytes(at(0x6692, 514)[i:i + 2], 'big', signed=True) for i in range(0, 514, 2)]
        self.tangent = [int.from_bytes(at(0x6892, 512)[i:i + 2], 'big') for i in range(0, 512, 2)]
        self.arctangent = at(0x5810, 257)
        self.guns = guns

    def sin(self, d0):                          # 0x5108
        d0 &= 0x3ff
        if d0 < 0x100:
            return self.sine[d0]
        if d0 < 0x200:
            return self.sine[0x200 - d0]
        d0 -= 0x200
        return -self.sine[d0] if d0 < 0x100 else -self.sine[0x200 - d0]

    def cos(self, d0):                          # 0x5104
        return self.sin(d0 + 0x100)

    def atan2(self, alt, dx):                   # 0x5ca6 (alt, dx >= 0)
        if alt == dx:
            return 0x80 if alt else 0
        small, big, steep = (alt, dx, False) if alt < dx else (dx, alt, True)
        q = (small << 16) // big
        q = (q >> 8) + ((q >> 7) & 1)
        return 0x100 - self.arctangent[q] if steep else self.arctangent[q]

    def ground(self, a, px, palt, left):        # 0x1a46
        if a >= 0:
            return 0
        if a == -255:
            a = -254
        d1 = (palt << 16) >> 8
        t = self.tangent[(-a) & 0xff]
        q = (d1 & 0xffffffff) // t
        low = d1 & 0xffff if q > 0xffff else q
        if not left:
            low = -low
        return s16(px - low)

    def launch(self, path, speed, hstep, vstep, left, x, alt, delay):
        bfa = int(path * 2 * 512 / 18000)          # divs.w: toward zero
        r = dict(x=x << 16, y=alt, vx=s32((-hstep if left else hstep) << 16), vy=s32(vstep << 16),
                 angle=bfa >> 1, speed=speed, delay=delay)
        r['ay'] = self.sin(r['angle']) * 2
        r['ax'] = self.cos(r['angle']) * 2 * (-1 if r['vx'] < 0 else 1)
        frame = min(9, max(0, 4 - (bfa >> 5)))
        r['frame'] = frame + (10 if r['vx'] < 0 else 0)
        return r

    def aim(self, r, px, palt, left):           # 0x099a
        d4 = r['angle'] >> 1
        if d4 >= 0:
            return
        points = [self.ground(a, px, palt, left) for a in (d4, d4 + 20, d4 - 20)]
        if 0 in points:
            return
        target = 0
        for other in (points[1], points[2]):
            lo, hi = sorted((points[0], other))
            target = next((g for g in self.guns if lo <= g <= hi), 0)
            if target:
                break
        if not target:
            return
        dx = abs(s16(target - (r['x'] >> 16)))
        a = self.atan2(r['y'], dx)
        a = -a if a >= 0 else a
        q = r['speed'] // 100
        vx = self.cos(a) * q
        r['vx'] = -vx if r['vx'] < 0 else vx
        r['vy'] = self.sin(a) * q

    def tick(self, r, px, palt, left, far, burst_altitude):
        """One tick; returns 'flying', 'gone' or ('burst', x, altitude)."""
        accelerate = True
        if r['delay']:
            r['delay'] -= 1
            if r['delay']:
                r['x'] = s32(r['x'] - ((-1 if left else 1) << 16))
                r['y'] = s16(r['y'] - 1)
                accelerate = False
            else:
                self.aim(r, px, palt, left)
        if accelerate:
            r['vy'] = s32(r['vy'] + r['ay'])
            r['vx'] = s32(r['vx'] + r['ax'])
        r['x'] = s32(r['x'] + r['vx'])
        d1 = abs(s32((px << 16) - r['x']))
        d1 = s16(s16(d1 >> 16) - 0x280 - (0x1180 if far else 0))
        if d1 > 0x280:
            return 'gone'
        r['y'] = s16((r['y'] << 16) + r['vy'] + r['ay'] >> 16)
        if r['y'] <= 44:
            altitude = burst_altitude(r['x'] >> 16)
            if r['y'] <= altitude:
                return ('burst', r['x'] >> 16, altitude)
        return 'flying'


class RocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        (work / 'stub.c').write_text(STUB)
        lib = work / 'rockets.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I' + str(MAP), '-I' + str(ROOT / 'src/core'),
                        '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DWINGS_FLIGHT_MAX_Y=1200u', f'-DWINGS_WORLD_WIDTH={WORLD}u',
                        *[str(ROOT / 'src' / p) for p in ('core/combat.c', 'core/rockets.c', 'core/rocket_move.c', 'core/ships.c',
                                                          'core/mission.c', 'generated/map_j/mission_surfaces.c')],
                        str(work / 'stub.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Rockets_Launch.argtypes = [C.POINTER(Combat), C.c_uint16, C.c_uint16, C.c_int16, C.c_int16, C.c_uint8]
        cls.core.Rockets_Launch.restype = C.c_uint8
        cls.core.Rockets_Step.argtypes = [C.POINTER(Combat), C.c_uint16, C.c_uint16, C.c_uint8]
        cls.core.Ships_Find.argtypes = [C.c_uint16]
        cls.core.Ships_Find.restype = C.c_uint8
        cls.core.Ships_Deck.argtypes = [C.c_uint8]
        cls.core.Ships_Deck.restype = C.c_uint8
        cls.core.Ships_Rocket.argtypes = [C.c_uint16, C.POINTER(C.c_uint32)]
        cls.core.Ships_Rocket.restype = C.c_uint8
        cls.core.Ships_Aim.argtypes = [C.c_int16, C.c_int16]
        cls.core.Ships_Aim.restype = C.c_uint16
        cls.core.Ships_Tick.argtypes = [C.c_uint8]
        cls.core.Ships_Guns.argtypes = [C.POINTER(Flight), C.c_uint16, C.c_uint8, C.c_void_p, C.c_void_p]
        cls.core.Ships_Guns.restype = C.c_uint8
        cls.core.Mission_Surface.argtypes = [C.c_uint16]
        cls.core.Mission_Surface.restype = C.c_uint8
        header = (MAP / 'mission_ships.h').read_text()
        cls.gun_x = [int(v) for v in re.search(r's_ShipGunX\[\d+\] = \{([^}]*)\}', header).group(1).split(',')]
        cls.original = Original(cls.gun_x)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.ships = Ships.in_dll(self.core, 'g_Ships')
        self.core.Ships_Reset()
        C.c_uint8.in_dll(self.core, 'g_PuffCount').value = 0

    def burst_altitude(self, x, bob):
        if self.core.Mission_Surface(x) != 1:
            return 12
        ship = self.core.Ships_Find(x)
        return 44 if ship >= 254 else self.core.Ships_Deck(ship) - bob + 11

    def fly(self, path, speed, hstep, vstep, left, x, y, far=0, bob=3, ticks=200, turn_at=None):
        """Launch from the plane at (x, y) and fly both models; the plane
        keeps its steps (and turns at turn_at). Returns the outcome."""
        s = Combat()
        s.path, s.speed, s.far, s.bob = path, speed, far, bob
        vx = round(hstep * 256 / 12) * (-1 if left else 1)
        vy = -round(vstep * 256 / 12)
        self.assertEqual(self.core.Rockets_Launch(C.byref(s), x, y, vx, vy, left), 1)
        c = s.rocket[0]
        self.assertIn(c.delay, (4, 8, 12))
        o = self.original.launch(path, speed, hstep, vstep, left, x, 1200 - y + 11, c.delay)
        self.assertEqual((c.x, c.y, c.vx, c.vy, c.ax * 2, c.ay * 2, c.frame, c.angle, c.speed),
                         (o['x'], o['y'], o['vx'], o['vy'], o['ax'], o['ay'], o['frame'], o['angle'], speed // 100))
        px, alt = x, 1200 - y
        for t in range(ticks):
            if turn_at == t:
                left = 1 - left
            px += -hstep if left else hstep
            alt += vstep
            outcome = self.original.tick(o, px, alt, left, far, lambda bx: self.burst_altitude(bx, bob))
            self.core.Rockets_Step(C.byref(s), px, 1200 - alt, left)
            if outcome == 'flying':
                self.assertEqual((c.live > 0, c.x, c.y, c.vx, c.vy), (True, o['x'], o['y'], o['vx'], o['vy']), t)
                continue
            self.assertEqual((c.live, s.rockets), (0, 0), t)
            if outcome != 'gone':
                _, bx, altitude = outcome
                p = next(p for p in s.projectile[2:] if p.kind)
                # x is a 16384 px ring (open sea past the map's ends).
                self.assertEqual((p.x >> 2, p.y >> 2, p.life, p.vx), (bx % 16384, 1200 - altitude + 12, 6, 1))
            return outcome, t
        self.fail('the rocket neither burst nor left')

    def test_free_flight_matches_the_original_tick_for_tick(self):
        rng = random.Random(7)
        outcomes = set()
        for _ in range(300):
            path = rng.randint(-4500, 3000)
            speed = rng.randint(600, 1400)
            hstep = speed // 100
            vstep = rng.randint(-12, 8)
            left = rng.randint(0, 1)
            x = rng.randint(1500, 6000)
            y = 1200 - rng.randint(20, 1000)
            outcome, _ = self.fly(path, speed, hstep, vstep, left, x, y, far=rng.randint(0, 1),
                                  turn_at=rng.choice((None, 3, 10)))
            outcomes.add(outcome if outcome == 'gone' else 'burst')
        self.assertEqual(outcomes, {'gone', 'burst'})

    def test_a_steep_dive_aims_at_a_ship_gun(self):
        # Diving at 45 degrees towards the destroyer's stern guns (86..126).
        aimed = 0
        for x in range(-150, 10, 4):
            s = Combat(); s.path, s.speed, s.bob = -4500, 1000, 3
            self.assertEqual(self.core.Rockets_Launch(C.byref(s), 0 if x < 0 else x, 1200 - 200, 154, 0, 0), 1)
            for t in range(s.rocket[0].delay):
                before = (s.rocket[0].vx, s.rocket[0].vy)
                self.core.Rockets_Step(C.byref(s), 0 if x < 0 else x, 1000, 0)
            if s.rocket[0].live and before != (s.rocket[0].vx - 2 * s.rocket[0].ax, s.rocket[0].vy - 2 * s.rocket[0].ay):
                aimed += 1
        # The model already agrees tick for tick; here check aims happen.
        self.assertGreater(aimed, 0)
        for x in range(0, 80, 6):
            self.fly(-4500, 1000, 10, -7, 0, x, 1200 - 160)
            self.fly(-4500, 1200, 12, -9, 1, 700 + x, 1200 - 150)

    def test_guns_fall_to_rockets_and_smoke(self):
        score = C.c_uint32(0)
        # Destroyer guns at 86, 96, ...: the first live one within 16 px.
        self.assertEqual(self.core.Ships_Rocket(100, C.byref(score)), 2)
        self.assertEqual((list(self.ships.down[:3]), score.value), ([1, 0, 0], 200))
        self.assertEqual(self.core.Ships_Rocket(100, C.byref(score)), 2)
        self.assertEqual((list(self.ships.down[:3]), score.value), ([1, 1, 0], 400))
        self.assertEqual(self.core.Ships_Rocket(100, C.byref(score)), 1)   # 116 is 16 away: no gun
        self.assertEqual(list(self.ships.down[:3]), [1, 1, 0])
        self.assertEqual(self.core.Ships_Rocket(300, C.byref(score)), 1)   # the hull, no gun near
        self.assertEqual(self.core.Ships_Rocket(2000, C.byref(score)), 0)  # open sea
        self.assertEqual(self.core.Ships_Rocket(4000, C.byref(score)), 1)  # the player's carrier
        self.assertEqual(score.value, 400)
        # 0x4c3e: the next puff a tick later each time, 49 of them.
        gaps, last, t = [], 0, 0
        while self.ships.smoking and t < 5000:
            count = C.c_uint8.in_dll(self.core, 'g_PuffCount').value
            self.core.Ships_Tick(1); t += 1
            if C.c_uint8.in_dll(self.core, 'g_PuffCount').value != count:
                gaps.append(t - last); last = t
        self.assertEqual(C.c_uint8.in_dll(self.core, 'g_PuffCount').value, 2 * 49)
        self.assertEqual(gaps[:3], [1, 1, 2])   # two guns: puffs at ticks 1, 1; then 50 - 48
        self.assertEqual(self.ships.guns_down, 2)
        self.core.Ships_Tick(0)

    def test_aim_finds_guns_between_points_live_or_not(self):
        self.assertEqual(self.core.Ships_Aim(90, 80), 86)
        self.assertEqual(self.core.Ships_Aim(97, 105), 0)
        self.assertEqual(self.core.Ships_Aim(7800, 7900), 7805)
        score = C.c_uint32(0)
        self.core.Ships_Rocket(86, C.byref(score))
        self.assertEqual(self.core.Ships_Aim(80, 90), 86)   # destroyed guns still draw rockets

    # Ship guns (0x4c3e, 0x4db8, 0x4efc, 0x4f5c).
    def guns(self, world, altitude, n=1, flying=1):
        """n updates with the plane at (world, altitude): the frames of the
        destroyer's first gun (x 86) each update, and the splashes made."""
        flight = Flight(y=(1200 - altitude) << 8)
        frames, splashes = [], []
        buf = C.create_string_buffer(64)
        for _ in range(n):
            self.core.Ships_Guns(C.byref(flight), world, flying, buf, buf)
            frames.append({s.x: s.frame for s in self.ships.shown[:self.ships.shown_count]})
            splashes += [(s.x, s.life) for s in self.ships.splash if s.life == 6]
        return frames, splashes

    def test_the_barrels_follow_the_plane(self):
        self.assertEqual(self.ships.present, 1)
        for dx in (-512, -400, -81, -40, 0, 39, 40, 200, 512):
            for altitude in (10, 31, 32, 100, 150, 186):
                frames, _ = self.guns(86 + dx, altitude, 8)
                expected = BARREL[((altitude >> 5) - 1) * 8 + int(dx / 40) + 3 + 17]
                self.assertEqual({f[86] % GUN_FLASH for f in frames}, {expected}, (dx, altitude))
        frames, _ = self.guns(86 + 100, 120, 4000)
        self.assertAlmostEqual(sum(f[86] >= GUN_FLASH for f in frames) / 4000, 1 / 2, delta=0.03)
        # The battleship's guns stand at its deck, 27 + 13.
        self.guns(7203, 100)
        self.assertEqual({s.altitude for s in self.ships.shown[:self.ships.shown_count]}, {40})

    def test_out_of_reach_not_flying_or_destroyed_guns_are_quiet(self):
        frames, _ = self.guns(606 + 513, 100, 4)
        self.assertNotIn(606, frames[0])
        frames, splashes = self.guns(86, 100, 50, flying=0)
        self.assertEqual((frames[-1], splashes, self.ships.hits), ({}, [], 0))
        score = C.c_uint32(0)
        self.core.Ships_Rocket(86, C.byref(score))
        frames, _ = self.guns(86, 100, 4)
        self.assertNotIn(86, frames[0])
        self.assertIn(96, frames[0])

    def test_the_distant_view_flashes_every_gun_on_screen(self):
        frames, _ = self.guns(1600, 300, 2000)   # 994 px from the bow guns, past close reach
        shown = [f.get(606) for f in frames]
        self.assertEqual(set(shown), {GUN_FAR, None})
        self.assertAlmostEqual(shown.count(GUN_FAR) / 2000, 1 / 2, delta=0.04)
        self.assertEqual(self.ships.nearest, 65535)   # out of reach: no fire

    def test_fire_damages_the_engine_and_is_heard(self):
        hits = C.c_uint16.in_dll(self.core, 'g_EngineHits')
        hits.value = 0
        self.guns(600, 60, 2000)
        # 8 guns, 0..40 px off at altitude 60: each hits about 20% x (1 - d/512).
        self.assertGreater(hits.value, 2000 * 4 * 0.12)
        self.assertEqual(hits.value, self.ships.hits)
        self.guns(606 + 300, 60)
        self.assertEqual(self.ships.nearest, 300)

    def test_shell_splashes_fall_near_a_low_plane(self):
        _, splashes = self.guns(600, 150, 2000)
        self.assertTrue(splashes)
        self.assertTrue(all(568 <= x <= 631 for x, _ in splashes), splashes[:5])
        for _ in range(6):
            self.guns(5000, 150)
        self.assertEqual(self.ships.splashes, 0)   # each lives 6 updates
        _, splashes = self.guns(600, 201, 500)
        self.assertEqual(splashes, [])             # above altitude 200, none


if __name__ == '__main__':
    unittest.main()
