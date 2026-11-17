"""Sinking ships (src/core/ships.c, docs/ship-sinking.md) against a model of
the Amiga sinking clock 0x1cae / 0x1cd8: the step times, the bonus and the
"sunk" message at step 10 (0x5640, 0x5694), the sea at step 120, the
stages shown to the terrain, the guns falling silent. Built on map j
(test_rockets.py's library): a destroyer (1 hit) and a battleship (2)."""
import ctypes as C
import re
import unittest

import test_island
import test_rockets
from test_rockets import Combat, Flight, MAP

MESSAGE_CLEARED, MESSAGE_MISSION = 1, 2
DESTROYER, BATTLESHIP = 0, 1


def original_steps(first, ticks):
    """0x1cd8 from the fatal hit: the tick of each step (1-based)."""
    wait, interval, steps = first, 20, []
    for tick in range(1, ticks + 1):
        wait -= 1                   # subq.w #1, +16; bgt
        if wait > 0:
            continue
        steps.append(tick)          # +14 += 1
        wait = interval             # +16 = +18
        if interval:
            interval -= 1           # +18 -= 1 unless 0
    return steps


class SinkHull(C.Structure):   # msx/terrain_patch.h
    _fields_ = [('left', C.c_uint16), ('right', C.c_uint16), ('rows', C.c_uint8)]


class SinkingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_rockets.RocketTests.setUpClass.__func__(cls)
        core = cls.core
        core.Ships_Torpedo.argtypes = [C.c_uint16]
        core.Ships_Torpedo.restype = C.c_uint8
        core.Ships_Guns.argtypes = [C.POINTER(Flight), C.c_uint16, C.c_uint8, C.c_void_p, C.c_void_p, C.POINTER(Combat)]
        core.Ships_Guns.restype = C.c_uint8
        header = (MAP / 'mission_ships.h').read_text()
        tiles = (MAP / 'mission_tiles.h').read_text()
        def table(name):
            return [int(v) for v in re.search(name + r'\[\d+\] = \{([^}]*)\}', header).group(1).split(',')]
        cls.bonus = table('s_ShipBonus')
        cls.far_first, cls.far_count, cls.entry = table('s_ShipFarFirst'), table('s_ShipFarCount'), table('s_ShipSinkEntry')
        cls.near = list(zip(table('s_ShipNearLeft'), table('s_ShipNearRight')))
        cls.far_column = int(re.search(r'#define TERRAIN_FAR_COLUMN (\d+)', tiles).group(1))
        cls.sink_table = int(re.search(r'#define TERRAIN_SINK_TABLE (\d+)', tiles).group(1))

    tearDownClass = classmethod(test_rockets.RocketTests.tearDownClass.__func__)

    def setUp(self):
        self.ships = test_rockets.Ships.in_dll(self.core, 'g_Ships')
        self.island = test_island.Island.in_dll(self.core, 'g_Island')
        C.memset(C.byref(self.island), 0, C.sizeof(self.island))
        self.core.Ships_Reset()
        self.remaps = C.c_uint16.in_dll(self.core, 'g_RemapCount')
        self.remaps.value = 0
        self.score = C.c_uint32(0)

    def sink(self, ship, x):
        hits = self.ships.hull[ship]
        for _ in range(hits):
            self.assertEqual(self.core.Ships_Torpedo(x), 2)
        self.assertEqual((self.ships.hull[ship], self.ships.sinking > 0), (0, True))

    def tick(self, n=1, flying=1):
        for _ in range(n):
            self.core.Ships_Tick(flying, C.byref(self.score))

    def test_the_clock_follows_the_original(self):
        for ship, x, first, bonus_at, gone_at in ((DESTROYER, 300, 20, 164, 329), (BATTLESHIP, 7500, 0, 145, 310)):
            self.setUp()
            expected = original_steps(first, 400)
            # The research figures: the bonus 13.1 s after the fatal hit.
            self.assertEqual((expected[9], expected[119]), (bonus_at, gone_at))
            self.sink(ship, x)
            steps = []
            for t in range(1, 400):
                before = self.ships.step[ship]
                self.tick(flying=t % 3 != 0)   # the clock runs whether the plane flies or not
                if self.ships.step[ship] != before:
                    steps.append(t)
            self.assertEqual(steps, expected[:120])
            self.assertEqual(self.ships.step[ship], 120)

    def test_the_bonus_message_and_the_mission(self):
        self.sink(DESTROYER, 300)
        self.tick(163)
        self.assertEqual((self.score.value, self.island.message), (0, 0))
        self.tick()
        # One ship left: the "sunk" message, no mission complete.
        self.assertEqual(self.score.value, self.bonus[DESTROYER])
        self.assertEqual((self.island.message, self.island.sunk, self.island.bonus, self.island.complete),
                         (MESSAGE_CLEARED, DESTROYER + 1, 2500, 0))
        self.assertEqual(self.ships.left, 1)
        # The last ship completes the mission (no islands on map j).
        self.island.message = 0
        self.sink(BATTLESHIP, 7500)
        self.tick(145)
        self.assertEqual(self.score.value, 2500 + 4500)
        self.assertEqual((self.island.message, self.island.sunk, self.island.bonus, self.island.complete),
                         (MESSAGE_MISSION, BATTLESHIP + 1, 4500, 1))
        self.assertEqual(self.ships.left, 0)

    def test_a_pending_message_keeps_its_place(self):
        # 0x555a queues the text only when none is pending.
        self.island.message, self.island.bonus = MESSAGE_CLEARED, 450
        self.sink(DESTROYER, 300)
        self.tick(164)
        self.assertEqual(self.score.value, 2500)
        self.assertEqual((self.island.message, self.island.sunk, self.island.bonus), (MESSAGE_CLEARED, 0, 450))

    def test_the_stages_reach_the_terrain(self):
        hulls = (SinkHull * 4).in_dll(self.core, 'g_SinkHull')
        remaps = (C.c_uint16 * 2 * 512).in_dll(self.core, 'g_Remaps')
        self.sink(DESTROYER, 300)
        n = self.far_count[DESTROYER]
        shown = []
        for t in range(400):
            count = self.remaps.value
            self.tick()
            if self.remaps.value != count:
                self.assertEqual(self.remaps.value - count, n)
                stage = self.ships.step[DESTROYER] // 8
                self.assertEqual(self.ships.step[DESTROYER] % 8, 0)
                self.assertEqual((hulls[0].left, hulls[0].right, hulls[0].rows), self.near[DESTROYER] + (stage,))
                self.assertEqual(C.c_uint8.in_dll(self.core, 'g_SinkActive').value, stage)
                entry = self.sink_table + 2 * (self.entry[DESTROYER] + (stage - 1) * n)
                self.assertEqual([tuple(remaps[count + i]) for i in range(n)],
                                 [(self.far_column + self.far_first[DESTROYER] + i, entry + 2 * i) for i in range(n)])
                shown.append(stage)
        self.assertEqual(shown, list(range(1, 16)))
        # A new mission brings it back: the distant columns restored.
        count = self.remaps.value
        self.core.Ships_Reset()
        self.assertEqual([tuple(remaps[count + i]) for i in range(n)],
                         [(self.far_column + self.far_first[DESTROYER] + i, 65535) for i in range(n)])
        self.assertEqual((hulls[0].rows, C.c_uint8.in_dll(self.core, 'g_SinkActive').value), (0, 0))
        self.assertEqual((self.ships.step[DESTROYER], self.ships.hull[DESTROYER], self.ships.left), (0, 1, 2))

    def test_a_sinking_ship_falls_silent_and_goes_under(self):
        flight = Flight(y=(1200 - 60) << 8)
        buf = C.create_string_buffer(64)
        combat = Combat()
        self.core.Ships_Guns(C.byref(flight), 600, 1, buf, buf, C.byref(combat))
        self.assertGreater(self.ships.shown_count, 0)
        self.sink(DESTROYER, 300)
        hits = self.ships.hits
        for _ in range(200):
            self.core.Ships_Guns(C.byref(flight), 600, 1, buf, buf, C.byref(combat))
            self.assertEqual(self.ships.shown_count, 0)
        self.assertEqual(self.ships.hits, hits)
        # The deck comes down a pixel a step; the sea takes it at step 120.
        deck = self.core.Ships_Deck(DESTROYER)
        self.tick(20 + 20)
        self.assertEqual((self.ships.step[DESTROYER], self.core.Ships_Deck(DESTROYER)), (2, deck - 2))
        self.assertEqual(self.core.Mission_Surface(300), 1)
        self.tick(400)
        self.assertEqual((self.core.Ships_Deck(DESTROYER), self.core.Mission_Surface(300)), (0, 0))
        self.assertEqual(C.c_uint8.in_dll(self.core, 'g_ShipsGone').value, 1)
        self.assertEqual(self.core.Mission_Surface(7500), 1)   # the battleship still floats
        self.assertEqual(self.ships.sinking, 0)


if __name__ == '__main__':
    unittest.main()
