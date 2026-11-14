"""Carrier landing, bounce and crash contact rules (Amiga 0xba80/0xb8c4)."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GROUND, AIRBORNE, STALL, STALL_DIVE = 0, 1, 2, 3
NONE, LANDED, BOUNCE, CRASH = 0, 1, 2, 3
DECK_LEFT, DECK_RIGHT, DECK_Y, SEA_Y = 6593, 7361, 1160, 1200


class Flight(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint32), ('vx', C.c_int16), ('vy', C.c_int16),
                ('frame', C.c_uint8), ('facing_left', C.c_uint8), ('mode', C.c_uint8),
                ('turn_ticks', C.c_uint8), ('target_left', C.c_uint8), ('ground_tick', C.c_uint8)]


class LandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'landing.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
                        '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in ('core/landing.c', 'core/flight.c',
                          'core/aircraft.c', 'generated/hellcat_frames.c')], '-o', str(lib)],
                       check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Landing_Contact.restype = C.c_uint8
        cls.core.Landing_Bottom.restype = C.c_uint8

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def contact(self, x, y, mode=STALL, left=1, failed=0, sub=0, bottom=7, height=0):
        # bottom 7 = a resting plane (pose 0 with gear), which puts the deck
        # boundary exactly at the port's deck row 1160.
        flight = Flight(y=y * 256 + sub, vx=-40, vy=48, mode=mode, facing_left=left, target_left=left)
        return self.core.Landing_Contact(C.byref(flight), x, failed, bottom, height), flight

    def test_stall_facing_left_onto_the_deck_lands(self):
        result, flight = self.contact(7000, DECK_Y + 1)
        self.assertEqual(result, LANDED)
        self.core.Landing_Apply(C.byref(flight), result)
        self.assertEqual((flight.mode, flight.y, flight.vy, flight.facing_left), (GROUND, DECK_Y * 256, 0, 1))

    def test_other_deck_contact_bounces(self):
        for mode, left in ((AIRBORNE, 1), (STALL_DIVE, 1), (STALL, 0)):
            result, flight = self.contact(7000, DECK_Y + 2, mode, left)
            self.assertEqual(result, BOUNCE, (mode, left))
            self.core.Landing_Apply(C.byref(flight), result)
            self.assertEqual((flight.vy, flight.y), (-48, (DECK_Y + 2 - 6) * 256))

    def test_resting_at_deck_height_or_above_is_not_contact(self):
        self.assertEqual(self.contact(7000, DECK_Y)[0], NONE)   # takeoff from the deck
        self.assertEqual(self.contact(7000, DECK_Y - 30)[0], NONE)
        self.assertEqual(self.contact(7000, DECK_Y + 1, mode=GROUND)[0], NONE)

    def test_deck_ends_hull_and_dead_engine_crash(self):
        self.assertEqual(self.contact(DECK_LEFT + 15, DECK_Y + 1)[0], CRASH)
        self.assertEqual(self.contact(DECK_LEFT + 16, DECK_Y + 1)[0], LANDED)
        self.assertEqual(self.contact(DECK_RIGHT - 16, DECK_Y + 1)[0], LANDED)
        self.assertEqual(self.contact(DECK_RIGHT - 15, DECK_Y + 1)[0], CRASH)
        self.assertEqual(self.contact(7000, DECK_Y + 4)[0], LANDED)
        self.assertEqual(self.contact(7000, DECK_Y + 4, sub=1)[0], CRASH)  # more than 4 px in: the hull
        self.assertEqual(self.contact(7000, DECK_Y + 1, failed=1)[0], CRASH)

    def test_the_sea_crashes_when_the_bottom_reaches_it(self):
        self.assertEqual(self.contact(4000, SEA_Y, bottom=0)[0], CRASH)
        self.assertEqual(self.contact(4000, SEA_Y - 1, sub=255, bottom=0)[0], NONE)
        self.assertEqual(self.contact(4000, SEA_Y - 7, bottom=7)[0], CRASH)       # bottom at the sea
        self.assertEqual(self.contact(4000, SEA_Y - 8, sub=255, bottom=7)[0], NONE)
        self.assertEqual(self.contact(DECK_LEFT - 1, DECK_Y + 10, bottom=2)[0], NONE)

    def test_scenery_crashes_below_its_static_height(self):
        # Amiga 0x5710: an island hill 30 px high, level plane (bottom 2).
        self.assertEqual(self.contact(3000, SEA_Y - 32, bottom=2, height=30)[0], NONE)
        self.assertEqual(self.contact(3000, SEA_Y - 31, bottom=2, height=30)[0], CRASH)

    def test_bottom_offsets_follow_the_original_pose_tables(self):
        bottom = self.core.Landing_Bottom
        self.assertEqual([bottom(p, 0) for p in range(10)], [12, 10, 6, 4, 2, 5, 7, 9, 12, 14])
        self.assertEqual([bottom(p, 1) for p in range(10)], [16, 13, 9, 7, 7, 8, 9, 10, 12, 14])
        self.assertEqual(bottom(255, 1), 7)  # resting pose 0 with gear

    def test_a_nose_up_plane_touches_the_deck_earlier(self):
        # Stall pose (pitch 0) with gear: bottom 16 -> contact 9 px above row 1160.
        self.assertEqual(self.contact(7000, DECK_Y - 9, bottom=16)[0], NONE)
        self.assertEqual(self.contact(7000, DECK_Y - 9, sub=1, bottom=16)[0], LANDED)


if __name__ == '__main__':
    unittest.main()
