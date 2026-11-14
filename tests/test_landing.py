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
                        '-DWINGS_WORLD_WIDTH=7608u', str(ROOT / 'src/core/landing.c'), '-o', str(lib)],
                       check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.Landing_Contact.restype = C.c_uint8

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def contact(self, x, y, mode=STALL, left=1, failed=0, sub=0):
        flight = Flight(y=y * 256 + sub, vx=-40, vy=48, mode=mode, facing_left=left, target_left=left)
        return self.core.Landing_Contact(C.byref(flight), x, failed), flight

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

    def test_the_sea_crashes_and_open_air_does_not(self):
        self.assertEqual(self.contact(4000, SEA_Y)[0], CRASH)
        self.assertEqual(self.contact(4000, SEA_Y - 1, sub=255)[0], NONE)
        self.assertEqual(self.contact(DECK_LEFT - 1, DECK_Y + 10)[0], NONE)


if __name__ == '__main__':
    unittest.main()
