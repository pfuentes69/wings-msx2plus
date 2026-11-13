"""Manual flight semantics, geometry and time grouping against the release C core."""
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UP, RIGHT, DOWN, LEFT = 1, 2, 4, 8


class Flight(ctypes.Structure):
    _fields_ = [('x', ctypes.c_uint16), ('y', ctypes.c_uint32),
                ('vx', ctypes.c_int16), ('vy', ctypes.c_int16),
                ('frame', ctypes.c_uint8), ('facing_left', ctypes.c_uint8),
                ('mode', ctypes.c_uint8), ('turn_ticks', ctypes.c_uint8),
                ('target_left', ctypes.c_uint8), ('ground_tick', ctypes.c_uint8)]


class World(ctypes.Structure):
    _fields_ = [('flight', Flight), ('x', ctypes.c_uint32), ('camera', ctypes.c_uint16)]


class Aircraft(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint8) for name in
                ('facing_left', 'target_left', 'turning', 'step', 'tick', 'shape')]


class P1FlightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / 'p1.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-shared', '-fPIC', '-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN',
                        '-DWINGS_FLIGHT_MAX_Y=1200u', '-DWINGS_WORLD_WIDTH=7608u',
                        '-DWINGS_WORLD_START=7032u',
                        *[str(ROOT / 'src' / p) for p in ('core/flight.c', 'core/world.c',
                          'core/aircraft.c', 'generated/hellcat_frames.c')],
                        '-o', str(library)], check=True, capture_output=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.World_Reset.argtypes = [ctypes.POINTER(World)]
        cls.core.World_StepSample.argtypes = [ctypes.POINTER(World), ctypes.c_uint8, ctypes.c_uint8]
        cls.core.Aircraft_SyncFlight.argtypes = [ctypes.POINTER(Aircraft), ctypes.POINTER(Flight), ctypes.c_uint16]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def state(self, airborne=False, left=True):
        s = World()
        self.core.World_Reset(ctypes.byref(s))
        if airborne:
            s.x = 4000 * 256
            s.flight.y = 600 * 256
            s.flight.mode = 1
            s.flight.facing_left = s.flight.target_left = left
            s.flight.vx = -154 if left else 154
        return s

    def advance(self, s, controls, ticks, group=1):
        for i in range(ticks):
            self.core.World_StepSample(ctypes.byref(s), controls, i % group == group - 1 or i == ticks - 1)
        return s

    def test_deck_geometry_matches_decoded_hulls_and_level_art(self):
        scene = json.loads((ROOT / 'assets_src/missions/a-scene.json').read_text())
        hulls = [p for p in scene['placed'] if p['name'] in ('fcar', 'mcar', 'rcar')]
        self.assertEqual(min(p['drawing_x'] for p in hulls), 6593)
        self.assertEqual(max(p['drawing_x'] + p['width'] for p in hulls), 7361)
        self.assertTrue(all(p['drawing_y'] - 40 == 129 for p in hulls))
        manifest = json.loads((ROOT / 'assets_msx/hellcat/manifest.json').read_text())
        level = next(f for f in manifest['animation']['frames'] if f['name'] == 'hc41')
        self.assertEqual(145 - (1200 - 1160) + level['dy'] + level['height'], 129)

    def test_automatic_gear_on_deck_departure_and_carrier_approach(self):
        self.core.Flight_GearDown.argtypes = [ctypes.POINTER(Flight), ctypes.c_uint16]
        s = self.state()
        a = Aircraft()
        self.core.Aircraft_SyncFlight(ctypes.byref(a), ctypes.byref(s.flight), s.x >> 8)
        meta = json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        self.assertEqual(a.shape, meta['tail_down_frames'][1])
        while not s.flight.mode:
            self.advance(s, LEFT|UP, 1)
        self.assertEqual(self.core.Flight_GearDown(ctypes.byref(s.flight), s.x >> 8), 0)
        s = self.state(True)
        s.x = 7440*256
        s.flight.y = 1120*256
        s.flight.vy = 20
        self.core.Aircraft_SyncFlight(ctypes.byref(a), ctypes.byref(s.flight), s.x >> 8)
        self.assertEqual(a.shape, meta['gear_frames'][1])
        s.flight.mode=2;s.flight.vy=32
        self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
        self.assertEqual(a.shape,meta['tail_down_frames'][1])
        s.flight.mode=1
        for world, y, vy, left, turning in ((4000,1120,20,1,0), (7440,1000,20,1,0),
                (7440,1120,-20,1,0), (7440,1120,20,0,0), (7440,1120,20,1,10)):
            s.flight.y=y*256; s.flight.vy=vy; s.flight.facing_left=left; s.flight.turn_ticks=turning
            self.assertEqual(self.core.Flight_GearDown(ctypes.byref(s.flight),world),0)

    def test_tail_down_until_takeoff_speed_and_ground_contact(self):
        meta=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        for left in (0,1):
            s=self.state(); s.flight.facing_left=left
            a=Aircraft()
            for speed in (0,100,153,154,205,153,0):
                s.flight.vx=-speed if left else speed
                self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
                self.assertEqual(a.shape,(meta['tail_down_frames'] if speed<154 else meta['gear_frames'])[left])
                frame=meta['frames'][a.shape]
                packed=(ROOT/'assets_msx/hellcat'/frame['file']).read_bytes()
                self.assertTrue(any(packed[-frame['width']//2:]))
        s=self.state();a=Aircraft()
        self.advance(s,LEFT,749)
        self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
        self.assertEqual(a.shape,meta['tail_down_frames'][1])
        self.advance(s,LEFT,21)
        self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
        self.assertEqual(a.shape,meta['gear_frames'][1])
        self.assertEqual(s.flight.mode,0)

    def test_five_second_ground_acceleration_is_progressive_and_pal_ntsc_equal(self):
        ntsc,pal=self.state(),self.state()
        for second in range(1,6):
            # 7.5 NTSC and 6.25 PAL presentations/sec; compare equal game time.
            self.advance(ntsc,LEFT,150,20)
            self.advance(pal,LEFT,150,24)
            self.assertEqual((ntsc.x,bytes(ntsc.flight)),(pal.x,bytes(pal.flight)))
            self.assertEqual(ntsc.flight.vx,-30*second)
            self.assertEqual(ntsc.flight.mode,0)
            self.assertLess(abs(ntsc.flight.vx),154)
        self.advance(ntsc,LEFT,19)
        self.assertEqual(ntsc.flight.vx,-153)
        self.advance(ntsc,LEFT,1)
        self.assertEqual(ntsc.flight.vx,-154)
        self.assertGreater(ntsc.x>>8,6593)
        # Waiting cannot build acceleration credit, and releasing consumes no
        # fractional credit toward the next throttle application.
        resting=self.advance(self.state(),0,1000)
        self.advance(resting,LEFT,4)
        self.assertEqual(resting.flight.vx,0)
        self.advance(resting,0,1)
        self.advance(resting,LEFT,4)
        self.assertEqual(resting.flight.vx,0)

    def test_start_waits_on_deck_facing_left(self):
        s = self.advance(self.state(), 0, 300)
        self.assertEqual((s.x, s.flight.y, s.flight.vx, s.flight.vy,
                          s.flight.facing_left, s.flight.mode), (7032*256, 1160*256, 0, 0, 1, 0))
        self.advance(s, UP | RIGHT, 300)
        self.assertGreater(s.x, 7032*256)
        self.assertEqual(s.flight.facing_left,0)
        self.assertEqual(s.flight.y, 1160*256)

    def test_takeoff_runs_left_and_climbs_near_bow_without_teleport(self):
        s = self.state()
        self.advance(s, UP | LEFT, 100)
        self.assertEqual((s.flight.mode, s.flight.y), (0, 1160*256))
        while s.flight.mode == 0:
            previous = s.x
            self.advance(s, UP | LEFT, 1)
            self.assertLessEqual(previous - s.x, 205)
        self.assertLessEqual(s.x >> 8, 6657)
        self.assertGreater(s.x >> 8, 6593)
        self.advance(s, UP | LEFT, 100)
        self.assertLess(s.flight.y, 1160*256)
        self.assertLess(s.x >> 8, 6593)

    def test_deck_end_stops_and_taxi_both_directions(self):
        s=self.advance(self.state(),LEFT,4000)
        self.assertEqual((s.x,s.flight.vx,s.flight.y,s.flight.mode),(6617*256,0,1160*256,0))
        self.advance(s,RIGHT|UP,4000)
        self.assertEqual((s.x,s.flight.vx,s.flight.y,s.flight.mode,s.flight.facing_left),
                         (7336*256,0,1160*256,0,0))
        self.advance(s,LEFT,4000)
        self.assertEqual((s.x,s.flight.vx,s.flight.mode),(6617*256,0,0))

    def test_ground_turn_brakes_and_plays_five_steps_per_quarter(self):
        meta=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        s=self.advance(self.state(),LEFT,400)
        before=s.x
        self.advance(s,RIGHT,1)
        self.assertLess(s.flight.vx,0)
        self.assertFalse(s.flight.turn_ticks)
        while not s.flight.turn_ticks:self.advance(s,RIGHT,1)
        self.assertEqual(s.flight.vx,0)
        position=s.x
        a=Aircraft();observed=[]
        for tick in range(240):
            self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
            observed.append(a.shape)
            self.advance(s,RIGHT,1)
            self.assertEqual((s.x,s.flight.y,s.flight.mode),(position,1160*256,0))
        self.assertEqual(observed,[f for f in meta['taxi_turn'][:10] for _ in range(24)])
        self.assertEqual((s.flight.facing_left,s.flight.turn_ticks),(0,0))
        self.advance(s,RIGHT,150)
        self.assertGreater(s.x,position)
        self.assertLess(position,before)
        # A full turn back uses the same source poses in reverse order.
        while not s.flight.turn_ticks:self.advance(s,LEFT,1)
        observed=[]
        for tick in range(240):
            self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
            observed.append(a.shape);self.advance(s,LEFT,1)
        self.assertEqual(observed,[f for f in meta['taxi_turn'][10:0:-1] for _ in range(24)])
        self.assertEqual(s.flight.facing_left,1)

    def test_ground_turn_and_bounds_are_pal_ntsc_deterministic(self):
        ntsc,pal=self.state(),self.state()
        for controls in (RIGHT,0,LEFT,RIGHT,LEFT,LEFT|UP):
            self.advance(ntsc,controls,1200,20)
            self.advance(pal,controls,1200,24)
            self.assertEqual(bytes(ntsc),bytes(pal))
            if not ntsc.flight.mode:self.assertTrue(6617<=ntsc.x>>8<=7336)

    def test_all_nine_positions_and_heading_symmetry(self):
        for left in (False, True):
            direction = LEFT if left else RIGHT
            for vertical in (0, UP, DOWN):
                for horizontal in (0, LEFT, RIGHT):
                    with self.subTest(left=left, vertical=vertical, horizontal=horizontal):
                        s = self.advance(self.state(True, left), vertical | horizontal, 250)
                        self.assertEqual(abs(s.flight.vx), 205 if horizontal else
                                         154 if not vertical else 32 if vertical == UP else 154)
                        self.assertEqual(s.flight.vy, (-96 if vertical == UP else 96 if vertical else 0)
                                         if horizontal else (32 if vertical == UP else 48 if vertical else 0))
                        self.assertEqual(s.flight.facing_left, horizontal == LEFT if horizontal else left)

    def test_held_stall_raises_nose_while_sinking_and_release_levels(self):
        meta=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        for left in (False,True):
            s=self.state(True,left);a=Aircraft();before=s.flight.y
            self.advance(s,UP,150)
            self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
            self.assertEqual((s.flight.mode,abs(s.flight.vx),s.flight.vy),(2,32,32))
            self.assertGreater(s.flight.y,before)
            settled_y=s.flight.y
            self.advance(s,UP,150)
            self.assertEqual(s.flight.y-settled_y,32*150)
            self.assertEqual(a.shape,meta['pitch_left' if left else 'pitch_right'][3])
            self.advance(s,0,30)
            self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
            self.assertEqual((s.flight.mode,s.flight.vy),(1,0))
            self.assertEqual(a.shape,meta['pitch_left' if left else 'pitch_right'][4])

    def test_brief_down_latches_dive_until_up_or_horizontal_command(self):
        meta=json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']
        for left in (False,True):
            s=self.state(True,left);a=Aircraft()
            self.advance(s,DOWN,1);self.advance(s,0,150)
            self.core.Aircraft_SyncFlight(ctypes.byref(a),ctypes.byref(s.flight),s.x>>8)
            self.assertEqual((s.flight.mode,abs(s.flight.vx),s.flight.vy),(3,154,48))
            self.assertEqual(a.shape,meta['pitch_left' if left else 'pitch_right'][6])
            self.assertGreater(s.flight.y,600*256)
            settled_y=s.flight.y
            self.advance(s,0,150)
            self.assertEqual(s.flight.y-settled_y,48*150)
            self.advance(s,UP,60);self.assertEqual(s.flight.mode,2)
            self.advance(s,0,30);self.assertEqual((s.flight.mode,s.flight.vy),(1,0))
            self.advance(s,DOWN,1);self.advance(s,LEFT if left else RIGHT,60)
            self.assertEqual((s.flight.mode,s.flight.vy),(1,0))

    def test_turn_cost_compensation_and_animation_follow_simulation(self):
        level, climb = self.state(True), self.state(True)
        a = Aircraft()
        for i in range(110):
            self.advance(level, RIGHT, 1)
            self.advance(climb, RIGHT | UP, 1)
            self.core.Aircraft_SyncFlight(ctypes.byref(a), ctypes.byref(level.flight), level.x >> 8)
            self.assertEqual(a.turning, level.flight.turn_ticks != 0)
            self.assertEqual(a.facing_left, level.flight.facing_left)
            self.assertLess(a.step, 22)
            if i < 109:
                self.assertEqual(level.flight.facing_left, 1)
        self.assertEqual(level.flight.facing_left, 0)
        self.assertGreater(level.flight.y, 600*256)
        self.assertLess(climb.flight.y, 600*256)

    def test_pal_ntsc_and_sampled_presentations_agree(self):
        ntsc, pal = self.state(), self.state()
        for controls in (LEFT, LEFT|UP, LEFT|UP, LEFT|UP, 0, RIGHT, UP, DOWN, RIGHT|UP):
            self.advance(ntsc, controls, 600, 20)
            self.advance(pal, controls, 600, 24)
            self.assertEqual(bytes(ntsc), bytes(pal))

    def test_opposed_axes_are_neutral_and_world_bounds_do_not_wrap(self):
        s, other = self.state(True), self.state(True)
        self.advance(s, 15, 300)
        self.advance(other, 0, 300)
        self.assertEqual(bytes(s), bytes(other))
        self.advance(s, LEFT | DOWN, 10000)
        self.assertEqual((s.x, s.flight.y), (0, 1200*256))
        self.advance(s, RIGHT | UP, 15000)
        self.assertEqual((s.x, s.flight.y), (7607*256, 0))
