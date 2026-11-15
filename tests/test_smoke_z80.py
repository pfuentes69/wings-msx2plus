"""Hand-written Z80 puff advance (Smoke_Advance in src/core/smoke.c) against
its C reference, on an emulated Z80."""
import ctypes
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import unittest

try:
    import z80
except ImportError:  # optional dev dependency (requirements.txt)
    z80 = None

from test_smoke import Puff

ROOT = Path(__file__).resolve().parents[1]
DEFINES = ['-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
           '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u']
COUNT, STACK, SENTINEL = 8, 0xF000, 0x3000


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SmokeAdvanceZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        *DEFINES, str(ROOT / 'src/core/smoke.c'), '-o', str(work / 'smoke.so')],
                       check=True, capture_output=True)
        cls.native = ctypes.CDLL(str(work / 'smoke.so'))
        cls.native_puffs = (Puff * COUNT).in_dll(cls.native, 'g_Smoke')
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', '--opt-code-speed', *DEFINES, '-I', str(ROOT / 'src/core'),
                        '-c', str(ROOT / 'src/core/smoke.c'), '-o', str(work) + '/'], check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'smoke.rel', '-o', 'smoke.ihx'], cwd=work, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'smoke.map').read_text(), re.M))
        cls.entry, cls.pool = symbols['_Smoke_Advance'], symbols['_g_Smoke']
        cls.machine = z80.Z80Machine()
        for line in (work / 'smoke.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                cls.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        cls.machine.set_memory_block(SENTINEL, b'\x76')
        cls.machine.set_breakpoint(SENTINEL)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_z80(self):
        m = self.machine
        m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
        m.sp, m.pc, m.ix, m.iy = STACK - 2, self.entry, 0x1234, 0x5678
        budget = 20000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:
            self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
        self.assertEqual((m.sp, m.ix, m.iy), (STACK, 0x1234, 0x5678))
        return budget - m.ticks_to_stop

    def test_assembly_matches_c_reference(self):
        rng = random.Random(7)
        worst = 0
        for trial in range(3000):
            pool = bytearray()
            for i in range(COUNT):
                stage = rng.choice([0, rng.randrange(1, 7)])
                pool += bytes(Puff(x=rng.choice([0, 1, 65535, rng.randrange(65536)]),
                                   y=rng.choice([0, 1, 65535, rng.randrange(65536)]),
                                   xf=rng.randrange(256), yf=rng.randrange(256), vx=rng.randrange(256),
                                   vy=rng.randrange(256), stage=stage, life=rng.randrange(7)))
            ctypes.memmove(self.native_puffs, bytes(pool), len(pool))
            self.machine.set_memory_block(self.pool, bytes(pool))
            for _ in range(rng.choice([1, 5, 40])):
                self.native.Smoke_Advance()
                worst = max(worst, self.run_z80())
                self.assertEqual(bytes(self.machine.memory[self.pool:self.pool + len(pool)]),
                                 bytes(self.native_puffs), trial)
        print(f'\nZ80 smoke advance: at most {worst} T-states for {COUNT} puffs')


if __name__ == '__main__':
    unittest.main()
