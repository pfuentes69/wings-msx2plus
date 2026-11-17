"""Hand-written Z80 rocket move (Rocket_Move in src/core/rocket_move.c)
against its C reference, on an emulated Z80."""
import ctypes
from pathlib import Path
import random
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

try:
    import z80
except ImportError:  # optional dev dependency (requirements.txt)
    z80 = None

ROOT = Path(__file__).resolve().parents[1]
STACK, SENTINEL, ROCKET = 0xF000, 0x3000, 0xD000
# Z80 layout (SDCC packs): x, vx, vy (16.16), ax, ay, y, delay, frame, angle, speed, live.
LAYOUT = '<iiihhhBBbBB'


class Rocket(ctypes.Structure):
    _fields_ = [('x', ctypes.c_int32), ('vx', ctypes.c_int32), ('vy', ctypes.c_int32), ('ax', ctypes.c_int16),
                ('ay', ctypes.c_int16), ('y', ctypes.c_int16), ('delay', ctypes.c_uint8), ('frame', ctypes.c_uint8),
                ('angle', ctypes.c_int8), ('speed', ctypes.c_uint8), ('live', ctypes.c_uint8)]

FIELDS = [name for name, _ in Rocket._fields_]


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class RocketMoveZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        source = ROOT / 'src/core/rocket_move.c'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(source), '-o', str(work / 'move.so')], check=True, capture_output=True)
        cls.native = ctypes.CDLL(str(work / 'move.so'))
        cls.native.Rocket_Move.argtypes = [ctypes.POINTER(Rocket)]
        cls.native.Rocket_Move.restype = ctypes.c_uint8
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', '--opt-code-speed', '-I', str(ROOT / 'src/core'),
                        '-c', str(source), '-o', str(work) + '/'], check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'rocket_move.rel', '-o', 'move.ihx'], cwd=work, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'move.map').read_text(), re.M))
        cls.entry, cls.left = symbols['_Rocket_Move'], symbols['_g_RocketLeft']
        cls.divide = symbols['_Rocket_Divide']
        cls.native.Rocket_Divide.argtypes = [ctypes.POINTER(ctypes.c_int32), ctypes.c_uint16]
        cls.native.Rocket_Divide.restype = ctypes.c_uint16
        cls.machine = z80.Z80Machine()
        for line in (work / 'move.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                cls.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        cls.machine.set_memory_block(SENTINEL, b'\x76')
        cls.machine.set_breakpoint(SENTINEL)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_z80(self, values, left):
        m = self.machine
        m.set_memory_block(ROCKET, struct.pack(LAYOUT, *values))
        m.set_memory_block(self.left, bytes([left]))
        m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
        m.sp, m.pc, m.ix, m.iy, m.hl = STACK - 2, self.entry, 0x1234, 0x5678, ROCKET
        budget = 5000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:
            self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
        self.assertEqual((m.sp, m.ix, m.iy), (STACK, 0x1234, 0x5678))
        return m.a, struct.unpack(LAYOUT, bytes(m.memory[ROCKET:ROCKET + struct.calcsize(LAYOUT)])), budget - m.ticks_to_stop

    def test_divide_matches_c_reference(self):
        rng = random.Random(5)
        m, worst = self.machine, 0
        for _ in range(5000):
            d = rng.choice([1, 2, 255, 256, 65535, rng.randrange(1, 65536), rng.randrange(1, 300)])
            high = rng.choice([0, d - 1, rng.randrange(d)])
            n = (high << 16) | rng.choice([0, 65535, rng.randrange(65536)])
            want = self.native.Rocket_Divide(ctypes.byref(ctypes.c_int32(n - (1 << 32) if n >= 1 << 31 else n)), d)
            self.assertEqual(want, n // d)
            m.set_memory_block(ROCKET, struct.pack('<I', n))
            m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
            m.sp, m.pc, m.ix, m.iy, m.hl, m.de = STACK - 2, self.divide, 0x1234, 0x5678, ROCKET, d
            m.ticks_to_stop = 5000
            while m.pc != SENTINEL:
                self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
            self.assertEqual(m.de, want, (n, d))
            worst = max(worst, 5000 - m.ticks_to_stop)
        print(f'\nRocket_Divide: at most {worst} T-states')

    def test_assembly_matches_c_reference(self):
        rng = random.Random(11)
        worst = 0
        def i32():
            return rng.choice([0, -1, 65535, -65536, 2**31 - 1, -2**31, rng.randrange(-2**31, 2**31),
                               rng.randrange(-40 << 16, 40 << 16)])
        def i16():
            return rng.choice([0, -1, 32767, -32768, rng.randrange(-32768, 32768)])
        for _ in range(5000):
            values = (i32(), i32(), i32(), i16(), i16(), i16(), rng.choice([0, 0, 1, 2, rng.randrange(256)]),
                      rng.randrange(20), rng.randrange(-128, 128), rng.randrange(15), rng.randrange(3))
            left = rng.randrange(2)
            ctypes.c_uint8.in_dll(self.native, 'g_RocketLeft').value = left
            r = Rocket(*values)
            want = self.native.Rocket_Move(ctypes.byref(r))
            got, after, ticks = self.run_z80(values, left)
            self.assertEqual((got, after), (want, tuple(getattr(r, f) for f in FIELDS)), values)
            worst = max(worst, ticks)
        self.assertLess(worst, 1200)
        print(f'\nRocket_Move: at most {worst} T-states')


if __name__ == '__main__':
    unittest.main()
