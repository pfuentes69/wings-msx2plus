"""Island targets (src/core/island.c) after the Amiga impact handler 0x46dc,
garrison release 0x4b40 and hut smoke 0x4e18 (docs/research/amiga-island-combat.md).

A stub Terrain_Remap logs the map columns the wrecked huts swap."""
import ctypes as C
import json
import random
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_engine import Engine, Sortie
from test_flight_model import Flight

ROOT = Path(__file__).resolve().parents[1]
MAX_HUTS = MAX_DUGOUTS = 8
GUN_COUNT, COUNT, IMPACT = 2, 18, 3
GUN_NONE, GUN_FLASH, GUN_FAR = 255, 7, 14
# DATA -$63e2 - 17 .. +47 (0x4db8): the barrel by altitude row and dx / 40.
BARREL = bytes([2, 2, 3, 3, 3, 1, 2, 3, 3, 0, 1, 2, 3, 0, 1, 2, 3,
                0, 0, 0, 3, 3, 6, 6, 6, 0, 1, 1, 3, 3, 5, 5, 6, 1, 1, 2, 3, 3, 4, 5, 5,
                1, 2, 2, 3, 3, 4, 4, 5, 2, 2, 3, 3, 3, 3, 4, 4, 1, 2, 3, 2, 1, 2, 3, 2])
STUB = r"""
#include <stdint.h>
uint8_t g_TerrainDirty;
uint16_t g_Remap[256][2];
uint8_t g_RemapCount;
void Terrain_Remap(uint16_t column, uint16_t source)
{
    g_Remap[g_RemapCount][0] = column; g_Remap[g_RemapCount][1] = source;
    ++g_RemapCount; g_TerrainDirty = 3;
}
"""


class Building(C.Structure):
    _fields_ = [('garrison', C.c_uint8), ('waiting', C.c_uint8), ('release', C.c_uint8), ('wrecked', C.c_uint8),
                ('c', C.c_uint16), ('e', C.c_uint16)]


class Gun(C.Structure):
    _fields_ = [('x', C.c_uint16), ('frame', C.c_uint8)]


class Soldier(C.Structure):
    _fields_ = [('x', C.c_int16), ('dir', C.c_int8), ('frame', C.c_uint8), ('delay', C.c_uint8),
                ('state', C.c_uint8), ('base', C.c_uint8)]


MAX_SOLDIERS, WALKING, DYING, DEAD = 20, 1, 2, 3


class Island(C.Structure):
    _fields_ = [('hut', Building * MAX_HUTS), ('dugout', Building * MAX_DUGOUTS),
                ('soldiers', C.c_uint8 * 4), ('guns', C.c_uint8 * 4), ('gun', Gun * MAX_DUGOUTS),
                ('hits', C.c_uint16), ('soldier', Soldier * MAX_SOLDIERS), ('kills', C.c_uint16),
                ('out', C.c_uint8), ('alive', C.c_uint8), ('tick', C.c_uint8), ('wait', C.c_uint8),
                ('gunwork', C.c_uint8), ('cleared', C.c_uint8), ('left', C.c_uint8), ('message', C.c_uint8),
                ('bonus', C.c_uint16), ('complete', C.c_uint8)]


class Projectile(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint16), ('vx', C.c_int8), ('vy', C.c_int8),
                ('life', C.c_uint8), ('kind', C.c_uint8)]


class Combat(C.Structure):
    _fields_ = [('projectile', Projectile * COUNT), ('phase', C.c_uint8), ('cooldown', C.c_uint8),
                ('secondary_cooldown', C.c_uint8), ('secondary_pending', C.c_uint8),
                ('primary_pending', C.c_uint8), ('secondary_phase', C.c_uint8),
                ('count', C.c_uint8), ('aim_pitch', C.c_uint8),
                ('shots_fired', C.c_uint16), ('secondary_fired', C.c_uint16), ('impacts', C.c_uint16),
                ('flash', C.c_uint8), ('flash_ticks', C.c_uint8)]


class Puff(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint16), ('xf', C.c_uint8), ('yf', C.c_uint8),
                ('vx', C.c_uint8), ('vy', C.c_uint8), ('stage', C.c_uint8), ('life', C.c_uint8)]


class IslandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        (work / 'stub.c').write_text(STUB)
        lib = work / 'island.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
                        '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in ('core/island.c', 'core/soldiers.c', 'core/smoke.c', 'core/engine.c', 'core/mission.c',
                                                          'generated/mission_surfaces.c', 'core/flight.c',
                                                          'core/flight_model.c')],
                        str(work / 'stub.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Island_Bombed.argtypes = [C.c_uint16]
        cls.core.Island_Bombed.restype = C.c_uint16
        cls.core.Island_Impacts.argtypes = [C.POINTER(Combat), C.POINTER(C.c_uint32)]
        cls.core.Island_Guns.argtypes = [C.POINTER(Flight), C.c_uint16, C.c_uint8, C.POINTER(Engine), C.POINTER(Sortie)]
        cls.core.Island_Guns.restype = C.c_uint8
        cls.core.Island_Soldiers.argtypes = [C.POINTER(C.c_uint32)]
        cls.core.Island_Soldiers.restype = C.c_uint8
        cls.core.Island_Kill.argtypes = [C.c_int16, C.c_uint8]
        cls.core.Mission_Surface.argtypes = [C.c_uint16]
        cls.core.Mission_Surface.restype = C.c_uint8
        cls.island = Island.in_dll(cls.core, 'g_Island')
        cls.remap = (C.c_uint16 * 2 * 256).in_dll(cls.core, 'g_Remap')
        cls.remap_count = C.c_uint8.in_dll(cls.core, 'g_RemapCount')
        cls.puffs = (Puff * 8).in_dll(cls.core, 'g_Smoke')
        meta = json.loads((ROOT / 'assets_msx/mission_a/manifest.json').read_text())
        cls.variants, cls.layout = meta['hut_variants'], meta['island']
        cls.far_column = meta['far_column_offset']

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.core.Smoke_Reset()
        self.core.Island_Reset()
        self.remap_count.value = 0

    def remaps(self):
        return [tuple(self.remap[i]) for i in range(self.remap_count.value)]

    def test_mission_a_layout(self):
        self.assertEqual([h['x'] for h in self.layout['huts']], [2392, 2712])
        self.assertEqual([d['x'] for d in self.layout['dugouts']], [1736, 3224])
        self.assertEqual(list(self.island.soldiers), [20, 0, 0, 0])
        self.assertEqual([b.garrison for b in self.island.hut[:2]] + [b.garrison for b in self.island.dugout[:2]],
                         [5] * 4)

    def test_a_bomb_wrecks_a_hut_within_its_32_px_once(self):
        for x, points in ((2392 - 17, 0), (2392 + 16, 0), (2392 - 16, 150), (2392 + 15, 0)):
            self.assertEqual(self.core.Island_Bombed(x), points, x)
        hut = self.island.hut[0]
        self.assertEqual((hut.wrecked, hut.garrison, hut.waiting, hut.release), (1, 0, 5, 60))
        self.assertEqual(self.island.hut[1].wrecked, 0)
        self.assertEqual(self.island.soldiers[0], 20)        # they come out alive

    def test_wrecking_swaps_the_near_and_far_columns(self):
        v = self.variants[1]
        self.core.Island_Bombed(2712)
        near = [(v['near_first'] + i, v['near_variant'] + i) for i in range(v['near_count'])]
        far = [(self.far_column + v['far_first'] + i, v['far_variant'] + i) for i in range(v['far_count'])]
        self.assertEqual(self.remaps(), near + far)
        self.assertEqual(C.c_uint8.in_dll(self.core, 'g_TerrainDirty').value, 3)
        self.remap_count.value = 0
        self.core.Island_Reset()                              # a new game restores the map
        self.assertEqual(self.remaps(), [(c, c) for c, _ in near + far])

    def test_a_manned_dugout_scores_until_emptied(self):
        self.assertEqual(self.core.Island_Bombed(3224 + 10), 200)
        dugout = self.island.dugout[1]
        self.assertEqual((dugout.garrison, dugout.waiting, dugout.release, dugout.e), (0, 5, 60, 200))
        self.assertEqual(self.core.Island_Bombed(3224), 0)
        self.assertEqual(self.remaps(), [])                   # dugouts never change the map

    def test_only_fresh_bomb_detonations_count(self):
        combat = Combat(count=5)
        for i, (x, life, kind) in enumerate(((2392, 6, IMPACT), (1736, 6, IMPACT), (2712, 5, IMPACT),
                                             (3224, 6, 4)), GUN_COUNT):
            combat.projectile[i] = Projectile(x=x * 4, y=1200 * 4, life=life, kind=kind)
        combat.projectile[0] = Projectile(x=2712 * 4, y=1200 * 4, life=6, kind=IMPACT)   # cannon: no effect
        score = C.c_uint32(70000)
        self.core.Island_Impacts(C.byref(combat), C.byref(score))
        self.assertEqual(score.value, 70000 + 150 + 200)

    def test_a_wrecked_hut_smokes_49_times_with_growing_gaps(self):
        self.core.Island_Bombed(2392)
        emitted = []
        for tick in range(1300):
            before = [p.stage for p in self.puffs]
            self.core.Island_Tick()
            for p, old in zip(self.puffs, before):
                if p.stage == 5 and p.life == 6 and old != 5:
                    emitted.append(tick)
                    self.assertEqual((p.x, p.y), (2392 + 16, 1200 - 17))
            for p in self.puffs:
                p.stage = 0                                    # keep the pool free
        self.assertEqual(len(emitted), 49)
        gaps = [b - a for a, b in zip(emitted, emitted[1:])]
        self.assertEqual(emitted[0], 0)
        self.assertEqual(gaps, list(range(1, 49)))

    # Dugout guns (0x3d78, 0x4d50, 0x4f5c).
    def guns(self, world, altitude, n=1, flying=1, left=True):
        flight = Flight(y=(1200 - altitude) * 256, facing_left=left, mode=1)
        engine, sortie = Engine(), Sortie()
        self.core.Engine_Reset(C.byref(engine), C.byref(sortie))
        frames = []
        for _ in range(n):
            self.core.Island_Guns(C.byref(flight), world, flying, C.byref(engine), C.byref(sortie))
            frames.append([g.frame for g in self.island.gun[:2]])
        return frames, engine, sortie

    def test_the_barrel_follows_the_plane(self):
        self.assertEqual([g.x for g in self.island.gun[:2]], [1736, 3224])
        for dx in (-512, -400, -81, -40, -39, 0, 39, 40, 200, 512):
            for altitude in (10, 31, 32, 100, 150, 186):
                frames, _, _ = self.guns(1736 + dx, altitude, 8)
                expected = BARREL[((altitude >> 5) - 1) * 8 + int(dx / 40) + 3 + 17]
                self.assertEqual({f[0] % GUN_FLASH for f in frames}, {expected}, (dx, altitude))

    def test_the_muzzle_flashes_on_6_updates_in_16(self):
        frames, _, _ = self.guns(1736 + 100, 120, 4000)
        flashes = sum(f[0] >= GUN_FLASH for f in frames) / len(frames)
        self.assertAlmostEqual(flashes, 6 / 16, delta=0.03)

    def test_guns_are_quiet_out_of_range_on_deck_and_when_emptied(self):
        frames, _, _ = self.guns(1736 + 513, 100, 4)
        self.assertEqual(frames[0], [GUN_NONE, GUN_NONE])
        frames, engine, sortie = self.guns(1736, 100, 200, flying=0)
        self.assertEqual({tuple(f) for f in frames}, {(GUN_NONE, GUN_NONE)})
        self.assertEqual((self.island.hits, sortie.oil), (0, 128))
        self.core.Island_Bombed(1736)
        frames, _, _ = self.guns(1736, 100, 4)
        self.assertEqual(frames[0][0], GUN_NONE)

    def test_a_remanned_gun_holds_its_fire(self):
        self.island.dugout[0].c = 360
        frames, _, _ = self.guns(1736, 100, 360)
        self.assertEqual(frames[358][0], GUN_NONE)
        self.assertNotEqual(frames[359][0], GUN_NONE)

    def test_the_distant_view_shows_a_flash_on_half_the_updates(self):
        frames, _, _ = self.guns(1736 + 800, 300, 2000)       # on the distant screen
        shown = [f[0] for f in frames if f[0] != GUN_NONE]
        self.assertEqual(set(shown), {GUN_FAR})
        self.assertAlmostEqual(len(shown) / len(frames), 0.5, delta=0.05)

    def hit_rate(self, dx, altitude, n=20000):
        self.island.hits = 0
        self.guns(1736 + dx, altitude, n)
        return self.island.hits / n

    def test_hits_fall_off_with_distance(self):
        # Hit if (rand & 511) >= d and (rand & 2047) <= 409, d = max + min / 4.
        for dx, altitude in ((0, 40), (200, 100), (300, 160)):
            d = max(dx, altitude) + min(dx, altitude) // 4
            self.assertAlmostEqual(self.hit_rate(dx, altitude), (512 - d) / 512 * 410 / 2048, delta=0.012)
        self.assertEqual(self.hit_rate(449, 100, 2000), 0)
        self.assertEqual(self.hit_rate(-449, 100, 2000), 0)

    def test_hits_spark_and_wear_the_engine(self):
        _, engine, sortie = self.guns(1736, 40, 400)
        hits = self.island.hits
        self.assertGreater(hits, 40)
        # 6..9 hits to the first damage, then 6..13 each: oil -1, fuel -0..3.
        lost = 128 - sortie.oil
        self.assertTrue((hits - 9) // 13 <= lost <= (hits - 6) // 6 + 1, (hits, lost))
        self.assertTrue(lost <= 192 - sortie.fuel <= 3 * lost)
        self.core.Smoke_Reset()
        self.island.hits = 0
        flight = Flight(y=(1200 - 40) * 256, facing_left=True, mode=1)
        while not self.island.hits:
            self.core.Island_Guns(C.byref(flight), 1736, 1, C.byref(engine), C.byref(sortie))
        (puff,) = [p for p in self.puffs if p.stage]
        self.assertEqual((puff.x, puff.y, puff.stage), (1736 - 10, 1200 - 40 - 13, 6))

    # Soldiers (0x1de4, 0x1e82, 0x3eee, 0x1a8c, 0x4fee).
    def live(self):
        return [s for s in self.island.soldier if s.state & 15]

    def ticks(self, n):
        for _ in range(n):
            self.core.Island_Tick()

    def test_a_wrecked_hut_lets_its_garrison_out_one_by_one(self):
        self.core.Island_Bombed(2392)
        self.ticks(59)
        self.assertEqual(self.live(), [])                     # the first after 60 ticks
        self.ticks(1)
        (s,) = self.live()
        self.assertEqual((s.state, self.island.hut[0].waiting), (WALKING, 4))
        # x = A + (dir & 7) * 4, frame dir & 3
        self.assertEqual((s.x, s.frame), (2392 + (s.dir & 7) * 4, s.dir & 3))
        out = 1
        for _ in range(5 * 32):
            self.ticks(1)
            out = len(self.live())
        self.assertEqual((out, self.island.hut[0].waiting, self.island.hut[0].release), (5, 0, 0))

    def test_dugout_soldiers_walk_inland(self):
        self.core.Island_Bombed(1736)                        # the island's leftmost dugout
        self.core.Island_Bombed(3224)                        # its rightmost
        self.ticks(60 + 5 * 32)
        left = [s for s in self.live() if s.x < 2500]
        right = [s for s in self.live() if s.x >= 2500]
        self.assertEqual((len(left), len(right)), (5, 5))
        # Right from A + 16, left from A - 44 (1 in 32 the other way).
        for s in left:
            self.assertEqual(s.x, (1736 + 16 if s.dir >= 0 else 1736 - 44) + (s.dir & 7) * 4)
        self.assertGreaterEqual(sum(s.dir > 0 for s in left), 4)
        self.assertGreaterEqual(sum(s.dir < 0 for s in right), 4)

    def now(self, s):
        """A walker's x now: his x at update `base`, 3 px a plain step since."""
        if s.state & 7 != WALKING: return s.x
        k = (self.island.tick - s.base) & 255
        return s.x + (-3 if s.dir < 0 else 3) * k

    def put(self, x, direction, frame=0):
        s = self.island.soldier[0]
        s.x, s.dir, s.frame, s.delay, s.state, s.base = x, direction, frame, 0, WALKING, self.island.tick
        self.island.out = max(self.island.out, 1)
        self.island.alive = max(self.island.alive, 1)
        self.island.wait = 0
        return s

    def test_soldiers_walk_3_px_and_turn_at_the_water(self):
        score = C.c_uint32(0)
        s = self.put(2000, 1)
        self.core.Island_Soldiers(C.byref(score))
        self.assertEqual(self.now(s), 2003)
        for _ in range(4):
            self.core.Island_Soldiers(C.byref(score))
        self.assertEqual(self.now(s), 2015)
        s = self.put(3970, 1)                                 # the beach ends at 3976
        self.core.Island_Soldiers(C.byref(score))
        self.core.Island_Soldiers(C.byref(score))
        self.assertEqual((self.now(s), s.dir), (3970, -1))   # 3976 is sea: turned round, stepped back
        self.core.Island_Soldiers(C.byref(score))
        self.assertEqual(self.now(s), 3967)

    def test_a_soldier_walking_into_a_dugout_mans_it(self):
        score = C.c_uint32(0)
        self.core.Island_Bombed(3224)
        dugout = self.island.dugout[1]
        dugout.waiting = dugout.release = 0
        s = self.put(3224 - 19, 1)
        self.core.Island_Soldiers(C.byref(score))            # x 3208: inside [3208, 3240)
        self.assertEqual((s.state, dugout.garrison, dugout.c), (0, 1, 360))
        s = self.put(3224 + 13, -1)
        self.core.Island_Soldiers(C.byref(score))            # a second one: no new delay
        self.assertEqual((dugout.garrison, dugout.c), (2, 360))

    def test_an_empty_dugout_sends_for_the_nearest_hut_soldier(self):
        self.core.Island_Bombed(3224)
        dugout = self.island.dugout[1]
        dugout.waiting = dugout.release = 0
        frames, _, _ = self.guns(5000, 100, 199, flying=0)
        self.assertEqual(self.live(), [])
        self.guns(5000, 100, 1, flying=0)                    # 200 updates
        (s,) = self.live()
        # From the hut at 2712 (nearer to 3224 - 44 than 2392), walking right.
        self.assertEqual((self.island.hut[1].garrison, self.island.hut[0].garrison), (4, 5))
        self.assertEqual((s.dir, s.x, s.frame), (1, 2712 + 4, 1))
        self.assertEqual(dugout.e, 200)

    def test_bursts_kill_within_16_px_and_score_25(self):
        score = C.c_uint32(0)
        for i, x in enumerate((1983, 1984, 2000, 2016, 2017)):   # x - 16 .. x + 16, inclusive
            s = self.island.soldier[i]
            s.x, s.dir, s.frame, s.delay, s.state, s.base = x, 1, 0, 0, WALKING, self.island.tick
        self.island.out = self.island.alive = 5
        self.island.wait = 0
        self.core.Island_Kill(2000, 16)
        self.assertEqual([s.state for s in self.island.soldier[:5]], [WALKING, DYING, DYING, DYING, WALKING])
        self.assertEqual(self.island.soldier[1].frame, 5)
        frames = []
        for _ in range(10):
            self.core.Island_Soldiers(C.byref(score))
            frames.append(self.island.soldier[2].frame)
        self.assertEqual(frames[:9], [5, 5, 6, 6, 6, 7, 7, 7, 8])   # 3 updates a frame
        self.assertEqual((self.island.soldier[2].state, score.value, self.island.kills), (DEAD, 75, 3))
        self.assertEqual(self.island.soldiers[0], 17)

    def test_a_kill_finds_a_walker_where_he_is_now(self):
        score = C.c_uint32(0)
        s = self.put(2000, 1)
        for _ in range(12):
            self.core.Island_Soldiers(C.byref(score))
        self.assertEqual(self.now(s), 2036)
        self.core.Island_Kill(2036 - 16, 16)
        self.assertEqual((s.state & 7, s.x, s.frame), (DYING, 2036, 5))

    def test_the_last_soldier_clears_the_island_and_the_mission(self):
        score = C.c_uint32(0)
        self.assertEqual((self.island.left, self.island.cleared, self.island.message), (1, 0, 0))
        self.island.soldiers[0] = 2
        s = self.put(2000, 1)
        self.core.Island_Kill(2000, 16)
        for _ in range(12):
            self.core.Island_Soldiers(C.byref(score))
        self.assertEqual((score.value, self.island.soldiers[0], self.island.cleared), (25, 1, 0))
        s = self.put(2100, 1)
        self.core.Island_Kill(2100, 16)
        for _ in range(12):
            self.core.Island_Soldiers(C.byref(score))
        # +25, then the island's bonus (450 on map A); the only island: done.
        self.assertEqual((score.value, self.island.soldiers[0]), (25 + 25 + 450, 0))
        self.assertEqual((self.island.cleared, self.island.left, self.island.bonus), (1, 0, 450))
        self.assertEqual((self.island.message, self.island.complete), (2, 1))

    def test_impacts_and_strikes_kill_soldiers(self):
        s = self.put(2600, 1)
        combat = Combat(count=3)
        combat.projectile[0] = Projectile(x=(2600 + 16) * 4, y=1200 * 4, life=6, kind=IMPACT)   # cannon strike
        self.core.Island_Impacts(C.byref(combat), C.byref(C.c_uint32(0)))
        self.assertEqual(s.state, DYING)
        s = self.put(2600, 1)
        combat.projectile[0].life = 5                         # not fresh
        self.core.Island_Impacts(C.byref(combat), C.byref(C.c_uint32(0)))
        self.assertEqual(s.state, WALKING)

    def test_walkers_follow_the_original_step_by_step(self):
        # The counted plain steps must give exactly the original's walk: a
        # water check and a dugout check on every 3-px step.
        rng = random.Random(5)
        sea = lambda x: self.core.Mission_Surface(x & 0xFFFF) == 0
        for trial in range(300):
            self.core.Island_Reset()
            model = []
            for i in range(MAX_SOLDIERS):
                x = rng.choice([rng.randrange(8, 3976), rng.randrange(1600, 1800), rng.randrange(3100, 3300),
                                rng.randrange(8, 40), rng.randrange(3940, 3976)])
                if any(-16 <= x - a < 16 for a in (1736, 3224)): x = 2500
                d = rng.choice([-1, 1]) * rng.randrange(1, 128)
                s = self.island.soldier[i]
                s.x, s.dir, s.frame, s.delay, s.state, s.base = x, d, 0, 0, WALKING, self.island.tick
                model.append([x, d, 0])
            self.island.out = self.island.alive = MAX_SOLDIERS
            self.island.wait = 0
            for dugout in self.island.dugout[:2]:
                dugout.garrison, dugout.c = 0, 0
            for step in range(rng.choice([10, 100, 600])):
                self.core.Island_Soldiers(C.byref(C.c_uint32(0)))
                for i, m in enumerate(model):
                    if m is None: continue
                    m[2] = (m[2] + 1) % 5
                    move = -3 if m[1] < 0 else 3
                    if sea(m[0] + move): move, m[1] = -move, -m[1]
                    m[0] += move
                    if m[0] >= 0 and any(-16 <= m[0] - a < 16 for a in (1736, 3224)):
                        model[i] = None
                for i, m in enumerate(model):
                    s = self.island.soldier[i]
                    if m is None: self.assertEqual(s.state & 7, 0, (trial, step, i))
                    else:
                        self.assertEqual((self.now(s), s.dir, s.state & 7), (m[0], m[1], WALKING), (trial, step, i))
                        k = (self.island.tick - s.base) & 255
                        self.assertEqual((s.frame + k) % 5, m[2], (trial, step, i))


if __name__ == '__main__':
    unittest.main()
