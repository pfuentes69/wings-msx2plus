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
          'rev', 'speed', 'tspeed', 'x', 'vy', 'talt', 'alt', 'dist', 'draws', 'shape', 'sub', 'near', 'far')
# Shape index to frames (0xd1ea's tables; src/core/planes.c).
NEAR = [10, 9, 9, 9, 8, 8, 8, 11, 11, 12, 12, 12, 13, 13, 5, 6, 6, 6, 7, 7, 8, 8, 8, 9, 9, 9, 17, 19,
        0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5, 5, 13, 14, 14, 14, 15, 15, 2, 2, 2, 1, 1, 1, 16, 18]
FAR = [8, 9, 9, 9, 10, 10, 10, 11, 11, 12, 12, 12, 13, 13, 5, 14, 14, 14, 15, 15, 10, 10, 10, 9, 9, 9, 8, 8,
       0, 1, 1, 1, 2, 2, 2, 3, 3, 4, 4, 4, 5, 5, 13, 6, 6, 6, 7, 7, 2, 2, 2, 1, 1, 1, 0, 0]


class Plane(C.Structure):
    _pack_ = 1
    _fields_ = [('state', C.c_uint8), ('beh', C.c_uint8), ('rel', C.c_uint8), ('hit', C.c_uint8),
                ('health', C.c_int16), ('hits', C.c_int16), ('rank', C.c_int16), ('t10', C.c_int16),
                ('firing', C.c_uint8), ('facing', C.c_int8), ('frame', C.c_int16), ('t18', C.c_int16),
                ('rev', C.c_int16), ('speed', C.c_int16), ('tspeed', C.c_int16), ('x', C.c_int16),
                ('vy', C.c_int16), ('talt', C.c_int16), ('alt', C.c_int16), ('dist', C.c_int16),
                ('draws', C.c_uint8), ('shape', C.c_uint8), ('sub', C.c_int16), ('near', C.c_uint8), ('far', C.c_uint8)]


class Planes(C.Structure):
    # The host compiler aligns the words (SDCC packs): natural layout here.
    _fields_ = [('plane', Plane * 4), ('timer', C.c_int16), ('fighters', C.c_uint8), ('kills', C.c_uint8),
                ('live', C.c_uint8), ('drop', C.c_uint8), ('drop_x', C.c_int16), ('drop_alt', C.c_int16),
                ('drop_speed', C.c_int16), ('drop_facing', C.c_int8), ('wreck', C.c_int16 * 8), ('wrecks', C.c_uint8),
                ('cooldown', C.c_int16), ('left', C.c_uint8 * 4), ('parked', C.c_uint8),
                ('parked_x', C.c_int16 * 16), ('parked_alt', C.c_int16 * 16), ('parked_left', C.c_uint8 * 16),
                ('firing', C.c_uint8), ('nearest', C.c_uint16), ('lists', C.c_uint8)]


class Player(C.Structure):
    _fields_ = [('x', C.c_int16), ('alt', C.c_int16), ('facing', C.c_int8), ('mode', C.c_uint8),
                ('turn', C.c_uint8), ('speed', C.c_int16), ('climb', C.c_int16), ('gun', C.c_uint8),
                ('hstep', C.c_int16), ('engine', C.c_void_p), ('sortie', C.c_void_p)]


