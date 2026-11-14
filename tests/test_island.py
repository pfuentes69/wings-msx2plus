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

ROOT = Path(__file__).resolve().parents[1]
MAX_HUTS = MAX_DUGOUTS = 8
GUN_COUNT, COUNT, IMPACT = 2, 18, 3
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


class Island(C.Structure):
    _fields_ = [('hut', Building * MAX_HUTS), ('dugout', Building * MAX_DUGOUTS),
                ('soldiers', C.c_uint8 * 4), ('guns', C.c_uint8 * 4)]


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
                        *[str(ROOT / 'src' / p) for p in ('core/island.c', 'core/smoke.c', 'core/flight.c',
                                                          'core/flight_model.c')],
                        str(work / 'stub.c'), '-o', str(lib)], check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Island_Bombed.argtypes = [C.c_uint16]
        cls.core.Island_Bombed.restype = C.c_uint16
        cls.core.Island_Impacts.argtypes = [C.POINTER(Combat), C.POINTER(C.c_uint32)]
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


if __name__ == '__main__':
    unittest.main()
