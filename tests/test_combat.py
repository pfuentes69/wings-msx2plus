"""Bounded prototype weapons on the deterministic flight clock."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Projectile(ctypes.Structure):
    _fields_ = [('x',ctypes.c_uint16),('y',ctypes.c_uint16),('vx',ctypes.c_int8),
               ('vy',ctypes.c_int8),('life',ctypes.c_uint8),('kind',ctypes.c_uint8)]

class Sortie(ctypes.Structure):
    _fields_=[('weapon',ctypes.c_uint8),('stock',ctypes.c_uint8),('oil',ctypes.c_uint8),('fuel',ctypes.c_uint8)]

class Combat(ctypes.Structure):
    _fields_ = [('projectile',Projectile*18),('phase',ctypes.c_uint8),('cooldown',ctypes.c_uint8),
               ('secondary_cooldown',ctypes.c_uint8),('secondary_pending',ctypes.c_uint8),
               ('primary_pending',ctypes.c_uint8),('secondary_phase',ctypes.c_uint8),('count',ctypes.c_uint8),('aim_pitch',ctypes.c_uint8),
               ('shots_fired',ctypes.c_uint16),('secondary_fired',ctypes.c_uint16),
               ('impacts',ctypes.c_uint16)]

class CombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name)/'combat.so'
        wrapper=Path(cls.directory.name)/'optimized.c'
        wrapper.write_text('#include "combat.h"\nvoid Combat_OptimizedStep(CombatState* s, SortieState* stock, uint16_t x,uint16_t y,int16_t vx,int16_t vy,uint8_t left,uint8_t controls) { if(Combat_Clock(s,controls) && Combat_Required(s,controls)) Combat_Advance(s,stock,x,y,vx,vy,left,controls); }\n')
        subprocess.run([shutil.which('cc') or 'cc','-std=c99','-Wall','-Wextra','-Werror',
            '-shared','-fPIC','-DWINGS_WORLD_WIDTH=7608u','-I'+str(ROOT/'src/core'),str(wrapper),str(ROOT/'src/core/combat.c'),
            str(ROOT/'src/core/mission.c'),str(ROOT/'src/generated/mission_surfaces.c'),
            '-o',str(library)],check=True,capture_output=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.Combat_Reset.argtypes = [ctypes.POINTER(Combat)]
        cls.core.Combat_Reset.restype = None
        cls.core.Combat_Step.argtypes = [ctypes.POINTER(Combat),ctypes.POINTER(Sortie),ctypes.c_uint16,ctypes.c_uint16,
            ctypes.c_int16,ctypes.c_int16,ctypes.c_uint8,ctypes.c_uint8]
        cls.core.Combat_Step.restype = None
        cls.core.Combat_OptimizedStep.argtypes=cls.core.Combat_Step.argtypes
        cls.core.Combat_OptimizedStep.restype=None

    @classmethod
    def tearDownClass(cls): cls.directory.cleanup()

    def state(self):
        s=Combat();s.sortie=Sortie(0,30,255,255);self.core.Combat_Reset(ctypes.byref(s));return s

    def advance(self,s,n,controls=0,x=7032,y=1108,vx=0,vy=0,left=0):
        for _ in range(n): self.core.Combat_Step(ctypes.byref(s),ctypes.byref(s.sortie),x,y,vx,vy,left,controls)

    def test_skipping_empty_updates_preserves_every_state_and_inventory_change(self):
        for x,y,left in ((7032,1160,1),(5000,800,0),(0,800,1),(7607,800,0)):
            reference,optimized=self.state(),self.state()
            for count,controls in ((100,0),(500,1),(300,0),(1,2),(5,0),(600,2),(600,0),(300,3)):
                for tick in range(count):
                    if tick==10:
                        reference.primary_pending=optimized.primary_pending=1
                    for fn,state in ((self.core.Combat_Step,reference),(self.core.Combat_OptimizedStep,optimized)):
                        fn(ctypes.byref(state),ctypes.byref(state.sortie),x,y,-154 if left else 154,0,left,controls)
                    self.assertEqual(bytes(reference),bytes(optimized))
                    self.assertEqual(bytes(reference.sortie),bytes(optimized.sortie))

    def test_reset_and_capture_layout(self):
        self.assertEqual(ctypes.sizeof(Combat),158)
        s=self.state();self.advance(s,100,3);self.core.Combat_Reset(ctypes.byref(s))
        self.assertEqual(bytes(s),bytes(self.state()))
        self.assertEqual((s.sortie.stock,s.sortie.weapon),(27,0))

    def test_cadence_pool_bounds_and_no_charge_for_full_pool(self):
        s=self.state();self.advance(s,72,1)
        self.assertEqual((s.shots_fired,s.sortie.stock),(2,30))
        self.assertTrue(all(p.kind==1 for p in s.projectile[:2]))
        self.assertEqual(s.projectile[2].kind,0)
        self.advance(s,6,1)
        self.assertEqual((s.shots_fired,s.sortie.stock),(3,30))

    def test_guns_have_no_invented_cap_and_do_not_consume_secondary(self):
        s=self.state();self.advance(s,10000,1)
        self.assertGreater(s.shots_fired,30)
        self.assertEqual(s.sortie.stock,30)
        count=s.shots_fired;self.advance(s,500)
        self.assertEqual(s.shots_fired,count)
        self.assertTrue(all(p.kind==0 for p in s.projectile))

    def test_empty_or_unimplemented_secondary_never_consumes_or_queues(self):
        for weapon,stock in [(0,0),(1,15),(2,1)]:
            s=self.state();s.sortie.weapon=weapon;s.sortie.stock=stock
            self.advance(s,100,2)
            self.assertEqual((s.sortie.stock,s.secondary_fired),(stock,0))
            self.assertEqual(s.projectile[2].kind,0)
        s=self.state();s.primary_pending=1;self.advance(s,6)
        self.assertEqual(s.shots_fired,1)
        self.advance(s,100);self.assertEqual(s.shots_fired,1)

    def test_bombs_repeat_four_per_second_and_stop_on_release(self):
        s=self.state();events=[]
        for tick in range(600):
            before=s.secondary_fired
            self.advance(s,1,2,x=5000,y=0,vx=154)
            if s.secondary_fired!=before:events.append(tick)
        self.assertEqual(len(events),16)
        self.assertEqual([events[i+1]-events[i] for i in range(8)],[36,36,36,42]*2)
        self.assertEqual(s.sortie.stock,14)
        self.assertGreater(sum(p.kind==2 for p in s.projectile),10)
        self.advance(s,600,x=5000,y=0)
        self.assertEqual(s.secondary_fired,16)
        self.assertTrue(all(p.kind==0 for p in s.projectile))

    def test_short_press_rate_limit_full_pool_and_empty_inventory(self):
        s=self.state();self.advance(s,1,2);self.advance(s,5)
        self.assertEqual((s.secondary_fired,s.sortie.stock),(1,29))
        self.advance(s,1,2);self.advance(s,5)
        self.assertEqual(s.secondary_fired,1)
        # A denied press is not deferred after release.
        self.advance(s,100);self.assertEqual(s.secondary_fired,1)
        s.count=18
        for p in s.projectile[2:]:p.kind=2;p.life=100;p.y=0
        self.advance(s,6,2,x=5000,y=0)
        self.assertEqual((s.secondary_fired,s.sortie.stock),(1,29))
        s=self.state();s.sortie.stock=2;self.advance(s,600,2,x=5000,y=0)
        self.assertEqual((s.secondary_fired,s.sortie.stock),(2,0))

    def test_inherited_velocity_and_both_firing_directions(self):
        for left,vx,expected in [(0,205,67),(1,-205,-67)]:
            s=self.state();self.advance(s,6,1,x=5000,vx=vx,vy=-154,left=left)
            p=s.projectile[0]
            self.assertEqual(p.x,(5000+(-24 if left else 24))*4)
            self.assertEqual((p.vx,p.vy),(expected,-14))

    def test_all_pitch_vectors_and_muzzle_positions_in_both_headings(self):
        xs=(12,24,34,46,48,46,42,34,24,12)
        ys=(-46,-42,-34,-12,0,12,24,34,42,46)
        for left in (0,1):
            for pitch,(ax,ay) in enumerate(zip(xs,ys)):
                s=self.state();s.aim_pitch=pitch
                ax=-ax if left else ax
                self.advance(s,6,1,x=5000,y=800,left=left)
                p=s.projectile[0]
                self.assertEqual((p.x,p.y),((5000+ax//2)*4,(798+ay//2)*4))
                self.assertEqual((p.vx,p.vy),(ax,ay))
                x,y=p.x,p.y;self.advance(s,6,x=5000,y=800)
                self.assertEqual((p.x-x,p.y-y),(ax,ay))

        s=self.state();s.aim_pitch=0
        self.advance(s,6,1,x=5000,y=0)
        self.assertEqual(s.projectile[0].y,0)
        self.advance(s,6,x=5000,y=0)
        self.assertEqual(s.projectile[0].kind,0)

    def test_stall_shots_rise_despite_sinking_and_dive_shots_descend(self):
        for left in (0,1):
            for pitch,vx,vy,shot_vy in ((3,32,32,-9),(6,154,48,28)):
                s=self.state();s.aim_pitch=pitch
                self.advance(s,6,1,x=5000,y=800,vx=-vx if left else vx,vy=vy,left=left)
                self.assertEqual(s.projectile[0].vy,shot_vy)
                self.assertEqual(s.projectile[0].vx<0,bool(left))

    def test_world_boundaries_do_not_wrap_or_consume_outside_shots(self):
        for x,left in [(0,1),(7607,0)]:
            s=self.state();self.advance(s,12,1,x=x,left=left)
            self.assertEqual((s.sortie.stock,s.shots_fired),(30,0))
        for x,vx in [(1,-24),(7607*4,24)]:
            s=self.state();p=s.projectile[0]
            p.x=x;p.y=1000*4;p.vx=vx;p.life=20;p.kind=1
            self.advance(s,6)
            self.assertEqual(p.kind,0)

    def test_surface_impacts_and_fixed_flash_lifetime(self):
        for x,floor,kind in [(1000,1200,3),(4500,1200,4),(7032,1168,3)]:
            s=self.state();self.advance(s,6,2,x=x,y=floor-8)
            self.advance(s,30,x=x,y=floor-8)
            p=s.projectile[2]
            self.assertEqual((p.kind,p.y,s.impacts),(kind,floor*4,1))
            self.advance(s,60,x=x,y=floor-8)
            self.assertEqual(p.kind,0)

    def test_pal_ntsc_grouping_and_pause_are_deterministic(self):
        ntsc,pal=self.state(),self.state()
        for controls in (1,3,1,0,2,0):
            for _ in range(60): self.advance(ntsc,20,controls,x=5000,y=800,vx=154)
            for _ in range(50): self.advance(pal,24,controls,x=5000,y=800,vx=154)
            self.assertEqual(bytes(ntsc),bytes(pal))
