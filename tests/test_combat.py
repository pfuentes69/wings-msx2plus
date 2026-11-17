"""Cannon flash/strikes and bombs on the deterministic flight clock."""
import ctypes
import math
from pathlib import Path
import re
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
               ('impacts',ctypes.c_uint16),('flash',ctypes.c_uint8),('flash_ticks',ctypes.c_uint8)]

class CombatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        library = Path(cls.directory.name)/'combat.so'
        wrapper=Path(cls.directory.name)/'optimized.c'
        wrapper.write_text('#include "combat.h"\nvoid Combat_OptimizedStep(CombatState* s, SortieState* stock, uint16_t x,uint16_t y,int16_t vx,int16_t vy,uint8_t left,uint8_t controls) { if(Combat_Clock(s,controls) && Combat_Required(s,controls)) Combat_Advance(s,stock,x,y,vx,vy,left,controls); }\n')
        subprocess.run([shutil.which('cc') or 'cc','-std=c99', '-I'+str(ROOT/'src/generated/map_a'),'-Wall','-Wextra','-Werror',
            '-shared','-fPIC','-DWINGS_WORLD_WIDTH=7608u','-I'+str(ROOT/'src/core'),str(wrapper),str(ROOT/'src/core/combat.c'),
            str(ROOT/'src/core/mission.c'),str(ROOT/'src/generated/map_a/mission_surfaces.c'),
            '-o',str(library)],check=True,capture_output=True)
        cls.core = ctypes.CDLL(str(library))
        cls.core.Combat_Reset.argtypes = [ctypes.POINTER(Combat)]
        cls.core.Combat_Reset.restype = None
        cls.core.Combat_Step.argtypes = [ctypes.POINTER(Combat),ctypes.POINTER(Sortie),ctypes.c_uint16,ctypes.c_uint16,
            ctypes.c_int16,ctypes.c_int16,ctypes.c_uint8,ctypes.c_uint8]
        cls.core.Combat_Step.restype = None
        cls.core.Combat_OptimizedStep.argtypes=cls.core.Combat_Step.argtypes
        cls.core.Combat_OptimizedStep.restype=None
        cls.core.Mission_Surface.argtypes=[ctypes.c_uint16]
        cls.core.Mission_Surface.restype=ctypes.c_uint8

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
        self.assertEqual(ctypes.sizeof(Combat),160)
        s=self.state();self.advance(s,100,3);self.core.Combat_Reset(ctypes.byref(s))
        self.assertEqual(bytes(s),bytes(self.state()))
        self.assertEqual((s.sortie.stock,s.sortie.weapon),(27,0))

    def test_cadence_keeps_flash_active_and_clears_after_release(self):
        s=self.state();flashes=[]
        for _ in range(12):
            self.advance(s,6,1);flashes.append(s.flash)
        self.assertEqual(s.shots_fired,4)
        # The renderer alternates fa/fb per presented frame; the core only
        # activates the overlay and must preserve the variant drawn last.
        self.assertEqual(flashes,[1]*12)
        s.flash=2;self.advance(s,6,1);self.assertEqual(s.flash,2)
        self.assertTrue(all(p.kind==0 for p in s.projectile),'level fire never strikes')
        # The last shot (weapon tick 13) stays visible for four ticks: 160 ms.
        self.assertEqual((s.shots_fired,s.flash_ticks),(5,4))
        self.advance(s,6);self.assertEqual((s.flash,s.flash_ticks),(2,3))
        self.advance(s,12);self.assertEqual((s.flash,s.flash_ticks),(2,1))
        self.advance(s,6);self.assertEqual((s.flash,s.flash_ticks),(0,0))

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
        self.advance(s,1200,x=5000,y=0)            # a 1188 px fall takes about 6 s
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

    TRACER=((10,-6),(10,-4),(10,-3),(10,-3),(11,0),(11,3),(10,5),(10,7),(9,8),(5,9))

    def test_tracer_slopes_match_original_fb_art(self):
        import sys;sys.path.insert(0,str(ROOT/'tools'))
        from decode_shapes import decode_record
        measured=[]
        for n in range(1,11):
            raw=next((ROOT/'reference_assets/unpacked_shapes/hellcat').glob(f'*_fb{n:02x}.bin')).read_bytes()
            pixels,meta=decode_record(raw);w=meta['width'];ox,oy=meta['origin_candidate']
            points=[(i%w-ox,i//w-oy,c) for i,c in enumerate(pixels) if c]
            tracer=[q for q in points if q[2] in (2,3,11,15,16,17)]
            root=min(points,key=lambda q:math.hypot(q[0],q[1]))
            tip=max(tracer,key=lambda q:math.hypot(q[0],q[1]))
            measured.append((tip[0]-root[0],tip[1]-root[1]))
        self.assertEqual(tuple(measured),self.TRACER)
        source=(ROOT/'src/core/combat.c').read_text()
        xs=[int(v) for v in re.search(r's_TracerX\[10\]=\{([^}]*)\}',source).group(1).split(',')]
        ys=[int(v) for v in re.search(r's_TracerY\[10\]=\{([^}]*)\}',source).group(1).split(',')]
        self.assertEqual(tuple(zip(xs,ys)),self.TRACER)

    def test_downward_fire_strikes_where_the_tracer_line_meets_the_sea(self):
        for left in (0,1):
            for pitch in range(5,10):
                tx,ty=self.TRACER[pitch]
                s=self.state();s.aim_pitch=pitch
                self.advance(s,6,1,x=4500,y=1160,left=left)
                reach=40*tx//ty;target=4500-reach if left else 4500+reach
                p=s.projectile[0]
                kind=4 if self.core.Mission_Surface(target)==0 else 3
                self.assertEqual((p.x,p.y,p.kind,p.life,s.impacts),(target*4,1200*4,kind,6,1),(left,pitch))
                self.advance(s,36,x=4500,y=1160)
                self.assertEqual(p.kind,0)

    def test_level_or_climbing_fire_and_out_of_range_fire_show_only_the_flash(self):
        for pitch in range(5):
            s=self.state();s.aim_pitch=pitch;self.advance(s,36,1,x=4500,y=1180)
            self.assertGreater(s.shots_fired,0);self.assertTrue(s.flash)
            self.assertEqual((s.impacts,s.projectile[0].kind),(0,0))
        s=self.state();s.aim_pitch=9;self.advance(s,6,1,x=4500,y=1200-161)
        self.assertEqual((s.shots_fired,s.impacts),(1,0))
        s=self.state();s.aim_pitch=9;self.advance(s,6,1,x=4500,y=1200-160)
        self.assertEqual(s.impacts,1)

    def test_carrier_deck_stops_the_line_of_fire(self):
        s=self.state();s.aim_pitch=9
        self.advance(s,6,1,x=7032,y=1140)
        p=s.projectile[0]
        self.assertEqual((p.x,p.y,p.kind),((7032+28*5//9)*4,1168*4,3))

    def test_strikes_never_wrap_world_edges_and_both_slots_bound_the_rate(self):
        for x,left in [(3,1),(7604,0)]:
            s=self.state();s.aim_pitch=5;self.advance(s,6,1,x=x,y=1160,left=left)
            self.assertEqual((s.shots_fired,s.impacts),(1,0))
        s=self.state();self.advance(s,12,1,x=7608)
        self.assertEqual(s.shots_fired,0)
        # Six-tick strikes and three-tick shots: two slots sustain held fire.
        s=self.state();s.aim_pitch=9
        self.advance(s,600,1,x=4500,y=1160)
        self.assertEqual((s.shots_fired,s.impacts),(34,34))
        s=self.state();s.aim_pitch=9
        for p in s.projectile[:2]:p.kind=3;p.life=50
        self.advance(s,6,1,x=4500,y=1160)
        self.assertEqual((s.shots_fired,s.impacts,s.flash),(1,0,1),'busy slots still flash')

    def test_surface_impacts_and_fixed_flash_lifetime(self):
        for x,floor,kind in [(1000,1200,3),(4500,1200,4),(7032,1168,3)]:
            s=self.state();self.advance(s,6,2,x=x,y=floor-8)
            self.advance(s,30,x=x,y=floor-8)
            p=s.projectile[2]
            self.assertEqual((p.kind,p.y,s.impacts),(kind,floor*4,1))
            self.advance(s,60,x=x,y=floor-8)
            self.assertEqual(p.kind,0)

    def original_bomb(self,x,y,vx,vy,ticks):
        """The Amiga update (0x0b58) in 16.16, per 12.5 Hz tick; y is the
        port's (down), vx/vy in pixels per original tick."""
        X,Y,VX,VY=x*65536,y*65536,round(vx*65536),round(vy*65536)
        path=[]
        for _ in range(ticks):
            whole=VX>>16
            q=abs(whole)//10*(1 if whole>=0 else -1)
            VX-=q*65536;X+=VX
            VY+=0x6000;Y+=VY
            path.append((X/65536,Y/65536))
        return path

    def test_bombs_fall_with_the_original_gravity_and_drag(self):
        # 1493 Q8 per 150 Hz step is 14 px per original tick: drag applies.
        # Sampling at 25 Hz trails the original's 12.5 Hz step (velocity
        # first, then position) by 3/32 px per original tick, plus rounding.
        for vx,vy in ((1493,0),(-1493,0),(533,-213)):
            s=self.state();self.advance(s,6,2,x=3000,y=200,vx=vx,vy=vy)
            p=s.projectile[2]
            start=(p.x/4,p.y/4,p.vx/2,p.vy/2)
            model=self.original_bomb(*start,40)
            for tick in range(40):
                self.advance(s,12,x=3000,y=200)
                self.assertEqual(p.kind,2)
                mx,my=model[tick]
                self.assertLess(abs(p.x/4-mx),2,(vx,tick))
                self.assertLess(abs(p.y/4-my),1.5+3/32*(tick+1),(vx,tick))

    def test_bombs_burst_12_px_above_the_sea_and_11_above_the_deck(self):
        for x,burst,floor,kind in ((4500,1188,1200,4),(1000,1188,1200,3),(7032,1156,1168,3)):
            s=self.state();self.advance(s,6,2,x=x,y=burst-40)
            p=s.projectile[2];lowest=0
            while p.kind==2:
                lowest=p.y;self.advance(s,6,x=x,y=burst-40)
            self.assertLess(lowest,burst*4)
            self.assertEqual((p.kind,p.y),(kind,floor*4),x)

    def test_pal_ntsc_grouping_and_pause_are_deterministic(self):
        ntsc,pal=self.state(),self.state()
        for controls in (1,3,1,0,2,0):
            for _ in range(60): self.advance(ntsc,20,controls,x=5000,y=800,vx=154)
            for _ in range(50): self.advance(pal,24,controls,x=5000,y=800,vx=154)
            self.assertEqual(bytes(ntsc),bytes(pal))
