"""Elevator timing, boarding rules and original platform conversion."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_p1_flight import Flight

ROOT=Path(__file__).resolve().parents[1]

class Carrier(C.Structure):
    _fields_=[('stage',C.c_uint8),('depth',C.c_uint8),('tick',C.c_uint8)]

class CarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();lib=Path(cls.temp.name)/'carrier.so'
        subprocess.run([shutil.which('cc') or 'cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',
            '-DWINGS_P1_FLIGHT','-DWINGS_FLIGHT_MAX_Y=1200u',
            str(ROOT/'src/core/carrier.c'),str(ROOT/'src/core/flight.c'),'-o',str(lib)],check=True,capture_output=True)
        cls.core=C.CDLL(str(lib))
        cls.core.Carrier_Reset.argtypes=[C.POINTER(Carrier)]
        cls.core.Carrier_Raise.argtypes=[C.POINTER(Carrier)]
        cls.core.Carrier_Step.argtypes=[C.POINTER(Carrier)]
        cls.core.Carrier_Request.argtypes=[C.POINTER(Carrier),C.POINTER(Flight),C.c_uint16]
        cls.core.Flight_Reset.argtypes=[C.POINTER(Flight)]
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def state(self):
        s=Carrier();f=Flight();self.core.Carrier_Reset(C.byref(s));self.core.Flight_Reset(C.byref(f));return s,f
    def steps(self,s,ticks):
        return [self.core.Carrier_Step(C.byref(s)) for _ in range(ticks)]
    def test_initial_rise_is_pixelwise_and_takes_576_ticks(self):
        s,f=self.state();self.assertEqual((s.stage,s.depth,f.facing_left),(0,32,1))
        for depth in range(31,-1,-1):
            self.steps(s,17);self.assertEqual(s.depth,depth+1)
            changed=self.steps(s,1)[0]
            self.assertEqual(s.depth,depth);self.assertEqual(bool(changed),depth==0)
        self.assertEqual(s.stage,1)
        self.steps(s,1000);self.assertEqual((s.stage,s.depth),(1,0))
    def test_service_cycles_preserve_heading_and_gate_boarding(self):
        for left in (0,1):
            s,f=self.state();f.facing_left=left;self.steps(s,576)
            for _ in range(2):
                before=bytes(s)
                for x,mode,vx,turn in ((7000,0,0,0),(7032,1,0,0),(7032,0,1,0),(7032,0,0,10)):
                    f.mode=mode;f.vx=vx;f.turn_ticks=turn
                    self.assertFalse(self.core.Carrier_Request(C.byref(s),C.byref(f),x));self.assertEqual(bytes(s),before)
                f.mode=f.vx=f.turn_ticks=0
                self.assertTrue(self.core.Carrier_Request(C.byref(s),C.byref(f),7032))
                self.assertFalse(self.core.Carrier_Request(C.byref(s),C.byref(f),7032))
                self.steps(s,575);self.assertEqual((s.stage,s.depth),(2,31))
                self.steps(s,1);self.assertEqual((s.stage,s.depth),(3,32))
                self.core.Carrier_Raise(C.byref(s));self.steps(s,576)
                self.assertEqual((s.stage,s.depth,f.facing_left),(1,0,left))
    def test_pal_ntsc_grouping_does_not_change_lift_time(self):
        a,_=self.state();b,_=self.state()
        self.steps(a,150);self.steps(a,426)
        self.steps(b,18*32)
        self.assertEqual(bytes(a),bytes(b))
    def test_original_platform_and_reproducible_cache_artifacts(self):
        import sys
        sys.path.insert(0,str(ROOT/'tools'))
        from convert_elevator import artifacts
        from decode_shapes import decode_record
        from unpack_shapes import read_ppkc,unpack_rpck
        for path,data in artifacts().items():self.assertEqual(path.read_bytes(),data,str(path))
        records={n:r for n,_,r in read_ppkc(unpack_rpck((ROOT/'reference_assets/original_files/Wings_of_Fury/shapes/world.shp').read_bytes()))}
        raw=records['elev'];pixels,meta=decode_record(raw,plane_constants=True)
        self.assertEqual((ROOT/'assets_src/ship/elevator.indices').read_bytes(),pixels)
        manifest=json.loads((ROOT/'assets_msx/elevator/manifest.json').read_text())
        self.assertEqual(manifest['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(meta['origin_candidate'],[28,-1])
        self.assertEqual(len((ROOT/'assets_msx/elevator/bank_15.bin').read_bytes()),1728)
