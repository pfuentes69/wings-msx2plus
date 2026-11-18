"""Enemy planes (src/core/planes.c) against a model written from the
pseudo-code in docs/research/amiga-enemy-planes.md: spawning 0xe4d0, the
relation 0xd3b4, rank 0xd476, speed 0xe64e, motion 0xd796, turns
0xd562/0xd530, the torpedo plane 0xdea4, the timer 0xbc02 and the shape
index 0xd35a. Built for map a (the carrier at 7032)."""
import ctypes as C
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARRIER_X = 7032
L, R = CARRIER_X - 440 + 16, CARRIER_X + 336 - 16
TURN = [100, 98, 95, 91, 86, 81, 75, 70, 60, 50, 40, 30, 23, 20, 0, 5, 25, 45, 60, 70, 75,
        81, 86, 91, 95, 98]
ALTSTEP = [1, 2, 2, 3, 4, 5]
FIELDS = ('state', 'beh', 'rel', 'hit', 'health', 'hits', 'rank', 't10', 'firing', 'facing', 'frame', 't18',
          'rev', 'speed', 'tspeed', 'x', 'vy', 'talt', 'alt', 'dist', 'draws', 'shape', 'sub')


class Plane(C.Structure):
    _pack_ = 1
    _fields_ = [('state', C.c_uint8), ('beh', C.c_uint8), ('rel', C.c_uint8), ('hit', C.c_uint8),
                ('health', C.c_int16), ('hits', C.c_int16), ('rank', C.c_int16), ('t10', C.c_int16),
                ('firing', C.c_uint8), ('facing', C.c_int8), ('frame', C.c_int16), ('t18', C.c_int16),
                ('rev', C.c_int16), ('speed', C.c_int16), ('tspeed', C.c_int16), ('x', C.c_int16),
                ('vy', C.c_int16), ('talt', C.c_int16), ('alt', C.c_int16), ('dist', C.c_int16),
                ('draws', C.c_uint8), ('shape', C.c_uint8), ('sub', C.c_int16)]


class Planes(C.Structure):
    _pack_ = 1
    _fields_ = [('plane', Plane * 4), ('timer', C.c_int16), ('fighters', C.c_uint8), ('kills', C.c_uint8),
                ('live', C.c_uint8)]


class Player(C.Structure):
    _fields_ = [('x', C.c_int16), ('alt', C.c_int16), ('facing', C.c_int8), ('mode', C.c_uint8),
                ('turn', C.c_uint8), ('speed', C.c_int16)]


