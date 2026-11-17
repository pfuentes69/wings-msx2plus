"""P0 context routing, bounded input and versioned session data."""
import ctypes as C
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
class Progress(C.Structure):
    _fields_=[('score',C.c_uint32),('kills',C.c_uint16),('rank',C.c_uint8),('lives',C.c_uint8)]
class Mission(C.Structure):
    _fields_=[('map',C.c_uint8),('number',C.c_uint8),('objectives',C.c_uint16)]
class Sortie(C.Structure):
    _fields_=[('weapon',C.c_uint8),('stock',C.c_uint8),('oil',C.c_uint8),('fuel',C.c_uint8)]
class Game(C.Structure):
    _fields_=[('progress',Progress),('mission',Mission),('sortie',Sortie),
              ('phase',C.c_uint8),('cursor',C.c_uint8),('invert',C.c_uint8),('notice',C.c_uint8)]
class Session(C.Structure):
    _fields_=[('game',Game),('x',C.c_uint16),('y',C.c_uint16),
              ('vx',C.c_int16),('vy',C.c_int16),('left',C.c_uint8)]
class Event(C.Structure):
    _fields_=[('state',C.c_uint16),('stamp',C.c_uint8)]
class Queue(C.Structure):
    _fields_=[('events',Event*8),('raw',C.c_uint16),('latest',C.c_uint16),('blocked',C.c_uint16),
              ('head',C.c_uint8),('tail',C.c_uint8),('overflow',C.c_uint8)]
