"""The Z80 smoke-path box (src/msx/smoke_box.h) against its C, in Python."""
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
STACK, SENTINEL = 0xF000, 0x3000
SOURCE = r'''
#include <stdint.h>
typedef int16_t i16; typedef int8_t i8; typedef uint8_t u8;
signed char g_SmokeBox[400];
i16 s_Left, s_Right, s_Top, s_Limit, s_BoxLeft, s_BoxRight, s_BoxTop, s_BoxBottom, s_BX, s_BY;
i8 s_Heave;
#include "smoke_box.h"
u8 Test(u8 frame) { return Box(frame); }
'''


def s16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SmokeBoxZ80Tests(unittest.TestCase):
    def test_matches_the_c(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'b.c').write_text(SOURCE)
            sdcc = shutil.which('sdcc')
            subprocess.run([sdcc, '-mz80', '-I', str(ROOT / 'src/msx'), '-c', 'b.c'], cwd=work, check=True, capture_output=True)
            subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                            'b.rel', '-o', 'b.ihx'], cwd=work, check=True, capture_output=True)
            sym = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'b.map').read_text(), re.M))
            m = z80.Z80Machine()
            for line in (work / 'b.ihx').read_text().split():
                count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
                if kind == 0:
                    m.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
            m.set_memory_block(SENTINEL, b'\x76')
            m.set_breakpoint(SENTINEL)
            rng = random.Random(3)
            def w(name, v): m.set_memory_block(sym['_' + name], struct.pack('<h', s16(v)))
            def r(name): return struct.unpack('<h', bytes(m.memory[sym['_' + name]:sym['_' + name] + 2]))[0]
            worst = 0
            for _ in range(4000):
                frame = rng.randrange(97)
                box = [rng.randrange(-40, 40), rng.randrange(-40, 40), rng.randrange(0, 40), rng.randrange(0, 30)]
                m.set_memory_block(sym['_g_SmokeBox'] + frame * 4, struct.pack('<bbBB', *box))
                camera = rng.choice([0, 100, 7000, -300, 20000, rng.randrange(-16000, 24000)])
                left, right = camera + 8, camera + 256
                top, limit = rng.choice([0, 4, 20]), rng.choice([159, 161, 172, 142])
                heave = rng.randrange(-8, 8)
                bx = camera + rng.randrange(-60, 320) if rng.random() < 0.9 else rng.randrange(-32768, 32768)
                by = rng.randrange(-60, 230)
                for name, v in (('s_Left', left), ('s_Right', right), ('s_Top', top), ('s_Limit', limit),
                                ('s_BX', bx), ('s_BY', by)):
                    w(name, v)
                m.set_memory_block(sym['_s_Heave'], struct.pack('<b', heave))
                m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
                m.sp, m.pc, m.a = STACK - 2, sym['_Test'], frame
                m.ticks_to_stop = 3000
                while m.pc != SENTINEL:
                    self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
                worst = max(worst, 3000 - m.ticks_to_stop)
                bl = s16(bx + box[0]); br = s16(bl + box[2])
                bt = s16(by - heave + box[1]); bb = s16(bt + box[3])
                bl = max(bl, s16(left)); br = min(br, s16(right)); bt = max(bt, top); bb = min(bb, limit)
                want = (bl, br, bt, bb, int(br > bl and bb > bt))
                got = (r('s_BoxLeft'), r('s_BoxRight'), r('s_BoxTop'), r('s_BoxBottom'), m.a)
                self.assertEqual(got, want, (frame, box, camera, bx, by, heave))
            print(f'\nBox: at most {worst} T-states')


if __name__ == '__main__':
    unittest.main()
