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
class HighScore(C.Structure):
    _fields_=[('score',C.c_uint32),('rank',C.c_uint8),('name',C.c_char*16)]
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
        cls.temp=tempfile.TemporaryDirectory()
        def build(name,*defines):
            lib=Path(cls.temp.name)/name
            subprocess.run([shutil.which('cc') or 'cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',*defines,
                *[str(ROOT/f'src/core/{name}.c') for name in ('game','controls','session')],'-o',str(lib)],check=True,capture_output=True)
            return C.CDLL(str(lib))
        cls.core=build('game.so')
        # The high-score table, set aside (WINGS_HIGH_SCORES): still tested.
        cls.hs=build('game_hs.so','-DWINGS_HIGH_SCORES')
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
        for lib in (cls.core,cls.hs):
            for name,(args,result) in declarations.items():
                fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
            lib.Game_Wait.argtypes=[C.POINTER(Game),C.c_uint8,C.c_uint8];lib.Game_Wait.restype=C.c_uint8
        cls.hs.Game_Type.argtypes=[C.POINTER(Game),C.c_uint8];cls.hs.Game_Type.restype=C.c_uint8
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
        # The panel's order: Rockets, Bombs, Torpedo (the cursor is the weapon:
        # 0 bombs, 1 rockets, 2 torpedo). Down from bombs is the torpedo, up
        # the rockets; it wraps round.
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,2,1))
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,1,15))
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,0,30))
        self.action(g,4);self.assertEqual((g.phase,g.cursor,g.sortie.stock),(7,2,1))
        flags=self.action(g,64)   # the torpedo flies too
        self.assertEqual((g.phase,flags,g.sortie.weapon,g.sortie.stock,g.notice),(3,10,2,1,0))
        self.core.Game_OpenService(C.byref(g))
        self.action(g,1);self.action(g,1);self.assertEqual((g.cursor,g.sortie.stock),(1,15))
        self.action(g,4);self.assertEqual((g.cursor,g.sortie.stock),(0,30))
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
        for _ in range(4): self.action(g,4)
        self.action(g,16);self.assertEqual((g.progress.rank,g.mission.number,g.mission.map),(4,1,10))
    def test_seven_ranks_without_return_from_r_and_r(self):
        # The original's eighth line (Return from R&R) is left out: up from
        # Midshipman wraps to Captain.
        g=self.game();self.action(g,1);self.assertEqual(g.cursor,6)
        self.action(g,16);self.assertEqual((g.phase,g.progress.rank),(1,6))
        for rank in range(7):
            g=self.game();g.cursor=rank;self.action(g,16)
            self.assertEqual((g.progress.rank,g.phase),(rank,1))
    def test_stock_model_and_every_weapon_launches(self):
        for weapon,count in [(0,30),(1,15),(2,1)]:
            g=self.game();g.phase=2
            self.core.Game_SetLoadout(C.byref(g),weapon)
            self.assertEqual(g.sortie.stock,count)
            self.action(g,64);self.assertEqual((g.phase,g.sortie.weapon,g.sortie.stock,g.notice),(3,weapon,count,0))
        before=bytes(g);self.core.Game_SetLoadout(C.byref(g),255);self.assertEqual(bytes(g),before)
    def test_f1_cheat_refills_the_weapon_in_flight_only(self):
        for weapon,full in [(0,30),(1,15),(2,1)]:
            g=self.game();self.core.Game_SetLoadout(C.byref(g),weapon);g.phase=3;g.sortie.stock=0
            g.sortie.oil=50;g.progress.score=77
            self.assertEqual(self.action(g,16384),0)
            self.assertEqual((g.phase,g.sortie.weapon,g.sortie.stock,g.sortie.oil,g.progress.score),(3,weapon,full,50,77))
        for phase in (2,4,7,8):   # loadout, pause, service, game over: nothing
            g=self.game();g.phase=phase;g.sortie.stock=3
            self.assertEqual(self.action(g,16384),0);self.assertEqual((g.phase,g.sortie.stock),(phase,3))
    def test_pause_only_esc_resumes_and_restart_preserves_setting(self):
        g=self.game();g.phase=3;g.sortie.stock=23;g.progress.score=123
        self.action(g,512);self.assertEqual(g.invert,1)
        self.action(g,128);self.assertEqual(g.phase,4)
        for key in (16,32,64,1,2,4,8):self.action(g,key);self.assertEqual(g.phase,4)
        self.assertEqual((g.sortie.stock,g.progress.score),(23,123))
        self.action(g,128);self.assertEqual(g.phase,3)
        # Without the high-score table, Ctrl-R is a new game at rank selection.
        self.action(g,256|32);self.assertEqual((g.phase,g.progress.lives,g.sortie.stock,g.invert),(0,3,30,1))
        self.assertEqual(g.progress.score,0)
    def test_the_end_returns_to_rank_selection_without_the_table(self):
        g=self.game();g.phase=8;g.progress.score=500;g.invert=1
        self.assertEqual(self.core.Game_Wait(C.byref(g),8,1),0)
        self.action(g,64);self.assertEqual(g.phase,8)    # a button only after 30 frames
        for _ in range(3): self.core.Game_Wait(C.byref(g),8,1)
        self.action(g,16);self.assertEqual((g.phase,g.progress.score,g.invert),(0,0,1))
        g=self.game();g.phase=8
        frames=0
        while g.phase==8:
            self.core.Game_Wait(C.byref(g),6,0);frames+=6
        self.assertEqual((g.phase,frames),(0,180))        # by itself after 150 PAL frames (NTSC fields)
    def test_ctrl_r_goes_through_the_high_scores_with_the_table(self):
        hs=self.hs
        g=Game();hs.Game_Reset(C.byref(g));g.phase=3;g.progress.score=123
        hs.Game_ClearScores()
        hs.Game_HandleAction(C.byref(g),256);self.assertEqual((g.phase,g.progress.score),(9,123))
        hs.Game_HandleAction(C.byref(g),64);self.assertEqual(g.phase,10)
        hs.Game_HandleAction(C.byref(g),16);self.assertEqual((g.phase,g.progress.score),(0,0))
        self.assertEqual(hs.Game_HandleAction(C.byref(g),256),0)   # at rank selection Ctrl-R does nothing
    def hsgame(self):
        g=Game();self.hs.Game_Reset(C.byref(g));return g
    def hsaction(self,g,keys):return self.hs.Game_HandleAction(C.byref(g),keys)
    def scores(self):
        table=(HighScore*10).in_dll(self.hs,'g_HighScores')
        return [(e.score,e.rank,bytes(e.name).rstrip(b' ').decode()) for e in table]
    def end_game(self,score,rank,name=b''):
        g=self.hsgame();g.phase=3;g.progress.score=score;g.progress.rank=rank
        self.hsaction(g,256)
        if g.phase==9:
            for key in name: self.hs.Game_Type(C.byref(g),key)
            self.hsaction(g,16)
        self.assertEqual(g.phase,10)
        return g
    def test_high_scores_keep_the_ten_best_ties_below(self):
        self.hs.Game_ClearScores()
        self.assertEqual(self.scores(),[(0,0,'')]*10)
        g=self.end_game(0,0)                   # 0 does not beat an empty row: the table only
        self.end_game(500,1,b'ANNE')
        self.end_game(900,2,b'BOB')
        self.end_game(500,3,b'CARL')            # a tie goes below the older 500
        got=self.scores()
        self.assertEqual(got[:3],[(900,2,'BOB'),(500,1,'ANNE'),(500,3,'CARL')])
        for i in range(10): self.end_game(1000+i,0,b'X%d'%i)
        got=self.scores()
        self.assertEqual([e[0] for e in got],[1009-i for i in range(10)])
        self.end_game(1000,0,b'NO')             # equal to the tenth: does not qualify
        self.assertEqual(self.scores(),got)
    def test_name_entry_types_and_deletes(self):
        self.hs.Game_ClearScores()
        g=self.hsgame();g.phase=3;g.progress.score=10;self.hsaction(g,256);self.assertEqual(g.phase,9)
        typed=[self.hs.Game_Type(C.byref(g),k) for k in b'AB?c 1.']
        self.assertEqual(typed,[1,1,0,0,1,1,1])         # '?' and lower case are not in the font
        self.assertEqual(self.hs.Game_Type(C.byref(g),8),1)
        for k in b'0123456789ABCDEFGH': self.hs.Game_Type(C.byref(g),k)
        length=C.c_uint8.in_dll(self.hs,'g_NameLength').value
        self.assertEqual(length,16)
        self.hsaction(g,4)                                 # down ends the name too
        self.assertEqual(self.scores()[0][2],'AB 10123456789AB')
    def test_the_end_takes_a_button_after_30_frames_and_moves_on_after_150(self):
        self.hs.Game_ClearScores()
        g=self.hsgame();g.phase=8;g.progress.score=0
        self.assertEqual(self.hs.Game_Wait(C.byref(g),8,1),0)
        self.hsaction(g,64);self.assertEqual(g.phase,8)    # too early
        for _ in range(3): self.hs.Game_Wait(C.byref(g),8,1)
        self.hsaction(g,64);self.assertEqual(g.phase,10)   # 32 frames: the table
        frames=0
        while g.phase==10:
            self.hs.Game_Wait(C.byref(g),8,1);frames+=8
        self.assertEqual((g.phase,frames),(0,1800))
        g=self.hsgame();g.phase=8
        frames=0
        while g.phase==8:
            self.hs.Game_Wait(C.byref(g),6,0);frames+=6
        self.assertEqual((g.phase,frames),(10,180))       # NTSC: 150 PAL frames as fields
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
