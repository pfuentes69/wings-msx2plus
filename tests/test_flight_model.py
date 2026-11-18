"""The original flight model (Amiga 0xbff4/0xbdfa/0xc4e8/0xab80) as ported in
src/core/flight_model.c, run through the release step function."""
import ctypes as C
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UP, RIGHT, DOWN, LEFT = 1, 2, 4, 8
GROUND, AIRBORNE, ARREST = 0, 1, 2
TICK = 12
DECK_LEFT, DECK_RIGHT, DECK_Y, CARRIER_X = 6593, 7361, 1160, 7032


class Flight(C.Structure):
    _fields_ = [('x', C.c_uint16), ('y', C.c_uint32), ('vx', C.c_int16), ('vy', C.c_int16),
                ('frame', C.c_uint8), ('facing_left', C.c_uint8), ('mode', C.c_uint8),
                ('turn', C.c_uint8), ('turn_clock', C.c_uint8), ('step', C.c_uint8),
                ('landing', C.c_uint8), ('fast_roll', C.c_uint8), ('throttle', C.c_uint8),
                ('xrem', C.c_int8), ('yrem', C.c_int8),
                ('speed', C.c_int16), ('climb', C.c_int16), ('path', C.c_int16),
                ('cancel', C.c_int16), ('boost', C.c_int16)]


class World(C.Structure):
    _fields_ = [('flight', Flight), ('x', C.c_uint32), ('camera', C.c_uint16)]


class Aircraft(C.Structure):
    _fields_ = [(n, C.c_uint8) for n in ('facing_left', 'target_left', 'turning', 'step', 'tick', 'shape')]


class FlightModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        lib = Path(cls.temp.name) / 'flight.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        '-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
                        '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in ('core/flight.c', 'core/flight_model.c', 'core/world.c',
                          'core/aircraft.c', 'generated/hellcat_frames.c')], '-o', str(lib)],
                       check=True, capture_output=True)
        cls.core = C.CDLL(str(lib))
        cls.core.World_Reset.argtypes = [C.POINTER(World)]
        cls.core.World_StepSample.argtypes = [C.POINTER(World), C.c_uint8, C.c_uint8]
        cls.core.Aircraft_SyncFlight.argtypes = [C.POINTER(Aircraft), C.POINTER(Flight), C.c_uint16]
        cls.core.Flight_GearDown.argtypes = [C.POINTER(Flight), C.c_uint16]
        cls.core.Flight_GearDown.restype = C.c_uint8
        cls.core.Aircraft_Wheel.argtypes = [C.POINTER(Flight)]
        cls.core.Aircraft_Wheel.restype = C.c_uint8
        cls.core.Flight_EngineOut.argtypes = [C.POINTER(Flight)]
        cls.meta = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())['animation']
        cls.names = {f['id']: f['name'] for f in cls.meta['frames']}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def deck(self):
        w = World()
        self.core.World_Reset(C.byref(w))
        return w

    def air(self, x=4000, altitude=600, speed=1000, left=True):
        w = self.deck()
        w.x = x * 256
        w.flight.y = (1200 - altitude) * 256
        w.flight.mode, w.flight.facing_left, w.flight.speed, w.flight.boost = AIRBORNE, left, speed, 4
        return w

    def until(self, w, controls, done, limit=400):
        for _ in range(limit):
            if done(w):
                return w
            self.ticks(w, controls)
        self.fail('condition not reached')

    def ticks(self, w, controls, n=1):
        for _ in range(n * TICK):
            self.core.World_StepSample(C.byref(w), controls, 1)
        return w

    def shape(self, w):
        a = Aircraft()
        self.core.Aircraft_SyncFlight(C.byref(a), C.byref(w.flight), w.x >> 8)
        return self.names[a.shape]

    def wheel(self, w):
        return self.core.Aircraft_Wheel(C.byref(w.flight))

    def altitude(self, w):
        return 1200 - w.flight.y / 256

    # On deck (0xc4e8, 0xbdba, 0xc5f4, 0xb92e)

    def test_new_plane_rests_on_the_elevator_facing_left(self):
        w = self.deck()
        self.assertEqual((w.x >> 8, w.flight.y, w.flight.mode, w.flight.facing_left, w.flight.speed),
                         (CARRIER_X, DECK_Y * 256, GROUND, 1, 0))
        self.assertEqual(self.shape(w), 'hcoc')   # tail down, facing left

    def test_logic_runs_once_per_original_tick(self):
        w = self.deck()
        speeds = []
        for _ in range(3 * TICK):
            self.core.World_StepSample(C.byref(w), LEFT, 1)
            speeds.append(w.flight.speed)
        self.assertEqual(speeds, [1] * 12 + [3] * 12 + [6] * 12)

    def test_deck_acceleration_and_takeoff_roll(self):
        w = self.deck()
        speeds = [self.ticks(w, LEFT).flight.speed for _ in range(10)]
        self.assertEqual(speeds, [1, 3, 6, 10, 15, 21, 28, 36, 44, 52])   # boost 1..8 per tick
        x0 = w.x
        self.until(w, LEFT | UP, lambda w: w.flight.mode != GROUND)
        # Rolled off the bow below flying speed (about 780 of 1000).
        self.assertLess(w.x >> 8, DECK_LEFT + 16 + 1)
        self.assertTrue(700 < w.flight.speed < 1000, w.flight.speed)
        self.assertLess(w.x, x0)
        lowest = self.altitude(w)
        for _ in range(100):
            self.ticks(w, LEFT | UP)
            lowest = min(lowest, self.altitude(w))
        self.assertGreater(lowest, 20)            # dips, but clears the sea
        self.assertGreater(self.altitude(w), 60)  # and climbs away
        self.assertEqual(w.flight.speed, 1400)

    def test_rolling_motion_is_whole_pixels_per_tick(self):
        w = self.deck()
        w.flight.speed, w.flight.boost = 500, 8
        x0 = w.x
        self.ticks(w, LEFT)
        self.assertEqual(w.flight.speed, 508)
        self.assertEqual(x0 - w.x, (508 + 50) // 100 * 256)

    def test_fast_roll_lifts_the_tail_unless_up_is_held(self):
        w = self.deck()
        w.flight.speed, w.flight.boost = 700, 8
        self.ticks(w, LEFT)
        # Level pose (hc28 is level facing left) on the level wheel overlay.
        self.assertEqual((w.flight.fast_roll, self.shape(w), self.wheel(w)), (1, 'hc28', 14))
        self.ticks(w, LEFT | UP)
        self.assertEqual((w.flight.fast_roll, self.shape(w), self.wheel(w)), (0, 'hcoc', 255))

    def test_brakes_without_power(self):
        w = self.deck()
        w.flight.speed = 100
        self.ticks(w, 0)
        self.assertEqual(w.flight.speed, 92)
        self.ticks(w, RIGHT)            # pushing back brakes too
        self.assertEqual(w.flight.speed, 84)

    def test_turning_round_on_deck_at_rest(self):
        w = self.deck()
        turns = [self.ticks(w, RIGHT).flight.turn for _ in range(7)]
        self.assertEqual(turns, [1, 2, 3, 4, 5, 6, 5])
        self.assertEqual(w.flight.facing_left, 0)
        self.assertEqual([self.ticks(w, RIGHT).flight.turn for _ in range(5)], [4, 3, 2, 1, 0])
        self.assertEqual((w.flight.speed, self.shape(w)), (0, 'hc21'))

    def test_hook_catches_a_cable_with_up_held(self):
        for cable in range(4):
            w = self.deck()
            hook = CARRIER_X + 70 + 56 * cable
            w.x = (hook - 24 + 10) * 256   # the next tick's 10 px roll puts the hook on the cable
            w.flight.speed, w.flight.boost = 1000, 0
            self.ticks(w, UP)
            self.assertEqual(w.flight.mode, ARREST, cable)
            speeds = []
            for _ in range(20):
                if w.flight.mode != ARREST:
                    break
                speeds.append(self.ticks(w, UP).flight.speed)
            self.assertEqual(speeds[:3], [882, 772, 662])
            self.assertEqual((w.flight.mode, w.flight.speed), (GROUND, 0))

    def test_no_catch_without_up_and_the_plane_rolls_off(self):
        w = self.deck()
        w.x = (CARRIER_X + 260) * 256
        w.flight.speed = 1400
        self.until(w, 0, lambda w: w.flight.mode != GROUND)
        self.assertEqual(w.flight.mode, AIRBORNE)
        self.assertLess(w.x >> 8, DECK_LEFT + 17)

    # In the air (0xbff4 controls, 0xbdfa integration)

    def test_level_flight_speed_steps(self):
        for speed, step in ((1000, 10), (1200, 12), (1400, 14)):
            w = self.air(speed=speed)
            w.flight.boost = 4
            x0, y0 = w.x, w.flight.y
            self.ticks(w, 0)
            # Without power the speed first drops by 4; (speed + 50) / 100 px.
            self.assertEqual(((x0 - w.x) // 256, w.flight.y - y0), (step, 0))

    def test_speed_builds_with_power_and_decays_to_1000(self):
        w = self.air(speed=1000)
        w.flight.boost = 0
        speeds = [self.ticks(w, LEFT).flight.speed for _ in range(4)]
        self.assertEqual(speeds, [1001, 1003, 1006, 1010])
        self.ticks(w, LEFT, 80)
        self.assertEqual((w.flight.speed, w.flight.throttle), (1400, 1))
        self.ticks(w, 0, 200)
        self.assertEqual((w.flight.speed, w.flight.throttle), (1000, 0))

    def test_stall_keeps_airspeed(self):
        for left in (True, False):
            w = self.air(speed=1300, left=left)
            self.ticks(w, UP, 30)
            self.assertEqual(w.flight.speed, 1300)

    def test_climb_and_dive_pass_through_every_angle(self):
        w = self.air(speed=1200)
        poses = [self.ticks(w, LEFT | UP).flight.frame for _ in range(6)]
        self.assertEqual(poses, [3, 3, 2, 2, 1, 1])        # +6..+30 degrees
        self.assertEqual(w.flight.climb, 3000)
        w = self.air(speed=1200)
        poses = [self.ticks(w, LEFT | DOWN).flight.frame for _ in range(11)]
        # One pose on the press (-10 degrees), a 4-tick repeat delay, then 6 a tick.
        self.assertEqual(poses, [5, 5, 5, 5, 6, 7, 7, 8, 8, 9, 9])  # down to -45 degrees
        self.assertEqual(w.flight.climb, -4500)
        self.assertEqual([self.shape(w)], ['hc0a-left'])

    def test_down_alone_dives_fast_and_release_holds_the_dive(self):
        w = self.air()
        self.ticks(w, DOWN, 6)
        self.assertEqual(w.flight.climb, -1000 - 2400)   # the press, the delay, then 12 degrees a tick
        self.ticks(w, 0, 3)
        self.assertEqual(w.flight.climb, -3400)          # a dive is kept

    def test_a_down_tap_noses_down_one_pose(self):
        # Input is read once per presented frame, so a tap lasts 2-4 ticks.
        w = self.air()
        poses = []
        for _ in range(6):
            self.ticks(w, DOWN, 4)
            self.ticks(w, 0, 2)
            poses.append(w.flight.frame)
        self.assertEqual(poses, [5, 6, 7, 8, 9, 9])      # one pose per tap, to -45 degrees
        self.assertEqual(w.flight.climb, -4500)
        w = self.air(left=False)
        self.ticks(w, RIGHT | DOWN, 4)                   # with power, too
        self.assertEqual((w.flight.climb, w.flight.frame), (-1000, 5))
        y = w.flight.y
        self.ticks(w, 0, 12)
        self.assertGreater(w.flight.y, y + 6 * 256)      # the first pose below level descends

    def test_a_released_climb_flattens(self):
        w = self.air()
        w.flight.climb = 1500
        self.assertEqual([self.ticks(w, LEFT).flight.climb for _ in range(3)], [900, 300, 0])

    def test_flight_path_lags_the_climb(self):
        w = self.air(speed=1200)
        self.ticks(w, LEFT | UP)
        self.assertEqual((w.flight.climb, w.flight.path), (600, 150))
        self.ticks(w, LEFT | UP)
        self.assertEqual((w.flight.climb, w.flight.path), (1200, 412))

    def test_stall_flare_facing_left_noses_up_and_sinks(self):
        w = self.air(altitude=300)
        self.ticks(w, UP)
        self.assertEqual((w.flight.climb, w.flight.landing, w.flight.frame), (600, 1, 3))
        a0 = self.altitude(w)
        self.ticks(w, UP, 12)
        self.assertLess(self.altitude(w), a0)             # sinking
        self.assertEqual((w.flight.frame, w.flight.landing), (3, 1))
        self.assertGreater(w.flight.path, -800)
        self.assertLess(w.flight.path, -700)

    def test_up_alone_facing_right_noses_down(self):
        w = self.air(left=False)
        climbs = [self.ticks(w, UP).flight.climb for _ in range(10)]
        self.assertEqual(climbs[:3], [-600, -900, -1050])
        self.assertTrue(-1200 <= climbs[-1] < -1190)
        self.assertEqual((w.flight.landing, w.flight.frame), (0, 6))

    def test_below_flying_speed_the_nose_drops_unless_up_is_held(self):
        w = self.air(speed=800)
        y0 = w.flight.y
        self.ticks(w, 0)
        self.assertEqual(w.flight.climb, -300)
        self.assertEqual((w.flight.y - y0) // 256, 2)     # (1000 - 800) / 100 px
        w = self.air(speed=800)
        self.ticks(w, UP | LEFT)
        self.assertEqual(w.flight.climb, 75)              # +75 facing left below 1000

    def test_ceiling(self):
        w = self.air(altitude=1095, speed=1400)
        w.flight.climb = w.flight.path = 3000
        self.ticks(w, LEFT | UP)
        self.assertEqual(self.altitude(w), 1100)
        self.assertEqual(w.flight.climb, -3000)

    # Turns (0xab80)

    def test_full_turn_takes_52_ticks_and_flips_at_frame_14(self):
        w = self.air(speed=1000)
        frames, facing = [], []
        for _ in range(52):
            self.ticks(w, RIGHT)
            frames.append(w.flight.turn)
            facing.append(w.flight.facing_left)
        self.assertEqual(frames[:4], [0, 1, 1, 2])
        self.assertEqual(frames[27], 14)
        self.assertEqual(facing.index(0), 27)
        self.assertEqual(frames[-1], 0)
        self.assertEqual(w.flight.facing_left, 0)

    def test_turn_shapes_follow_the_original_tables(self):
        w = self.air(speed=1000)
        seen = []
        for _ in range(52):
            self.ticks(w, RIGHT)
            name = self.shape(w)
            if not seen or seen[-1] != name:
                seen.append(name)
        self.assertEqual(seen[:4], ['hc28', 'hc29', 'hc2a', 'hc2b'])
        self.assertIn('hc32', seen)
        self.assertEqual(seen[-3:-1], ['hc23', 'hc22'])
        # Turning drops the nose 1.5 degrees per tick (to -22.5), so the
        # plane comes out of the turn diving.
        self.assertEqual((seen[-1], w.flight.climb), ('hc08', -2250))

    def test_turn_slows_horizontal_motion(self):
        w = self.air(speed=1000)
        w.flight.turn, w.flight.turn_clock = 14, 2
        x0 = w.x
        self.ticks(w, 0)
        self.assertEqual(w.x, x0)    # edge on: turn factor 0

    def test_releasing_late_in_a_turn_mirrors_and_unwinds(self):
        w = self.air(speed=1000)
        w.flight.turn, w.flight.turn_clock = 19, 1
        w.flight.facing_left = 0     # already flipped at 14
        self.ticks(w, 0)
        self.assertEqual(w.flight.turn, 6)    # 20 mirrors to 26 - 20
        self.assertEqual([self.ticks(w, 0).flight.turn for _ in range(6)], [5, 4, 3, 2, 1, 0])

    def test_early_turn_unwinds_when_pushing_forward_again(self):
        w = self.air(speed=1000)
        self.ticks(w, RIGHT, 6)
        self.assertEqual(w.flight.turn, 3)
        self.assertEqual([self.ticks(w, LEFT).flight.turn for _ in range(3)], [2, 1, 0])
        self.assertEqual(w.flight.facing_left, 1)

    def test_turning_drops_the_nose(self):
        w = self.air()
        w.flight.turn, w.flight.turn_clock = 8, 2
        self.ticks(w, 0, 3)
        self.assertEqual(w.flight.climb, -450)

    # Engine failure (original mode 4, 0xafba)

    def test_a_dead_engine_falls_keeping_its_horizontal_step(self):
        w = self.air(speed=1200)
        self.ticks(w, 0)                       # level: 12 px a tick (speed 1196)
        self.core.Flight_EngineOut(C.byref(w.flight))
        self.assertEqual((w.flight.mode, w.flight.speed, w.flight.path), (3, 1200, 0))
        steps, xs = [], []
        for _ in range(14):
            y0, x0 = w.flight.y, w.x
            self.ticks(w, LEFT | UP)           # no control
            steps.append((w.flight.y - y0) // 256)
            xs.append((x0 - w.x) // 256)
        self.assertEqual(steps[:11], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 10])
        self.assertEqual(set(xs), {12})
        self.assertEqual((w.flight.climb, w.flight.frame), (-3100, 8))   # nose down, pose 9

    def test_a_falling_plane_finishes_or_unwinds_its_turn(self):
        w = self.air(speed=1000)
        w.flight.turn = 16
        self.core.Flight_EngineOut(C.byref(w.flight))
        self.assertEqual([self.ticks(w, 0).flight.turn for _ in range(6)], [18, 20, 22, 24, 0, 0])
        w = self.air(speed=1000)
        w.flight.turn = 5
        self.core.Flight_EngineOut(C.byref(w.flight))
        self.assertEqual([self.ticks(w, 0).flight.turn for _ in range(3)], [3, 1, 0])

    def test_a_dead_engine_has_no_gear_or_wheels(self):
        w = self.air(x=7300, altitude=100)
        self.core.Flight_EngineOut(C.byref(w.flight))
        self.ticks(w, 0)
        self.assertEqual((self.core.Flight_GearDown(C.byref(w.flight), 7300), self.wheel(w)), (0, 255))

    # Open sea beyond the map (the original never limits x)

    def test_the_plane_flies_on_past_both_map_ends(self):
        w = self.air(x=10, altitude=600, speed=1000)
        self.ticks(w, 0, 3)
        self.assertEqual(((w.x >> 8) & 0xFFFF) - 65536, 10 - 30)  # x is a signed 16-bit ring
        self.assertEqual(w.camera, (((w.x >> 8) & 0xFFFF) - 128) & 0xFFFF)  # centred, not clamped
        w = self.air(x=7600, altitude=600, speed=1000, left=False)
        self.ticks(w, 0, 3)
        self.assertEqual(w.x >> 8, 7630)
        self.assertEqual(w.camera, 7630 - 128)

    def test_open_sea_ends_16000_px_out(self):
        w = self.air(x=7608 + 15995, altitude=600, speed=1000, left=False)
        self.ticks(w, 0, 3)
        self.assertEqual(w.x >> 8, 7608 + 16000)
        w = self.air(x=(65536 - 15995) & 0xFFFF, altitude=600, speed=1000)
        self.ticks(w, 0, 3)
        self.assertEqual(w.x >> 8, 65536 - 16000)

    # Gear (0xb45a)

    def test_gear_down_near_the_carrier_in_either_direction(self):
        w = self.air()
        for world, left, gear in ((CARRIER_X + 1279, 1, 1), (CARRIER_X + 1279, 0, 1),
                                  (CARRIER_X - 1279, 0, 1), (CARRIER_X + 1280, 1, 0), (4000, 1, 0)):
            w.flight.facing_left = left
            self.assertEqual(self.core.Flight_GearDown(C.byref(w.flight), world), gear, (world, left))
        w = self.deck()
        self.assertEqual(self.core.Flight_GearDown(C.byref(w.flight), 0), 1)

    def test_wheel_overlay_follows_the_pose(self):
        # 0x0550: wheel sprite (left ? 10 : 0) + pitch, on every flying pose,
        # whatever the gear state (the renderer slides it up when retracted).
        w = self.air(x=7300, altitude=60)
        self.ticks(w, 0)
        self.assertEqual((self.shape(w), self.wheel(w)), ('hc28', 14))
        self.ticks(w, UP)
        self.assertEqual((self.shape(w), self.wheel(w)), ('hc04-left', 13))   # the flare
        w = self.air(x=4000, altitude=600, left=False)
        self.ticks(w, RIGHT | DOWN, 11)
        self.assertEqual((self.shape(w), self.wheel(w)), ('hc0a', 9))
        w.flight.turn = 5
        self.assertEqual(self.wheel(w), 255)                                  # none while turning
        w = self.deck()
        self.assertEqual(self.wheel(w), 255)                                  # tail-down pose has its own
        w.flight.mode = ARREST
        self.assertEqual((self.shape(w), self.wheel(w)), ('hc28', 14))

    def test_wheel_pieces_rebuild_the_original_sprites(self):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        from decode_shapes import decode_record
        meta, folder = self.meta, ROOT / 'assets_msx/hellcat'
        for sprite in range(20):
            raw = next((ROOT / 'reference_assets/unpacked_shapes/hellcat').glob(f'*_wh{sprite + 1:02x}.bin')).read_bytes()
            indices, m = decode_record(raw)
            ox, oy = m['origin_candidate']
            original = {(i % m['width'] - ox, i // m['width'] - oy) for i, v in enumerate(indices) if v}
            drawn = set()
            for r in meta['wheels'][meta['wheel_first'][sprite]:meta['wheel_first'][sprite + 1]]:
                bank = r['data_offset'] // 8192
                data = (folder / f'mission_bank_{(8, 9, 10, 14, 4, 5, 6)[bank]}.bin').read_bytes()
                packed = data[r['data_offset'] % 8192:r['data_offset'] % 8192 + r['bytes']]
                for y in range(r['height']):
                    for x in range(r['width']):
                        b = packed[y * (r['width'] // 2) + x // 2]
                        if (b & 15 if x % 2 else b >> 4):
                            drawn.add((r['dx'] - 25 + x, r['dy'] - 16 + y))
            # Every drawn pixel is an original wheel pixel; only source
            # colour 1 (mapped to transparent) may be missing.
            self.assertLessEqual(drawn, original, sprite)
            self.assertGreaterEqual(len(drawn), len(original) - 2, sprite)


if __name__ == '__main__':
    unittest.main()