class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();lib=Path(cls.temp.name)/'game.so'
        subprocess.run([shutil.which('cc') or 'cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',
            *[str(ROOT/f'src/core/{name}.c') for name in ('game','controls','session')],'-o',str(lib)],check=True,capture_output=True)
        cls.core=C.CDLL(str(lib))
        declarations={
            'Game_Reset':([C.POINTER(Game)],None),
            'Game_HandleAction':([C.POINTER(Game),C.c_uint16],C.c_uint8),
            'Game_SetLoadout':([C.POINTER(Game),C.c_uint8],None),
            'Controls_Reset':([C.POINTER(Queue)],None),
            'Controls_Store':([C.POINTER(Queue),C.c_uint16,C.c_uint8],None),
            'Controls_Pop':([C.POINTER(Queue),C.POINTER(Event)],C.c_uint8),
            'Controls_Block':([C.POINTER(Queue)],None),
            'Session_Encode':([C.POINTER(Session),C.c_uint8,C.POINTER(C.c_uint8)],C.c_uint8),
            'Session_Decode':([C.POINTER(C.c_uint8),C.c_uint16,C.POINTER(Session)],C.c_uint8)}
        for name,(args,result) in declarations.items():
            fn=getattr(cls.core,name);fn.argtypes=args;fn.restype=result
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def game(self):
        g=Game();self.core.Game_Reset(C.byref(g));return g
    def action(self,g,keys):return self.core.Game_HandleAction(C.byref(g),keys)
    def test_new_game_menu_shells_and_debug_free_controls(self):
        g=self.game();self.assertEqual((g.phase,g.progress.lives,g.sortie.stock),(0,3,30))
        self.action(g,16);self.assertEqual(g.phase,1)
        self.action(g,32);self.assertEqual(g.phase,2)
        flags=self.action(g,64);self.assertEqual((g.phase,flags),(3,3))
        self.action(g,64);self.assertEqual(g.phase,3) # Enter is not gameplay secondary
    def test_hold_service_rearms_without_resetting_progress(self):
        self.core.Game_OpenService.argtypes=[C.POINTER(Game)]
        g=self.game();g.phase=3;g.progress.score=12345;g.progress.rank=3;g.progress.lives=2
        g.mission.objectives=17;g.sortie.stock=4;g.sortie.oil=90;g.sortie.fuel=23
        self.core.Game_OpenService(C.byref(g))
        self.assertEqual((g.phase,g.sortie.stock,g.sortie.oil,g.sortie.fuel),(7,30,128,192))
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,1,15))
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,2,1))
        self.action(g,64);self.assertEqual((g.phase,g.notice),(7,1))   # no torpedo yet
        self.action(g,1);self.action(g,1);self.assertEqual((g.cursor,g.sortie.stock),(0,30))
        flags=self.action(g,64)
        self.assertEqual((g.phase,flags),(3,10))
        self.assertEqual((g.progress.score,g.progress.rank,g.progress.lives,g.mission.objectives),(12345,3,2,17))

    def test_missions_advance_through_the_ranks_and_promote(self):
        # 0x5694: missions per rank 3, 3, 2, 2, 1, 1, 3; maps by rank * 4 +
        # mission (-$7b9f); past the 7th rank the rank stays.
        self.core.Game_AdvanceMission.argtypes=[C.POINTER(Game)];self.core.Game_AdvanceMission.restype=C.c_uint8
        g=self.game()
        self.assertEqual((g.progress.rank,g.mission.number,g.mission.map),(0,1,0))
        seen=[]
        for _ in range(17):
            promoted=self.core.Game_AdvanceMission(C.byref(g))
            seen.append((g.progress.rank,g.mission.number,g.mission.map,promoted))
        self.assertEqual(seen,[(0,2,1,0),(0,3,2,0),(1,1,3,1),(1,2,4,0),(1,3,5,0),(2,1,6,1),(2,2,7,0),
                               (3,1,8,1),(3,2,9,0),(4,1,10,1),(5,1,11,1),(6,1,12,1),(6,2,13,0),(6,3,14,0),
                               (6,1,12,1),(6,2,13,0),(6,3,14,0)])
    def test_back_in_the_hold_the_next_mission_is_briefed(self):
        self.core.Game_NextMission.argtypes=[C.POINTER(Game),C.c_uint8]
        g=self.game();g.phase=3;g.progress.score=4321;g.progress.lives=2;g.sortie.oil=10;g.sortie.fuel=20
        self.core.Game_NextMission(C.byref(g),0)
        self.assertEqual((g.phase,g.progress.lives,g.progress.score,g.sortie.oil,g.sortie.fuel),(1,2,4321,128,192))
        self.core.Game_NextMission(C.byref(g),1);self.assertEqual(g.progress.lives,3)   # the promotion's plane
        g.progress.lives=9;self.core.Game_NextMission(C.byref(g),1);self.assertEqual(g.progress.lives,9)
        # The briefing leads to the loadout and a new sortie, as at game start.
        self.action(g,32);self.assertEqual(g.phase,2)
        flags=self.action(g,64);self.assertEqual((g.phase,flags),(3,3))
    def test_rank_selection_starts_that_ranks_first_mission(self):
        g=self.game()
        for _ in range(4): self.action(g,8)
        self.action(g,16);self.assertEqual((g.progress.rank,g.mission.number,g.mission.map),(4,1,10))
    def test_seven_ranks_plus_separate_load_command(self):
        g=self.game();self.action(g,1);self.assertEqual(g.cursor,7)
        self.action(g,16);self.assertEqual((g.phase,g.progress.rank),(5,0))
        self.action(g,64);self.assertEqual((g.phase,g.cursor),(0,0))
        for rank in range(7):
            g=self.game();g.cursor=rank;self.action(g,16)
            self.assertEqual((g.progress.rank,g.phase),(rank,1))
    def test_stock_model_and_unimplemented_weapons_are_honest(self):
        g=self.game();g.phase=2
        for weapon,count in [(0,30),(1,15),(2,1)]:
            self.core.Game_SetLoadout(C.byref(g),weapon)
            self.assertEqual(g.sortie.stock,count)
            if weapon==2:   # the torpedo comes later; rockets launch the sortie
                self.action(g,64);self.assertEqual((g.phase,g.sortie.stock,g.notice),(2,count,1))
        before=bytes(g);self.core.Game_SetLoadout(C.byref(g),255);self.assertEqual(bytes(g),before)
    def test_pause_only_esc_resumes_and_restart_preserves_setting(self):
        g=self.game();g.phase=3;g.sortie.stock=23;g.progress.score=123
        self.action(g,512);self.assertEqual(g.invert,1)
        self.action(g,128);self.assertEqual(g.phase,4)
        for key in (16,32,64,1,2,4,8):self.action(g,key);self.assertEqual(g.phase,4)
        self.assertEqual((g.sortie.stock,g.progress.score),(23,123))
        self.action(g,128);self.assertEqual(g.phase,3)
        self.action(g,256|32);self.assertEqual((g.phase,g.progress.lives,g.sortie.stock,g.invert),(0,3,30,1))
        self.assertEqual(g.progress.score,0)
    def test_in_game_storage_shells_return_to_game_without_mutation(self):
        for key,phase in ((1024,5),(2048,6)):
            g=self.game();g.phase=3;g.sortie.stock=19;g.progress.score=42
            self.assertEqual(self.action(g,key),2);self.assertEqual(g.phase,phase)
            self.action(g,128);self.assertEqual((g.phase,g.sortie.stock,g.progress.score),(3,19,42))
            self.action(g,key);self.action(g,64);self.assertEqual(g.phase,3)
    def test_quick_press_release_survives_a_redraw_and_alias_overlap(self):
        q=Queue();e=Event();self.core.Controls_Reset(C.byref(q))
        for state,time in [(32,254),(32,255),(32,0),(0,1)]:self.core.Controls_Store(C.byref(q),state,time)
        events=[]
        while self.core.Controls_Pop(C.byref(q),C.byref(e))==1:events.append((e.state,e.stamp))
        self.assertEqual(events,[(32,254),(0,1)])
    def test_context_consumes_held_aliases_until_all_released(self):
        q=Queue();e=Event();self.core.Controls_Reset(C.byref(q))
        self.core.Controls_Store(C.byref(q),32|16,0);self.core.Controls_Block(C.byref(q))
        self.assertEqual(q.latest,0)
        for state in (32,32,0):self.core.Controls_Store(C.byref(q),state,1)
        self.assertEqual(self.core.Controls_Pop(C.byref(q),C.byref(e)),0)
        self.core.Controls_Store(C.byref(q),32,2)
        self.assertEqual(self.core.Controls_Pop(C.byref(q),C.byref(e)),1);self.assertEqual(e.state,32)
    def test_queue_overflow_resync_drops_stale_shots_without_stuck_buttons(self):
        q=Queue();e=Event();self.core.Controls_Reset(C.byref(q))
        for i in range(10):self.core.Controls_Store(C.byref(q),32 if i%2 else 0,i)
        self.assertTrue(q.overflow)
        self.assertEqual(self.core.Controls_Pop(C.byref(q),C.byref(e)),2)
        self.assertEqual(q.latest,0)
        self.core.Controls_Store(C.byref(q),0,11);self.core.Controls_Store(C.byref(q),32,12)
        self.assertEqual(self.core.Controls_Pop(C.byref(q),C.byref(e)),1)
        self.assertEqual(e.state,32)
    def test_session_round_trip_each_loadout_and_carrier_gate(self):
        for weapon,stock in [(0,30),(1,15),(2,1)]:
            s=Session();s.game=self.game();self.core.Game_SetLoadout(C.byref(s.game),weapon)
            s.game.progress.score=0x12345678;s.game.progress.rank=6;s.game.progress.kills=42
            s.game.mission.objectives=0x1234;s.game.invert=1;s.x=7032;s.y=1168;s.vx=-205;s.vy=154;s.left=1
            data=(C.c_uint8*32)();out=Session()
            self.assertEqual(self.core.Session_Encode(C.byref(s),0,data),0)
            self.assertEqual(self.core.Session_Encode(C.byref(s),1,data),1)
            self.assertEqual(self.core.Session_Decode(data,32,C.byref(out)),1)
            self.assertEqual((out.game.sortie.weapon,out.game.sortie.stock),(weapon,stock))
            self.assertEqual((out.game.progress.score,out.game.progress.kills,out.game.mission.objectives),(0x12345678,42,0x1234))
            self.assertEqual((out.x,out.y,out.vx,out.vy,out.left),(7032,1168,-205,154,1))
    def test_corrupt_incompatible_or_invalid_session_is_transactional(self):
        s=Session();s.game=self.game();s.x=7032;s.y=1108
        data=(C.c_uint8*32)();self.assertEqual(self.core.Session_Encode(C.byref(s),1,data),1)
        out=Session();out.x=123;before=bytes(out)
        for index in range(32):
            copy=(C.c_uint8*32)(*data);copy[index]^=1
            self.assertEqual(self.core.Session_Decode(copy,32,C.byref(out)),0)
            self.assertEqual(bytes(out),before)
        self.assertEqual(self.core.Session_Decode(data,31,C.byref(out)),0)
        s.game.sortie.stock=31;self.assertEqual(self.core.Session_Encode(C.byref(s),1,data),0)
        self.assertEqual(bytes(out),before)