# The hooks planes.c calls, stubbed: they log their calls for the model to
# match. Island land at x 2000..2999; the rest is sea.
STUB = r'''
#include <stdint.h>
#include "combat.h"
CombatState g_Combat;
int32_t g_Log[512][4]; int g_Logged;
static void Log(int32_t a, int32_t b, int32_t c, int32_t d)
{ if (g_Logged < 512) { g_Log[g_Logged][0] = a; g_Log[g_Logged][1] = b; g_Log[g_Logged][2] = c; g_Log[g_Logged][3] = d; } ++g_Logged; }
void Smoke_Puff(uint16_t x, uint16_t y, uint8_t stage) { Log(1, x, y, stage); }
void Island_Kill(int16_t x, uint8_t r) { Log(2, x, r, 0); }
void Torpedo_Kill(CombatState* s, int16_t x, uint8_t r) { (void)s; Log(3, x, r, 0); }
void Ships_AddSplash(int16_t x) { Log(4, x, 0, 0); }
uint16_t Island_Bombed(uint16_t x) { Log(5, x, 0, 0); return 0; }
uint8_t Ships_Rocket(uint16_t x, uint32_t* score) { (void)score; Log(6, x, 0, 0); return 0; }
uint8_t Mission_Surface(uint16_t x) { return x >= 2000 && x < 3000 ? 2 : 0; }
#include "engine.h"
#include "ships.h"
ShipsState g_Ships;
uint8_t g_PlanesHoldTurn;
EngineState g_TestEngine; SortieState g_TestSortie;
void Engine_Damage(EngineState* e, SortieState* s, uint8_t oil, uint8_t fuel) { (void)e; (void)s; Log(7, oil, fuel, 0); }
'''
WORLD = 7608


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
        self.log, self.score, self.kills, self.wrecks, self.slide = [], 0, 0, [], 0
        self.parity = self.flee = self.firing = self.hold = self.cooldown = 0
        self.nearest, self.hits = 65535, 6

    def effect(self, kind, x, alt):
        x = s16(x + (self.rand.raw() & 7)); alt = max(16, alt + 6)
        self.log.append((1, x & 0xffff, (1200 - alt) & 0xffff, min(kind, 6)))

    def damage(self, e):
        p = 128 - e['health']
        if p > (self.rand.raw() & 63): self.effect((p >> 3) + 1, e['x'], e['alt'] + 11)

    def surface(self, x):
        return 0 if x <= 0 or x >= WORLD - 8 else (2 if 2000 <= x < 3000 else 0)

    def shot_down(self, e):
        p = 128 - e['health']
        if p > (self.rand.raw() & 63): self.effect((p >> 3) + 1, e['x'] - 16, e['alt'] + 10)
        if e['alt'] != e['talt']: return
        surface = self.surface(e['x'])
        if surface == 0 and e['speed'] < 300:
            self.slide += 1
            if self.slide >= 2: self.slide = 0; e['talt'] -= 1
            e['speed'] += 24
        e['speed'] -= 35
        self.log.append((2, e['x'], 20, 0))
        self.log.append((3, s16(e['x'] - 20), 40, 0))
        if e['speed'] > 500:
            self.log.append((5, e['x'] & 0xffff, 0, 0) if surface == 2 else (6, e['x'] & 0xffff, 0, 0))
        self.log.append((4, s16(e['x'] + e['facing'] * 4), 0, 0))
        if e['speed'] >= 100: return
        self.kills += 1
        if surface == 2:
            e.update(state=16, tspeed=6, speed=30, beh=0)
            return
        if e['beh'] not in (4, 16) and self.fighters: self.fighters -= 1
        e.update(state=0, beh=0); self.live -= 1

    def wreck(self, e):
        e['speed'] -= 1
        if not e['speed']: e['tspeed'] -= 1; e['speed'] = e['tspeed'] * 5
        if e['tspeed'] > 1:
            if not e['speed'] & 3: self.effect(e['tspeed'], e['x'] - 4, 6)
            return
        if len(self.wrecks) < 8: self.wrecks.append(-e['x'] if e['facing'] < 0 else e['x'])
        if self.fighters: self.fighters -= 1
        e.update(state=0, beh=0); self.live -= 1

    def gun(self, P):
        for e in self.p:
            if e['state'] == 0 or e['rel'] != 3 or P['climb']: continue
            if abs(P['x'] - e['x']) >= 160 or abs(P['alt'] - e['alt']) >= 20: continue
            e['hit'] = 1
            e['hits'] -= 1
            if e['hits'] > 0: continue
            self.effect(6, e['x'] - 16, e['alt'] + 10)
            e['health'] -= 8
            if e['health'] < 96:
                self.score += 350
                e.update(state=4, talt=-3, frame=0); e['beh'] &= ~8
                e['shape'] = 0 if e['facing'] == -1 else 28
                e['near'], e['far'] = NEAR[e['shape']], FAR[e['shape']]
            e['hits'] = self.rand(4) + 6

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
        if e['state'] & 4:
            if e['alt'] > e['talt']: e['alt'] = s16(e['alt'] + trunc_div(e['vy'], 100)); e['vy'] -= 10
            elif e['alt'] < e['talt']: e['alt'] = e['talt']
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

    def fighter(self, e, P):
        ptf = P['turn']
        if e['rel'] == 1:
            if e['dist'] < 160:
                if 0 < ptf < 6 and P['mode'] != 1 and e['t18'] == 0:
                    e['t18'] = s16(trunc_div(e['dist'] * 100, e['speed']) + e['rank'] * 2)
                elif e['t18'] == 0 and e['rank'] == 1:
                    e['beh'] = (e['beh'] & 8) | 2
                else:
                    e['firing'] = 0; e['talt'] = P['alt']; e['tspeed'] = s16(P['speed'] - e['rank'] * 70)
            elif e['frame'] == 0:
                e['tspeed'] = s16(e['dist'] + P['speed'] + (80 if e['rank'] == 1 else -80 * e['rank']))
        elif e['rel'] == 2:
            if P['mode'] == 0 and 0 < ptf < 11: e['tspeed'] = 900
            else: e['beh'] |= 8
        elif e['rel'] == 3:
            if e['dist'] >= 1536: e['beh'] |= 8; return
            e['t10'] -= 1
            if e['t10'] <= 0 or 0 < ptf < 6 or P['mode'] == 1:
                e['beh'] |= 8; e['t10'] = 0; return
            if e['hit'] == 1:
                e['hit'] = 0
                if e['t18'] == 0: e['t18'] = self.rand(6) + 8
                e['t10'] = 550; return
            e['tspeed'] = s16(P['speed'] - trunc_div(e['dist'], 4) + self.flee * 70)
            self.flee += 1
            if e['alt'] == e['talt']: e['talt'] = self.rand(7) * 10 + 35
        elif e['rel'] == 4:
            if P['mode'] != 0: return
            e['tspeed'] = 900
            e['talt'] = P['alt'] + 32 if e['alt'] >= P['alt'] else P['alt'] - 32
            e['t18'] = s16(trunc_div(s16(e['dist'] * 100), e['speed'] + P['hstep']))
            e['beh'] |= 8

    def attack(self, e, P):
        if e['rel'] != 1: e['beh'] = 1; return
        if P['turn'] or P['mode'] == 1:
            e['beh'] = 9; e['t18'] = trunc_div(e['dist'], trunc_div(e['speed'], 100))
        elif e['dist'] > 130: e['tspeed'] = P['speed'] + 50
        elif e['dist'] < 130: e['tspeed'] = P['speed'] - 50
        e['talt'] = P['alt']
        da = abs(P['alt'] - e['alt'])
        if (P['mode'] == 0 and e['beh'] == 2 and e['rank'] == 1 and da < 8 and e['frame'] == 0 and e['dist'] < 160
                and P['facing'] == e['facing'] and s16(s16(e['x'] - P['x']) ^ P['facing']) < 0):
            e['firing'] = 1
            if e['alt'] == P['alt'] and self.parity:
                self.hits = (self.hits - 1) & 255
                if self.hits == 0:
                    self.log.append((7, 8, self.rand(32), 0))
                    self.hits = self.rand(5) + 6
        else:
            e['firing'] = 0

    def tick(self, P, fire, carrier):
        self.parity ^= 1
        self.timer_tick(P, fire, carrier)
        self.flee = 0
        for e in self.p:
            if e['state'] == 0: continue
            self.relation(e, P)
            self.rank()
            if e['state'] == 2:
                self.damage(e)
                kind = e['beh'] & ~8
                if kind in (1, 2): (self.fighter if kind == 1 else self.attack)(e, P)
                elif kind == 4: self.torpedo(e, P)
                elif kind == 16: self.dropped(e)
                if e['state'] == 0: continue
                self.speed(e)
            elif e['state'] == 4: self.shot_down(e)
            else: self.wreck(e)
            if e['state'] == 0: continue
            if e['state'] != 16: self.motion(e, P)
            idx = e['frame']
            if e['beh'] & 4 and not e['frame']: idx = 26
            e['shape'] = idx if e['facing'] == -1 else idx + 28
            e['near'], e['far'] = NEAR[e['shape']], FAR[e['shape']]
        if P.get('gun') and self.live: self.gun(P)
        self.firing, self.nearest, self.hold = 0, 65535, 0
        for e in self.p:
            if not e['state'] or e['state'] > 2: continue
            d = (abs(e['x'] - P['x']) + abs(e['alt'] - P['alt'])) & 0xffff
            self.nearest = min(self.nearest, d)
            self.firing |= e['firing']
            if e['beh'] == 1 and e['rel'] == 3 and e['frame'] == 13: self.hold = 1
        if self.cooldown: self.cooldown -= 1


class PlanesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        lib = work / 'planes.so'
        (work / 'stub.c').write_text(STUB)
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I' + str(ROOT / 'src/core'),
                        '-I' + str(ROOT / 'src/generated/map_a'),
                        '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', f'-DWINGS_CARRIER_X={CARRIER_X}u',
                        '-DWINGS_FLIGHT_MAX_Y=1200u', f'-DWINGS_WORLD_WIDTH={WORLD}u',
                        str(ROOT / 'src/core/planes.c'), str(ROOT / 'src/core/fighters.c'), str(work / 'stub.c'),
                        '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Planes_Spawn.argtypes = [C.c_uint8, C.c_int16, C.c_int16, C.c_int8]
        cls.core.Planes_Spawn.restype = C.c_uint8
        cls.core.Planes_Tick.argtypes = [C.POINTER(Player), C.c_uint8, C.c_uint8, C.POINTER(C.c_uint32), C.POINTER(C.c_uint16)]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.state = Planes.in_dll(self.core, 'g_Planes')
        self.core.Planes_NewGame()
        self.model = Model()
        self.score, self.kills = C.c_uint32(0), C.c_uint16(0)
        C.c_int.in_dll(self.core, 'g_Logged').value = 0
        self.engine = C.addressof(C.c_uint8.in_dll(self.core, 'g_TestEngine'))
        self.sortie = C.addressof(C.c_uint8.in_dll(self.core, 'g_TestSortie'))
        C.c_uint8.from_address(self.engine + 10).value = 6   # EngineState.hits

    def calls(self):
        n = C.c_int.in_dll(self.core, 'g_Logged').value
        log = (C.c_int32 * 4 * 512).in_dll(self.core, 'g_Log')
        return [tuple(log[i]) for i in range(min(n, 512))]

    def compare(self, what):
        for i in range(4):
            got = {f: getattr(self.state.plane[i], f) for f in FIELDS}
            want = self.model.p[i]
            if want['state'] == 0 and got['state'] == 0: continue
            self.assertEqual(got, want, (what, i))
        self.assertEqual((self.state.timer, self.state.live, self.state.fighters),
                         (self.model.timer, self.model.live, self.model.fighters), what)
        self.assertEqual((self.score.value, self.kills.value), (self.model.score, self.model.kills), what)
        self.assertEqual(list(self.state.wreck[:self.state.wrecks]), self.model.wrecks, what)
        self.assertEqual(self.calls(), self.model.log[:512], what)
        self.assertEqual((self.state.firing, self.state.nearest, C.c_uint8.in_dll(self.core, 'g_PlanesHoldTurn').value,
                          C.c_uint8.from_address(self.engine + 10).value, self.state.cooldown),
                         (self.model.firing, self.model.nearest, self.model.hold, self.model.hits, self.model.cooldown), what)

    def put(self, i, **fields):
        for k, v in fields.items():
            setattr(self.state.plane[i], k, v)
            self.model.p[i][k] = v

    def tick(self, P, fire=0, carrier=1):
        self.core.Planes_Tick(C.byref(Player(**P, engine=self.engine, sortie=self.sortie)), fire, carrier,
                              C.byref(self.score), C.byref(self.kills))
        self.model.tick(P, fire, carrier)

    def test_against_the_model(self):
        rng = random.Random(7)
        for run in range(150):
            self.setUp()
            P = dict(x=rng.randrange(1500, 10000), alt=rng.randrange(20, 400), facing=rng.choice((-1, 1)),
                     mode=0, turn=0, speed=rng.randrange(1000, 1401), climb=0, gun=0, hstep=rng.randrange(10, 15))
            for _ in range(rng.randrange(1, 4)):
                kind = rng.choice((0, 1))
                args = (kind, s16(P['x'] + rng.randrange(-1500, 1500)), rng.randrange(33, 300), rng.choice((-1, 1)))
                self.assertEqual(self.core.Planes_Spawn(*args), self.model.spawn(*args))
            for i in range(4):
                if self.model.p[i]['state'] and rng.random() < 0.3:
                    self.put(i, beh=self.model.p[i]['beh'] | 8)
                if self.model.p[i]['state'] and rng.random() < 0.4:
                    self.put(i, health=rng.choice((96, 104, 112, 120)), hits=1)   # nearly shot down
                if self.model.p[i]['state'] and rng.random() < 0.2:   # already falling, near the end
                    self.put(i, state=4, talt=-3, alt=rng.choice((-3, 10, 60)), speed=rng.choice((300, 600, 1400)),
                             vy=0, x=rng.choice((2400, 5000)))
            self.state.timer = self.model.timer = rng.choice((0, 3, 40, 900))
            for t in range(200):
                P['x'] = s16(P['x'] + P['facing'] * rng.randrange(8, 15))
                P['alt'] = max(10, P['alt'] + rng.randrange(-3, 4))
                if rng.random() < 0.02: P['facing'] = -P['facing']
                P['turn'] = rng.choice((0, 0, 0, 3, 18))
                P['mode'] = rng.choice((0,) * 20 + (1, 4))
                P['climb'] = rng.choice((0, 0, 0, 600))
                P['gun'] = rng.random() < 0.5
                self.tick(P, fire=rng.random() < 0.05)
                self.compare((run, t))

    def shoot(self, x, island=False):
        # A fighter 100 px ahead of the player, both flying right, level.
        self.core.Planes_Spawn(0, x + 100, 150, 1)
        p = self.state.plane[3]
        P = Player(engine=self.engine, sortie=self.sortie, x=x, alt=150, facing=1, mode=0, turn=0, speed=1000, climb=0, gun=1)
        ticks = 0
        while p.state == 2 and ticks < 1000:
            P.x, P.alt = p.x - 100, p.alt   # keep it in the box (it goes down to 50)
            p.t18, p.beh, p.t10 = 0, p.beh & ~8, 100   # no break-away (the AI: test_against_the_model)
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            ticks += 1
        return p, ticks

    def test_nineteen_hits_shoot_a_plane_down(self):
        p, ticks = self.shoot(5000)
        self.assertEqual((p.state, p.talt, self.score.value, p.health), (4, -3, 350, 88))
        self.assertTrue(19 * 6 - 1 <= ticks <= 5 + 18 * 9 + 2, ticks)   # 5..7, then 6..9 a hit
        self.assertEqual(self.kills.value, 0)   # counted at rest

    def test_shot_down_at_sea_slides_and_is_gone(self):
        p, _ = self.shoot(5000)
        P = Player(engine=self.engine, sortie=self.sortie, x=1500, alt=300, facing=1, mode=0, turn=0, speed=1000, climb=0, gun=0)
        for _ in range(400):
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            if not p.state: break
        self.assertEqual((p.state, self.kills.value, self.state.live, self.state.fighters, self.state.wrecks), (0, 1, 0, 0, 0))

    def test_shot_down_over_an_island_burns_then_stays(self):
        p, _ = self.shoot(5000)
        p.x, p.alt = 2100, -3   # down on the island (x 2000..2999), sliding
        P = Player(engine=self.engine, sortie=self.sortie, x=1500, alt=300, facing=1, mode=0, turn=0, speed=1000, climb=0, gun=0)
        states = []
        for _ in range(500):
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            states.append(p.state)
            if not p.state: break
        self.assertIn(16, states)
        self.assertEqual(states.count(16), 100)   # 30 + 25 + 20 + 15 + 10 ticks burning
        self.assertEqual((self.kills.value, self.state.wrecks), (1, 1))
        self.assertTrue(2000 <= self.state.wreck[0] < 3000, self.state.wreck[0])

    def test_climbing_or_turning_the_gun_misses(self):
        self.core.Planes_Spawn(0, 5100, 150, 1)
        p = self.state.plane[3]
        for climb, gun in ((600, 1), (0, 0)):
            for _ in range(200):
                P = Player(engine=self.engine, sortie=self.sortie, x=p.x - 100, alt=p.alt, facing=1, mode=0, turn=0, speed=1000, climb=climb, gun=gun)
                self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            self.assertEqual((p.health, p.state), (240, 2), (climb, gun))

    def test_a_fighter_on_the_tail_attacks_and_hits(self):
        # 120 px behind the player, same heading and altitude: rank 1, the
        # attack; it fires, and on odd ticks at equal altitude the hit
        # counter runs down (oil -8 and fuel -0..31 each time it runs out).
        self.core.Planes_Spawn(0, 4880, 150, 1)
        p = self.state.plane[3]
        fired = 0
        for _ in range(300):
            P = Player(engine=self.engine, sortie=self.sortie, x=p.x + 120, alt=p.alt, facing=1, mode=0, turn=0,
                       speed=1000, climb=0, gun=0, hstep=10)
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            fired += p.firing
        damage = [c for c in self.calls() if c[0] == 7]
        self.assertEqual(p.beh & 7, 2)
        self.assertGreater(fired, 250)
        self.assertTrue(damage and all(c[1] == 8 and 0 <= c[2] < 32 for c in damage), damage)
        self.assertTrue(150 // 10 - 2 <= len(damage) <= 150 // 6 + 1, len(damage))   # every 6..10 odd ticks

    def test_ships_launch_their_planes_on_map_j(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'stub.c').write_text(STUB)
            subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-I' + str(ROOT / 'src/core'),
                            '-I' + str(ROOT / 'src/generated/map_j'), '-shared', '-fPIC', '-DWINGS_CARRIER_X=3960u',
                            '-DWINGS_FLIGHT_MAX_Y=1200u', '-DWINGS_WORLD_WIDTH=7944u',
                            str(ROOT / 'src/core/planes.c'), str(ROOT / 'src/core/fighters.c'), str(work / 'stub.c'),
                            '-o', str(work / 'j.so')], check=True, capture_output=True)
            j = C.CDLL(str(work / 'j.so'))
            j.Planes_Tick.argtypes = [C.POINTER(Player), C.c_uint8, C.c_uint8, C.POINTER(C.c_uint32), C.POINTER(C.c_uint16)]
            j.Planes_NewGame(); j.Planes_Reset()
            state = Planes.in_dll(j, 'g_Planes')
            hull = (C.c_uint8 * 5).from_address(C.addressof(C.c_uint8.in_dll(j, 'g_Ships')) + 218)
            hull[0], hull[1], hull[4] = 1, 2, 4
            self.assertEqual((state.parked, list(state.left[:2])), (0, [4, 6]))
            engine = C.addressof(C.c_uint8.in_dll(j, 'g_TestEngine'))
            P = Player(x=7000, alt=300, facing=1, mode=1, turn=0, speed=0, climb=0, gun=0, hstep=0,
                       engine=engine, sortie=engine)
            launches = []
            for t in range(400):
                j.Planes_Tick(C.byref(P), 0, 0, C.byref(self.score), C.byref(self.kills))
                if state.fighters > len(launches):
                    new = [state.plane[i] for i in range(4) if state.plane[i].state]
                    launches.append((t, sorted((q.x, q.alt) for q in new)))
            # The ghost (7480, -32768: it climbs, still far below) first, then
            # entry 4 (7706, 47) 100 ticks later; the battleship's max is 2.
            self.assertEqual(len(launches), 2)
            self.assertEqual(launches[1][0] - launches[0][0], 100)
            self.assertIn(7480, [x for x, _ in launches[0][1]])
            self.assertEqual((state.fighters, list(state.left[:2]), state.parked), (2, [4, 4], 8))
            self.assertTrue(all(state.parked_alt[k] > 0 for k in range(state.parked)))

    def test_level_step_at_minimum_speed(self):
        # The note's inferred sequence: trunc(factor x 9).
        steps = []
        for frame in range(26):
            self.setUp()
            self.core.Planes_Spawn(1, 1000, 100, 1)   # a torpedo plane: no fighter AI
            p = self.state.plane[3]
            p.frame, p.alt, p.talt = frame, 100, 100
            self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=5000, alt=300, facing=1, mode=0, turn=0, speed=1000)), 0, 1, C.byref(self.score), C.byref(self.kills))
            steps.append(p.x - 1000)
        self.assertEqual(steps, [9, 8, 8, 8, 7, 7, 6, 6, 5, 4, 3, 2, 2, 1, 0, 0, 2, 4, 5, 6, 6, 7, 7, 8, 8, 8])

    def test_a_turn_takes_75_ticks_and_flips_once(self):
        self.core.Planes_Spawn(1, 2000, 0, 1)
        p = self.state.plane[3]
        p.beh |= 8
        p.sub = 2   # left over from a full turn
        P = Player(engine=self.engine, sortie=self.sortie, x=100, alt=300, facing=1, mode=0, turn=0, speed=1000)
        frames, ticks = [], 0
        while p.beh & 8:
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
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
            self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=2100, alt=300, facing=1, mode=0, turn=0, speed=1000)), 0, 1, C.byref(self.score), C.byref(self.kills))
            p.tspeed = 1300
        self.assertIn(p.speed, (1310, 1311))

    def test_timer_firing_holds_it_and_the_side_follows_the_carrier(self):
        self.state.timer = 100
        self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 1, 1, C.byref(self.score), C.byref(self.kills))
        self.assertEqual(self.state.timer, 750)
        self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 1, 1, C.byref(self.score), C.byref(self.kills))
        self.assertEqual(self.state.timer, 750)   # no count-down while firing
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=3000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 1, C.byref(self.score), C.byref(self.kills))
        p = self.state.plane[3]
        self.assertEqual((p.state, p.beh, p.facing, p.alt), (2, 4, 1, 50))
        self.assertEqual(p.x, s16(3000 - 6144) + 9)   # it moved on its first tick
        self.assertEqual(self.core.Planes_Spawn(1, 0, 0, 1), 0)   # one armed torpedo plane at a time
        self.core.Planes_NewGame()
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=9000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 1, C.byref(self.score), C.byref(self.kills))
        self.assertEqual((self.state.plane[3].facing, self.state.plane[3].x), (-1, s16(9000 + 6144) - 9))
        self.core.Planes_NewGame()
        self.state.timer = 1
        self.core.Planes_Tick(C.byref(Player(engine=self.engine, sortie=self.sortie, x=9000, alt=300, facing=-1, mode=0, turn=0, speed=1000)), 0, 0, C.byref(self.score), C.byref(self.kills))
        self.assertEqual((self.state.timer, self.state.live), (1, 0))   # no carrier: no count-down

    def test_torpedo_plane_descends_and_drops_short_of_the_carrier(self):
        self.core.Planes_Spawn(1, L - 1500, 0, 1)
        p = self.state.plane[3]
        P = Player(engine=self.engine, sortie=self.sortie, x=0, alt=300, facing=-1, mode=0, turn=0, speed=1000)
        drop = None
        for _ in range(300):
            self.core.Planes_Tick(C.byref(P), 0, 1, C.byref(self.score), C.byref(self.kills))
            if p.beh == 16 and drop is None: drop = p.x
        self.assertIsNotNone(drop)
        self.assertTrue(L - 1000 < drop < L, drop)
        self.assertTrue(0 < self.state.timer < 500, self.state.timer)   # 500 at the drop, counting down


if __name__ == '__main__':
    unittest.main()
