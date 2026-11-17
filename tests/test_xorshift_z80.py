"""The Z80 xorshift (src/core/xorshift.h) gives the C sequence."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

try:
    import z80
except ImportError:  # optional dev dependency (requirements.txt)
    z80 = None

ROOT = Path(__file__).resolve().parents[1]
STACK, SENTINEL, SEED = 0xF000, 0x3000, 0xD000


def reference(s):
    s ^= (s << 7) & 0xffff
    s ^= s >> 9
    s ^= (s << 8) & 0xffff
    return s


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class XorshiftZ80Tests(unittest.TestCase):
    def test_same_sequence_as_c(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'x.c').write_text('#include "xorshift.h"\nuint16_t Next(uint16_t* seed) { return Xorshift(seed); }\n')
            sdcc = shutil.which('sdcc')
            subprocess.run([sdcc, '-mz80', '-I', str(ROOT / 'src/core'), '-c', 'x.c'], cwd=work, check=True, capture_output=True)
            subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                            'x.rel', '-o', 'x.ihx'], cwd=work, check=True, capture_output=True)
            symbols = dict((n, int(a, 16)) for a, n in
                           re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'x.map').read_text(), re.M))
            m = z80.Z80Machine()
            for line in (work / 'x.ihx').read_text().split():
                count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
                if kind == 0:
                    m.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
            m.set_memory_block(SENTINEL, b'\x76')
            m.set_breakpoint(SENTINEL)
            s, worst = 0x5a3c, 0
            for _ in range(3000):
                m.set_memory_block(SEED, bytes([s & 255, s >> 8]))
                m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
                m.sp, m.pc, m.hl = STACK - 2, symbols['_Next'], SEED
                m.ticks_to_stop = 2000
                while m.pc != SENTINEL:
                    self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
                s = reference(s)
                self.assertEqual((m.de, m.memory[SEED] | m.memory[SEED + 1] << 8), (s, s))
                worst = max(worst, 2000 - m.ticks_to_stop)
            print(f'\nXorshift: {worst} T-states')


if __name__ == '__main__':
    unittest.main()