def s16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def trunc_div(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


class Random:
    """The port's source (xorshift 7, 9, 8); the original's is the beam."""
    def __init__(self):
        self.s = 0x3c5a

    def raw(self):
        s = self.s
        s ^= (s << 7) & 0xffff
        s ^= s >> 9
        s ^= (s << 8) & 0xffff
        self.s = s
        return s

    def __call__(self, n):
        return self.raw() % n


class Model:
    def __init__(self):
        self.p = [dict.fromkeys(FIELDS, 0) for _ in range(4)]
        self.timer = self.fighters = self.live = 0
        self.rand = Random()

    def spawn(self, kind, x, alt, facing):
        e = None
        for p in self.p:
            if p['state'] == 0: e = p
            elif kind != 0 and p['beh'] & 4: return 0
        if e is None: return 0
        e.update(state=2, facing=facing, x=s16(x), talt=50, speed=900, tspeed=900, health=240,
                 hits=5 + self.rand(3), rel=0, hit=0, rank=0, frame=0, t18=0)
        if kind == 0:
            e.update(beh=1, alt=alt); self.fighters += 1
        else:
            e.update(beh=4, alt=50)
        self.live += 1
        return 1

    def relation(self, e, P):
        dx = s16(e['x'] - P['x'])
        if P['facing'] == e['facing']:
            e['rel'] = 1
            if s16(dx ^ P['facing']) >= 0:
                e['rel'] = 3
                if e['t10'] == 0: e['t10'] = 550
        else:
            e['rel'] = 4 if dx < 0 else 2
        e['dist'] = s16(-dx if dx < 0 else dx)

    def rank(self):
        a = self.p
        for i in range(4):
            if not a[i]['beh'] or a[i]['rel'] != 1: continue
            r = 1
            for j in range(i):
                if a[j]['rel'] != 1: continue
                if a[j]['dist'] < a[i]['dist']: r += 1
                else: a[j]['rank'] += 1
            a[i]['rank'] = r

    def speed(self, e):
        e['tspeed'] = min(2600, max(900, e['tspeed']))
        if e['speed'] < e['tspeed']:
            e['speed'] = min(2600, e['speed'] + (e['tspeed'] - e['speed']) // 2 + 5)
        elif e['speed'] > e['tspeed']:
            e['speed'] = max(900, e['speed'] - ((e['speed'] - e['tspeed']) // 2 - 5))

    def turn(self, e, P):
        deck = P['mode'] == 1
        fighter = (e['beh'] & 3) != 0
        if P['mode'] == 0 and fighter: e['talt'] = P['alt']
        if not P['turn'] and not deck and P['mode'] == 0 and e['frame'] >= 19 and e['rel'] in (1, 3) and fighter:
            e['frame'] = 0; e['beh'] &= ~8
            return
        e['t10'] = 0
        t = e['sub']; e['sub'] -= 1
        if t <= 0: e['sub'] = 2; e['frame'] += 1
        if e['frame'] > 25: e['frame'] = 0; e['beh'] &= ~8; return
        if e['frame'] == 14: e['facing'] = -e['facing']; e['frame'] += 1; return
        if e['frame'] != 20 or not fighter or P['mode'] != 0: return
        if e['rev'] >= 3: e['rev'] = 0; e['t10'] = 550; return
        flag = 0
        if e['rel'] == 1:
            if 0 < P['turn'] < 6 and e['t10'] == 0: e['t18'] = s16(trunc_div(e['dist'] * 100, e['speed']))
            flag = 1
        elif e['rel'] == 2:
            flag = 1 if 0 < P['turn'] < 6 else 0
        elif e['rel'] == 3:
            flag = 1
        elif e['rel'] == 4:
            if e['t10'] == 0: e['t18'] = s16(trunc_div(e['dist'] * 100, e['speed'] + P['speed']))
            flag = 1
        if flag and not deck and e['t10'] == 0:
            e['frame'] -= (e['frame'] - 13) * 2
            e['rev'] += 1

    def motion(self, e, P):
        if not e['state'] & 0x14 and P['mode'] in (4, 6, 8): e['tspeed'] = 1700
        q = trunc_div(e['speed'], 100) * e['facing']
        e['x'] = s16(e['x'] + trunc_div(q * TURN[e['frame']], 100))
        if not e['state'] & 0x14 and not e['beh'] & 4:
            if P['mode'] == 1: e['talt'] = 70
            if e['talt'] < 33: e['talt'] = 33
        d = abs(e['talt'] - e['alt'])
        k = min(d, 100) // 20
        if e['alt'] > e['talt']: e['alt'] -= ALTSTEP[k] + self.rand(2)
        elif e['alt'] < e['talt']: e['alt'] += ALTSTEP[k] + self.rand(2)
        if not e['state'] & 0x14 and e['t18']:
            e['t18'] -= 1
            if e['t18'] <= 0: e['beh'] |= 8; e['t18'] = 0
        if e['beh'] & 8 and e['state'] == 2: self.turn(e, P)

    def torpedo(self, e, P):
        if e['rel'] == 3:
            if e['hit'] == 1:
                e['hit'] = 0
                if e['t18'] == 0: e['t18'] = self.rand(6) + 8
                e['t10'] = 275
            if e['dist'] > 150: e['dist'] = 240
            if e['dist'] < 150:
                e['dist'] -= 150
                if e['alt'] == e['talt']: e['talt'] = self.rand(7) * 10 + 35
            e['tspeed'] = s16(P['speed'] - e['dist'])
        else:
            if e['facing'] == -1 and e['x'] < L - 500: e['beh'] |= 8
            elif e['facing'] == 1 and e['x'] > R + 500: e['beh'] |= 8
        if e['facing'] == -1 and e['x'] > R and e['x'] - R < 1000: e['talt'] = 20
        elif e['facing'] == 1 and e['x'] < L and L - e['x'] < 1000: e['talt'] = 20
        approaching = (e['facing'] == -1 and e['x'] > R) or (e['facing'] == 1 and e['x'] < L)
        if approaching:
            if e['alt'] == 20 and e['frame'] == 0:
                e.update(tspeed=1300, talt=60, beh=16)
                self.timer = 500
        else:
            e['t10'] -= 1
            if e['t10'] <= 0: e['beh'] |= 8; e['t10'] = 0

    def dropped(self, e):
        if e['dist'] > 2600:
            e['state'] = e['beh'] = 0; self.live -= 1
            return
        if e['rel'] == 1: e['beh'] |= 8
        elif e['rel'] == 3:
            if e['hit'] == 1:
                e['hit'] = 0
                if e['t18'] == 0: e['t18'] = self.rand(6) + 8
                e['t10'] = 275
            if e['alt'] == e['talt']: e['talt'] = self.rand(8) * 10 + 25

    def timer_tick(self, P, fire, carrier):
        d = abs(s16(0x7fff - P['x']))
        if fire:
            if self.timer and self.timer < 750: self.timer = 750
            return
        if not self.timer or not carrier: return
        self.timer -= 1
        if self.timer or d <= 0x1a00: return
        if P['x'] < L or (P['x'] <= R and self.rand.raw() & 0x8000):
            self.spawn(1, P['x'] - 0x1800, 0, 1)
        else:
            self.spawn(1, P['x'] + 0x1800, 0, -1)

    def tick(self, P, fire, carrier):
        self.timer_tick(P, fire, carrier)
        if not self.live: return
        for e in self.p:
            if e['state'] == 0: continue
            self.relation(e, P)
            self.rank()
            if e['state'] == 2:
                if e['beh'] & 4: self.torpedo(e, P)
                elif e['beh'] & 16: self.dropped(e)
                if e['state'] == 0: continue
                self.speed(e)
            if e['state'] != 16: self.motion(e, P)
            idx = e['frame']
            if e['beh'] & 4 and not e['frame']: idx = 26
            e['shape'] = idx if e['facing'] == -1 else idx + 28


class PlanesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        lib = work / 'planes.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I' + str(ROOT / 'src/core'),
                        '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', f'-DWINGS_CARRIER_X={CARRIER_X}u',
                        str(ROOT / 'src/core/planes.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Planes_Spawn.argtypes = [C.c_uint8, C.c_int16, C.c_int16, C.c_int8]
        cls.core.Planes_Spawn.restype = C.c_uint8
        cls.core.Planes_Tick.argtypes = [C.POINTER(Player), C.c_uint8, C.c_uint8]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.state = Planes.in_dll(self.core, 'g_Planes')
        self.core.Planes_NewGame()
        self.model = Model()

    def compare(self, what):
        for i in range(4):
            got = {f: getattr(self.state.plane[i], f) for f in FIELDS}
            want = self.model.p[i]
            if want['state'] == 0 and got['state'] == 0: continue
            self.assertEqual(got, want, (what, i))
        self.assertEqual((self.state.timer, self.state.live, self.state.fighters),
                         (self.model.timer, self.model.live, self.model.fighters), what)

    def put(self, i, **fields):
        for k, v in fields.items():
            setattr(self.state.plane[i], k, v)
            self.model.p[i][k] = v

    def tick(self, P, fire=0, carrier=1):
        self.core.Planes_Tick(C.byref(Player(**P)), fire, carrier)
        self.model.tick(P, fire, carrier)

    def test_against_the_model(self):
        rng = random.Random(7)
        for run in range(150):
            self.setUp()
            P = dict(x=rng.randrange(4000, 10000), alt=rng.randrange(20, 400), facing=rng.choice((-1, 1)),
                     mode=0, turn=0, speed=rng.randrange(1000, 1401))
            for _ in range(rng.randrange(1, 4)):
                kind = rng.choice((0, 1))
                args = (kind, s16(P['x'] + rng.randrange(-1500, 1500)), rng.randrange(33, 300), rng.choice((-1, 1)))
                self.assertEqual(self.core.Planes_Spawn(*args), self.model.spawn(*args))
            for i in range(4):
                if self.model.p[i]['state'] and rng.random() < 0.3:
                    self.put(i, beh=self.model.p[i]['beh'] | 8)
            self.state.timer = self.model.timer = rng.choice((0, 3, 40, 900))
            for t in range(200):
                P['x'] = s16(P['x'] + P['facing'] * rng.randrange(8, 15))
                P['alt'] = max(10, P['alt'] + rng.randrange(-3, 4))
                if rng.random() < 0.02: P['facing'] = -P['facing']
                P['turn'] = rng.choice((0, 0, 0, 3, 18))
                P['mode'] = rng.choice((0,) * 20 + (1, 4))
                self.tick(P, fire=rng.random() < 0.05)
                self.compare((run, t))

    def test_level_step_at_minimum_speed(self):
        # The note's inferred sequence: trunc(factor x 9).
        steps = []
        for frame in range(26):
            self.setUp()
            self.core.Planes_Spawn(0, 1000, 100, 1)
            p = self.state.plane[3]
            p.frame, p.alt, p.talt = frame, 100, 100
            self.core.Planes_Tick(C.byref(Player(x=5000, alt=300, facing=1, mode=0, turn=0, speed=1000)), 0, 1)
            steps.append(p.x - 1000)
        self.assertEqual(steps, [9, 8, 8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 2, 1, 0, 0, 2, 4, 5, 6, 6, 7, 7, 8, 8, 8])

    def test_a_turn_takes_75_ticks_and_flips_once(self):
        self.core.Planes_Spawn(1, 2000, 0, 1)
        p = self.state.plane[3]
        p.beh |= 8
        p.sub = 2   # left over from a full turn
        P = Player(x=100, alt=300, facing=1, mode=0, turn=0, speed=1000)
        frames, ticks = [], 0
        while p.beh & 8:
            self.core.Planes_Tick(C.byref(P), 0, 1)
            frames.append((p.frame, p.facing))
            ticks += 1
        self.assertEqual(ticks, 75)
        self.assertNotIn(14, [f for f, _ in frames])
        self.assertEqual(frames[-1], (0, -1))

    def test_speed_settles_ten_over_the_target(self):
        self.core.Planes_Spawn(1, 2000, 0, 1)
        p = self.state.plane[3]
        p.beh = 16   # after the drop: target 1300 set below
        p.tspeed = 1300
        for _ in range(30):
            self.core.Planes_Tick(C.byref(Player(x=2100, alt=300, facing=1, mode=0, turn=0, speed=1000)), 0, 1)
            p.tspeed = 1300
        self.assertIn(p.speed, (1310, 1311))

    def test_timer_firing_holds_it_and_the_side_follows_the_carrier(self):
        self.state.timer = 100
        self.core.Planes_Tick(C.byref(Player(x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 1, 1)
        self.assertEqual(self.state.timer, 750)
        self.core.Planes_Tick(C.byref(Player(x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 1, 1)
        self.assertEqual(self.state.timer, 750)   # no count-down while firing
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 1)
        p = self.state.plane[3]
        self.assertEqual((p.state, p.beh, p.facing, p.alt), (2, 4, 1, 50))
        self.assertEqual(p.x, s16(3000 - 6144) + 9)   # it moved on its first tick
        self.assertEqual(self.core.Planes_Spawn(1, 0, 0, 1), 0)   # one armed torpedo plane at a time
        self.core.Planes_NewGame()
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(x=9000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 1)
        self.assertEqual((self.state.plane[3].facing, self.state.plane[3].x), (-1, s16(9000 + 6144) - 9))
        self.core.Planes_NewGame()
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(x=9000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 0)
        self.assertEqual((self.state.timer, self.state.live), (1, 0))   # no carrier: no count-down

    def test_torpedo_plane_descends_and_drops_short_of_the_carrier(self):
        self.core.Planes_Spawn(1, L - 1500, 0, 1)
        p = self.state.plane[3]
        P = Player(x=0, alt=300, facing=-1, mode=0, turn=0, speed=1000)
        drop = None
        for _ in range(300):
            self.core.Planes_Tick(C.byref(P), 0, 1)
            if p.beh == 16 and drop is None: drop = p.x
        self.assertIsNotNone(drop)
        self.assertTrue(L - 1000 < drop < L, drop)
        self.assertTrue(0 < self.state.timer < 500, self.state.timer)   # 500 at the drop, counting down


if __name__ == '__main__':
    unittest.main()
