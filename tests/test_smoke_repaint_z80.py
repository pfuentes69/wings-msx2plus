"""The Z80 repaint of one column under a smoke-path shape (src/msx/
smoke_repaint.h, RepaintColumn) against the C it replaced, in Python. The
tile row lookup, the column decode and the VDP setup are stubs that record
what they are given; every command sent is compared."""
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
ROWS, UNIFORM, TILES = 19, 2, 1013
COLORS = (0x00, 0x08)
SOURCE = r'''
#include <stdint.h>
typedef uint16_t u16; typedef uint8_t u8;
#define TERRAIN_MAP_ROWS 19
#define TERRAIN_UNIFORM_COUNT 2
#define TERRAIN_TILE_COUNT 1013
#define VDP_CMD_HMMV 0xC0
#define VDP_CMD_HMMM 0xD0
typedef struct { u16 SX, SY, DX, DY, NX, NY; u8 CLR, ARG, CMD; } VDP_Command;
VDP_Command g_VDP_Command;
const unsigned char g_TerrainUniformColor[TERRAIN_UNIFORM_COUNT] = {0x00, 0x08};
u8 g_TileSourceX;
u16 g_Map[TERRAIN_MAP_ROWS + 1];
u8 g_Decodes; u16 g_DecodedWorld;
VDP_Command g_Sent[24]; u8 g_SentCount;
u16 Terrain_TileY(u16 tile) { g_TileSourceX = (u8)(tile * 3); return 692 + (tile & 7) * 8 + (tile >> 3) * 512 % 1024; }
void Terrain_DecodeColumn(u16 world, u16* out) { u8 i; ++g_Decodes; g_DecodedWorld = world; for (i = 0; i <= TERRAIN_MAP_ROWS; ++i) out[i] = g_Map[i]; }
void VDP_CommandSetupR32(void) { g_Sent[g_SentCount++] = g_VDP_Command; }
u16 g_Column[TERRAIN_MAP_ROWS];
static u16 s_Decoded[TERRAIN_MAP_ROWS + 1];
static u16 s_Column;
static const u16* s_Cached;
static u8 s_RepaintRow, s_Y8, s_Next8, s_Bottom8, s_Origin8, s_Page8, s_DecodedOnce;
#include "smoke_repaint.h"
void Test(u8 first, u8 top, u8 bottom, u8 origin, u8 page, u16 world)
{
    s_Origin8 = origin; s_Bottom8 = bottom; s_Page8 = page; s_Column = world;
    s_Cached = &g_Column[first]; s_RepaintRow = first; s_Y8 = top; s_DecodedOnce = 0;
    g_SentCount = 0; g_Decodes = 0;
    g_VDP_Command.DX = world & 255; g_VDP_Command.NX = 8; g_VDP_Command.ARG = 0;
    RepaintColumn();
}
'''


def tile_y(tile):
    return (692 + (tile & 7) * 8 + (tile >> 3) * 512 % 1024) & 0xffff, (tile * 3) & 255


def model(column, mapped, first, top, bottom, origin, page, world):
    sent, decodes, row, y = [], 0, first, top
    sx, sy, clr = 0, 0, 0
    while True:
        nxt = min(origin + (row + 1) * 8, bottom)
        tile = column[row]
        if tile >= TILES:
            decodes = 1
            tile = mapped[row]
        if tile < TILES:
            dy, ny = page * 256 + y, (nxt - y) & 0xffff
            if tile < UNIFORM:
                clr, cmd = COLORS[tile] * 17, 0xC0
            else:
                base, sx = tile_y(tile)
                sy, cmd = (base + (y - origin) - row * 8) & 0xffff, 0xD0
            sent.append((sx, sy, world & 255, dy, 8, ny, clr, 0, cmd))
        y = nxt; row += 1
        if y >= bottom:
            return sent, decodes


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SmokeRepaintZ80Tests(unittest.TestCase):
    def test_matches_the_c(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 'r.c').write_text(SOURCE)
            sdcc = shutil.which('sdcc')
            subprocess.run([sdcc, '-mz80', '--opt-code-speed', '-I', str(ROOT / 'src/msx'), '-c', 'r.c'],
                           cwd=work, check=True, capture_output=True)
            subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                            'r.rel', '-o', 'r.ihx'], cwd=work, check=True, capture_output=True)
            sym = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'r.map').read_text(), re.M))
            m = z80.Z80Machine()
            for line in (work / 'r.ihx').read_text().split():
                count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
                if kind == 0:
                    m.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
            m.set_memory_block(SENTINEL, b'\x76')
            m.set_breakpoint(SENTINEL)
            rng = random.Random(6)
            commands = 0
            for trial in range(3000):
                pan = rng.choice([0, 8, 16, 24, 56])
                origin = 24 + pan
                pick = lambda: rng.choice([0, 0, 1, rng.randrange(2, TILES), 65535])
                column = [pick() for _ in range(ROWS)]
                mapped = [rng.choice([0, 1, rng.randrange(2, TILES), 65535]) for _ in range(ROWS + 1)]
                top = rng.randrange(origin, 172)
                bottom = rng.randrange(top + 1, 173)
                first = (top - origin) >> 3
                if first >= ROWS:
                    continue
                bottom = min(bottom, origin + ROWS * 8)
                if bottom <= top:
                    continue
                page, world = rng.randrange(2), rng.randrange(65536)
                m.set_memory_block(sym['_g_Column'], b''.join(struct.pack('<H', t) for t in column))
                m.set_memory_block(sym['_g_Map'], b''.join(struct.pack('<H', t) for t in mapped))
                m.set_memory_block(STACK - 7, bytes([SENTINEL & 255, SENTINEL >> 8, bottom, origin, page,
                                                     world & 255, world >> 8]))
                m.sp, m.pc, m.a, m.l = STACK - 7, sym['_Test'], first, top
                m.ix = 0x1234
                m.ticks_to_stop = 400000
                while m.pc != SENTINEL:
                    self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
                want, decodes = model(column, mapped, first, top, bottom, origin, page, world)
                n = m.memory[sym['_g_SentCount']]
                got = [struct.unpack_from('<HHHHHHBBB', bytes(m.memory[sym['_g_Sent'] + 15 * k:sym['_g_Sent'] + 15 * k + 15]))
                       for k in range(n)]
                # SX/SY/CLR of a command that does not use them carry over: compare what each uses.
                def used(c):
                    sx, sy, dx, dy, nx, ny, clr, arg, cmd = c
                    return (dx, dy, nx, ny, arg, cmd) + ((clr,) if cmd == 0xC0 else (sx, sy))
                self.assertEqual([used(c) for c in got], [used(c) for c in want], trial)
                self.assertEqual(m.memory[sym['_g_Decodes']], decodes, trial)
                if decodes:
                    self.assertEqual(struct.unpack('<H', bytes(m.memory[sym['_g_DecodedWorld']:sym['_g_DecodedWorld'] + 2]))[0], world)
                commands += n
            self.assertGreater(commands, 3000)


if __name__ == '__main__':
    unittest.main()
