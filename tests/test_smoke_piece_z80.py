"""The Z80 smoke-path piece copy (src/msx/smoke_piece.h, Piece) against the
C it replaced, in Python: the VDP command fields and the ring copy's
arguments (Vdp_RingCopy is a stub that records them)."""
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
typedef int16_t i16; typedef uint16_t u16; typedef uint8_t u8;
#define VDP_CMD_LMMM 0x90
#define VDP_OP_TIMP 0x08
typedef struct AircraftShape {
    const unsigned char* data; signed char dx, dy; unsigned char width, height;
    unsigned char atlas_x; unsigned short atlas_y;
} AircraftShape;
typedef struct { u16 SX, SY, DX, DY, NX, NY; u8 CLR, ARG, CMD; } VDP_Command;
VDP_Command g_VDP_Command;
u8 g_Ring; u16 g_Width; u8 g_Calls;
void Vdp_RingCopy(u8 ring, u16 width) { g_Ring = ring; g_Width = width; ++g_Calls; }
i16 s_Left, s_Right, s_Top, s_Limit, s_X, s_Row, s_PL, s_PT, s_PR, s_PB;
u8 s_Page;
AircraftShape g_Piece;
#include "smoke_piece.h"
void Test(void) { Piece(&g_Piece); }
'''


def s16(v):
    v &= 0xffff
    return v - 0x10000 if v & 0x8000 else v


def model(piece, x, row, page, left, right, top, limit):
    dx, dy, width, height, ax, ay = piece
    pl = s16(x + dx); pr = s16(pl + width); pt = s16(row + dy); pb = s16(pt + height)
    sx, sy = ax, ay
    if pl < left: sx = (sx + left - pl) & 0xffff; pl = left
    if pr > right: pr = right
    if pt < top: sy = (sy + top - pt) & 0xffff; pt = top
    if pb > limit: pb = limit
    if pr <= pl or pb <= pt:
        return None, sx, sy
    return ((page << 8) + pt) & 0xffff, (pb - pt) & 0xffff, pl & 255, (pr - pl) & 0xffff, sx, sy


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SmokePieceZ80Tests(unittest.TestCase):
    def test_matches_the_c(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'p.c').write_text(SOURCE)
            sdcc = shutil.which('sdcc')
            subprocess.run([sdcc, '-mz80', '--opt-code-speed', '-I', str(ROOT / 'src/msx'), '-c', 'p.c'],
                           cwd=work, check=True, capture_output=True)
            subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                            'p.rel', '-o', 'p.ihx'], cwd=work, check=True, capture_output=True)
            sym = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'p.map').read_text(), re.M))
            m = z80.Z80Machine()
            for line in (work / 'p.ihx').read_text().split():
                count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
                if kind == 0:
                    m.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
            m.set_memory_block(SENTINEL, b'\x76')
            m.set_breakpoint(SENTINEL)
            def w(name, v): m.set_memory_block(sym['_' + name], struct.pack('<h', s16(v)))
            def rw(addr): return struct.unpack('<H', bytes(m.memory[addr:addr + 2]))[0]
            rng = random.Random(5)
            drawn = 0
            for trial in range(6000):
                camera = rng.choice([0, 100, 7000, -300, 16000, rng.randrange(-16000, 24000)])
                left, right = s16(camera + 8), s16(camera + 256)
                top, limit = rng.choice([0, 4, 20, 14]), rng.choice([159, 161, 172, 142])
                page = rng.randrange(2)
                piece = (rng.randrange(-60, 60), rng.randrange(-60, 60), rng.randrange(1, 64), rng.randrange(1, 40),
                         rng.randrange(256), rng.randrange(1024))
                x = s16(camera + rng.randrange(-80, 330)) if rng.random() < 0.9 else rng.randrange(-32768, 32768)
                row = rng.randrange(-80, 230)
                for name, v in (('s_Left', left), ('s_Right', right), ('s_Top', top), ('s_Limit', limit),
                                ('s_X', x), ('s_Row', row)):
                    w(name, v)
                m.set_memory_block(sym['_s_Page'], bytes([page]))
                m.set_memory_block(sym['_g_Piece'], struct.pack('<HbbBBBH', 0, *piece))
                m.set_memory_block(sym['_g_VDP_Command'], bytes(15))
                m.set_memory_block(sym['_g_Calls'], b'\x00')
                m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
                m.sp, m.pc, m.ix = STACK - 2, sym['_Test'], 0x1234
                m.ticks_to_stop = 20000
                while m.pc != SENTINEL:
                    self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
                self.assertEqual(m.ix, 0x1234)
                want = model(piece, x, row, page, left, right, top, limit)
                cmd = sym['_g_VDP_Command']
                self.assertEqual((rw(cmd), rw(cmd + 2)), want[-2:], trial)
                calls = m.memory[sym['_g_Calls']]
                if want[0] is None:
                    self.assertEqual(calls, 0, trial)
                    continue
                drawn += 1
                self.assertEqual(calls, 1, trial)
                got = (rw(cmd + 6), rw(cmd + 10), m.memory[sym['_g_Ring']], rw(sym['_g_Width']))
                self.assertEqual(got, want[:4], trial)
                self.assertEqual((m.memory[cmd + 13], m.memory[cmd + 14]), (0, 0x98), trial)
            self.assertGreater(drawn, 1500)


if __name__ == '__main__':
    unittest.main()
