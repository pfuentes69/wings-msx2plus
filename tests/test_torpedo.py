"""The torpedo (src/core/rockets.c, src/core/ships.c) against a model of the
Amiga code written from the 68000 routines: release 0x088e, the fall 0x0b58,
the surface 0x0bf0..0x0d32, the run 0x0d50, the kill window 0x1ae2 and the
hull hit 0x4986 (docs/torpedo.md). Built on map j (test_rockets.py's
library): a destroyer at x 8..655, the carrier at 3520..4295, a battleship
at 7160..7935, open sea between."""
import ctypes as C
import random
import unittest

import test_rockets
from test_rockets import Combat, Flight, s16, s32


FALLING, RUNNING = 1, 2
SPEED = 0x45000
IMPACT, SPLASH = 3, 4
TORPEDO_BURST, TORPEDO_HIT, TORPEDO_DUD = 2, 3, 4
SEA, DECK = 0, 1


class Original:
    """The Amiga torpedo, in its own terms (68000 word and long arithmetic)."""
    def __init__(self, hstep, vstep, left, x, altitude):
        self.x = s32(x << 16)
        self.vx = s32((-hstep if left else hstep) << 16)
        self.vy = s32(vstep << 16)
        self.y = altitude + 11                   # 0x08ba
        self.state, self.life = FALLING, 0

    def tick(self, surface, burst_altitude):
        if self.state == FALLING:                # 0x0b58
            q = int(s16(self.vx >> 16) / 10)     # divs.w: toward zero
            self.vx = s32(self.vx - (q << 16))
            self.x = s32(self.x + self.vx)
            self.vy = s32(self.vy - 0x6000)
            d5 = s16(s32((self.y << 16) + self.vy) >> 16)
            x = s16(self.x >> 16)
            burst = burst_altitude(x)
            if d5 > burst:
                self.y = d5
                return 'falling'
            self.y = burst                       # 0x0c76
            if surface(x) != SEA or s16(self.vy >> 16) < -5:
                self.state = 0
                return ('burst', x, burst)
            self.vx = -SPEED if s16(self.vx >> 16) < 0 else SPEED   # 0x0d18
            self.life, self.state = 200, RUNNING
        self.life -= 1                           # 0x0d50
        if self.life <= 0:
            self.state = 0
            return 'gone'
        self.x = s32(self.x + self.vx)
        x = s16(self.x >> 16)
        if surface(x) != SEA:
            self.state = 0
            return ('hit', x)
        return 'running'


class TorpedoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_rockets.RocketTests.setUpClass.__func__(cls)
        core = cls.core
        core.Torpedo_Launch.argtypes = [C.POINTER(Combat), C.c_uint16, C.c_uint16, C.c_int16, C.c_int16, C.c_uint8]
        core.Torpedo_Launch.restype = C.c_uint8
        core.Torpedo_Kill.argtypes = [C.POINTER(Combat), C.c_int16, C.c_uint8]
        core.Ships_Torpedo.argtypes = [C.c_uint16]
        core.Ships_Torpedo.restype = C.c_uint8

    tearDownClass = classmethod(test_rockets.RocketTests.tearDownClass.__func__)
    setUp = test_rockets.RocketTests.setUp
    burst_altitude = test_rockets.RocketTests.burst_altitude

    def release(self, hstep, vstep, left, x, altitude, bob=3):
        s = Combat()
        s.bob = bob
        vx = round(hstep * 256 / 12) * (-1 if left else 1)
        vy = -round(vstep * 256 / 12)
        self.assertEqual(self.core.Torpedo_Launch(C.byref(s), x, 1200 - altitude, vx, vy, left), 1)
        self.assertEqual(self.core.Torpedo_Launch(C.byref(s), x, 1200 - altitude, vx, vy, left), 0)   # one at a time
        return s

    def drop(self, hstep, vstep, left, x, altitude, bob=3):
        """Release and run both models to the end. Returns the outcome and
        the C state."""
        s = self.release(hstep, vstep, left, x, altitude, bob)
        o = Original(hstep, vstep, left, x, altitude)
        t = s.torpedo
        surface = self.core.Mission_Surface
        for tick in range(300):
            outcome = o.tick(lambda bx: surface(bx & 0xffff), lambda bx: self.burst_altitude(bx & 0xffff, bob))
            self.core.Rockets_Step(C.byref(s), x, 1200 - altitude, left)
            if outcome in ('falling', 'running'):
                self.assertEqual((t.live, t.x, t.y, t.vx), (o.state, o.x, o.y, o.vx), tick)
                if outcome == 'falling':
                    self.assertEqual(t.vy, o.vy, tick)
                continue
            self.assertEqual(t.live, 0, tick)
            slots = [p for p in s.projectile[2:] if p.kind]
            if outcome == 'gone':
                self.assertEqual(slots, [])   # no explosion, no sound
            elif outcome[0] == 'burst':
                _, bx, altitude = outcome
                p, = slots
                kind = SPLASH if surface(bx) == SEA else IMPACT
                # x is a 16384 px ring (open sea past the map's ends).
                self.assertEqual((p.x >> 2, p.y >> 2, p.life, p.vx, p.kind),
                                 (bx % 16384, 1200 - altitude + 12, 6, TORPEDO_BURST, kind))
            else:
                _, hx = outcome
                p, = slots
                # On a hull, the sea explosion at the waterline.
                self.assertEqual((p.x >> 2, p.y >> 2, p.life, p.vx, p.kind),
                                 (hx % 16384, 1200, 6, TORPEDO_HIT, SPLASH if surface(hx) == DECK else IMPACT))
            return outcome, s
        self.fail('the torpedo never ended')

    def test_the_enemy_torpedo_runs_into_the_carrier(self):
        # 0xe08c: dropped by a torpedo plane at altitude 20, speed 900,
        # flying left, 870 px short of the carrier's near end (R = 4280).
        self.core.Torpedo_Drop.argtypes = [C.POINTER(Combat), C.c_int16, C.c_int16, C.c_int16, C.c_int8]
        s = Combat()
        s.bob = 3
        self.core.Torpedo_Drop(C.byref(s), 4280 + 870, 20, 900, -1)
        e = s.enemy
        self.assertEqual((e.live, e.x >> 16, e.y, e.vx, e.left), (FALLING, 5150, 35, -900 * 0x28f, 1))
        self.assertEqual(s.torpedo.live, 0)
        o = Original(0, 0, 1, 5150, 20)
        o.x, o.y, o.vx = s32(5150 << 16), 35, -900 * 0x28f
        surface = self.core.Mission_Surface
        for tick in range(300):
            outcome = o.tick(lambda bx: surface(bx & 0xffff), lambda bx: self.burst_altitude(bx & 0xffff, 3))
            self.core.Rockets_Step(C.byref(s), 0, 1100, 0)
            if outcome in ('falling', 'running'):
                self.assertEqual((e.live, e.x, e.y, e.vx), (o.state, o.x, o.y, o.vx), tick)
                continue
            break
        self.assertEqual(outcome[0], 'hit')
        self.assertTrue(4100 < outcome[1] <= 4296, outcome)   # the carrier's hull (3520..4295)
        hull = self.ships.hull[4]
        self.assertEqual(self.core.Ships_Torpedo(outcome[1]), 2)   # COMBAT_SKY_RED
        self.assertEqual(self.ships.hull[4], hull - 1)
        # The kill window destroys the enemy's torpedo as it does the player's.
        self.core.Torpedo_Drop(C.byref(s), 5000, 20, 900, -1)
        self.core.Torpedo_Kill(C.byref(s), 5005, 10)
        self.assertEqual(s.enemy.live, 0)

    def test_fall_and_run_match_the_original_tick_for_tick(self):
        rng = random.Random(11)
        kinds = set()
        for _ in range(300):
            x = rng.choice((rng.randint(700, 3400), rng.randint(4400, 7100), rng.randint(100, 600),
                            rng.randint(3600, 4200), rng.randint(7200, 7900)))
            outcome, _ = self.drop(rng.randint(0, 14), rng.randint(-4, 3), rng.randint(0, 1), x,
                                   rng.randint(12, 120), rng.randint(0, 5))
            kinds.add(outcome if isinstance(outcome, str) else outcome[0])
        self.assertEqual(kinds, {'burst', 'hit', 'gone'})

    def test_the_release_envelope(self):
        # Level flight: it must meet the sea within 13 ticks, from 41 px up.
        for hstep in (0, 6, 14):
            outcome, _ = self.drop(hstep, 0, 0, 1500, 41)
            self.assertEqual(outcome, 'gone', hstep)    # ran 199 moves over open sea
            outcome, _ = self.drop(hstep, 0, 0, 1500, 42)
            self.assertEqual(outcome[0], 'burst', hstep)

    def test_a_run_lasts_199_moves_and_strikes_the_first_hull(self):
        s = self.release(10, 0, 0, 1500, 30)
        surfaced = None
        for tick in range(300):
            self.core.Rockets_Step(C.byref(s), 1500, 1170, 0)
            if surfaced is None and s.torpedo.live == RUNNING:
                surfaced, start = tick, s.torpedo.x >> 16
                self.assertEqual(s.torpedo.sound, 1)    # the splash at the surface
            if not s.torpedo.live:
                break
        self.assertEqual(tick - surfaced, 199)
        self.assertEqual(((s.torpedo.x - SPEED * 199) >> 16), start - 4)   # the surfacing tick moved too
        # Left from x 900: the destroyer's stern (655) stops it.
        outcome, s = self.drop(10, 0, 1, 900, 30)
        self.assertEqual(outcome[0], 'hit')
        self.assertEqual(self.core.Ships_Find(outcome[1]), 0)

    def test_torpedo_hits_wear_down_the_hulls(self):
        hull = self.ships.hull
        self.assertEqual((hull[0], hull[1], hull[4]), (1, 2, 4))
        self.assertEqual(self.core.Ships_Torpedo(2000), 0)     # open sea
        for x, ship, hits in ((300, 0, 1), (7500, 1, 2), (4000, 4, 4)):
            for left in range(hits - 1, -1, -1):
                self.assertEqual(self.core.Ships_Torpedo(x), 2)   # red
                self.assertEqual(hull[ship], left)
        self.assertEqual(self.core.Ships_Torpedo(300), 2)      # sinking already: no change
        self.assertEqual((hull[0], self.ships.hull_hits), (0, 8))

    def test_splashes_and_bursts_destroy_a_torpedo(self):
        for live in (FALLING, RUNNING):
            s = self.release(0, 0, 0, 2000, 100)
            s.torpedo.live = live
            self.core.Torpedo_Kill(C.byref(s), 2011, 10)
            self.assertEqual(s.torpedo.live, live)
            self.core.Torpedo_Kill(C.byref(s), 1990, 10)
            self.assertEqual(s.torpedo.live, 0)
            p, = [p for p in s.projectile[2:] if p.kind]
            self.assertEqual((p.x >> 2, p.vx, p.kind), (2000, TORPEDO_DUD, SPLASH if live == RUNNING else IMPACT))

    def test_the_wake_and_the_guns(self):
        flight = Flight(y=(1200 - 30) << 8)
        buf = C.create_string_buffer(64)
        s = Combat()
        t = s.torpedo
        t.live, t.life, t.x, t.vx = RUNNING, 150, 2000 << 16, SPEED
        self.core.Ships_Guns(C.byref(flight), 2000, 1, buf, buf, C.byref(s))
        self.assertEqual([(w.x, w.life) for w in self.ships.splash if w.life], [(2000, 4)])
        # Low near the destroyer's bow guns (566..606), the shell splashes
        # at the plane's x +-32 soon destroy a torpedo there.
        t.x = 700 << 16
        for update in range(200):
            self.core.Ships_Guns(C.byref(flight), 700, 1, buf, buf, C.byref(s))
            if not t.live:
                break
        self.assertEqual(t.live, 0)
        self.assertLess(update, 100)
        p, = [p for p in s.projectile[2:] if p.kind]
        self.assertEqual((p.x >> 2, p.vx), (700, TORPEDO_DUD))


if __name__ == '__main__':
    unittest.main()
