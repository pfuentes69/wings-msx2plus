"""Island targets (src/core/island.c) after the Amiga impact handler 0x46dc,
garrison release 0x4b40 and hut smoke 0x4e18 (docs/research/amiga-island-combat.md).

A stub Terrain_Remap logs the map columns the wrecked huts swap."""
import ctypes as C
import json
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


class Island(C.Structure):
    _fields_ = [('hut', Building * MAX_HUTS), ('dugout', Building * MAX_DUGOUTS),
                ('soldiers', C.c_uint8 * 4), ('guns', C.c_uint8 * 4), ('gun', Gun * MAX_DUGOUTS),
                ('hits', C.c_uint16)]


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
                        *[str(ROOT / 'src' / p) for p in ('core/island.c', 'core/smoke.c', 'core/engine.c', 'core/flight.c',
                                                          'core/flight_model.c')],
                        str(work / 'stub.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Island_Bombed.argtypes = [C.c_uint16]
        cls.core.Island_Bombed.restype = C.c_uint16
        cls.core.Island_Impacts.argtypes = [C.POINTER(Combat), C.POINTER(C.c_uint32)]
        cls.core.Island_Guns.argtypes = [C.POINTER(Flight), C.c_uint16, C.c_uint8, C.POINTER(Engine), C.POINTER(Sortie)]
        cls.core.Island_Guns.restype = C.c_uint8
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
        frames, _, _ = self.guns(1736 + 3000, 300, 2000)
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


if __name__ == '__main__':
    unittest.main()
