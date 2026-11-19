"""The Z80 sky test of the smoke erase (src/msx/smoke_sky.h, AllSky) against
the C it replaced (SkyRows over a box's columns), in Python."""
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
SOURCE = r'''
#include <stdint.h>
typedef uint16_t u16; typedef uint8_t u8;
#define TERRAIN_MAP_ROWS 19
#define TERRAIN_UNIFORM_COUNT 2
#define TERRAIN_TILE_COUNT 1013
u16 g_TerrainCached[2][32][TERRAIN_MAP_ROWS];
const unsigned char g_TerrainUniformColor[TERRAIN_UNIFORM_COUNT] = {0x00, 0x08};
static const u16* s_SkyPtr;
static u8 s_SkySlot, s_SkyCols, s_SkyRows;
#include "smoke_sky.h"
u8 Test(u8 page, u8 slot, u8 first, u8 cols, u8 rows)
{
    s_SkySlot = slot; s_SkyPtr = &g_TerrainCached[page][slot][first];
    s_SkyCols = cols; s_SkyRows = rows;
    return AllSky();
}
'''
COLORS = (0x00, 0x08)


def model(cache, page, slot, first, cols, rows):
    for c in range(cols):
        for r in range(first, first + rows):
            tile = cache[page][(slot + c) & 31][r]
            if tile >= TILES or (tile >= UNIFORM or COLORS[tile]):
                return 0
    return 1


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SmokeSkyZ80Tests(unittest.TestCase):
    def test_matches_the_c(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            (work / 's.c').write_text(SOURCE)
            sdcc = shutil.which('sdcc')
            subprocess.run([sdcc, '-mz80', '--opt-code-speed', '-I', str(ROOT / 'src/msx'), '-c', 's.c'],
                           cwd=work, check=True, capture_output=True)
            subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                            's.rel', '-o', 's.ihx'], cwd=work, check=True, capture_output=True)
            sym = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 's.map').read_text(), re.M))
            m = z80.Z80Machine()
            for line in (work / 's.ihx').read_text().split():
                count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
                if kind == 0:
                    m.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
            m.set_memory_block(SENTINEL, b'\x76')
            m.set_breakpoint(SENTINEL)
            rng = random.Random(4)
            worst, sky = 0, 0
            for trial in range(3000):
                # Mostly sky, with sea (1), copied tiles and overlay rows.
                cache = [[[0 if rng.random() < 0.93 else rng.choice([1, 2, 300, 1012, 65535, 256])
                           for _ in range(ROWS)] for _ in range(32)] for _ in range(2)]
                if trial % 3 == 0:
                    cache = [[[0] * ROWS for _ in range(32)] for _ in range(2)]
                    cache[rng.randrange(2)][rng.randrange(32)][rng.randrange(ROWS)] = rng.choice([1, 256, 65535])
                data = b''.join(struct.pack('<H', t) for page in cache for slot in page for t in slot)
                m.set_memory_block(sym['_g_TerrainCached'], data)
                page, slot = rng.randrange(2), rng.randrange(32)
                first = rng.randrange(ROWS)
                rows = rng.randrange(1, ROWS - first + 1)
                cols = rng.randrange(1, 9)
                m.set_memory_block(STACK - 5, bytes([SENTINEL & 255, SENTINEL >> 8, first, cols, rows]))
                m.sp, m.pc, m.a, m.l = STACK - 5, sym['_Test'], page, slot
                m.ticks_to_stop = 100000
                while m.pc != SENTINEL:
                    self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
                want = model(cache, page, slot, first, cols, rows)
                self.assertEqual(m.a, want, (trial, page, slot, first, cols, rows))
                sky += want
                if want:
                    worst = max(worst, (100000 - m.ticks_to_stop) / (cols * rows))
            self.assertGreater(sky, 500)
            print(f'\nAllSky: ~{worst:.0f} T-states a tile (with the test wrapper)')


if __name__ == '__main__':
    unittest.main()
