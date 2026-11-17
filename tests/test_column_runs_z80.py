"""Column_Runs (src/msx/column_ops.c), the hand-written Z80 core of
Terrain_DrawColumn, against a model of the C loop it replaced
(mission_streamer.c under WINGS_TERRAIN_C), on an emulated Z80.

Stubs stand in for the tile tables and MSXgl's VDP command setup; each setup
call logs the command block, so the test compares every command issued and
the final tile cache."""
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
ROWS = 19
TILES = 400
COLORS, LIMITS, TILE_X, TILE_Y, COMMAND = 0xD400, 0xD600, 0xD800, 0xDA00, 0xC800
LOG_POINTER, LOG = 0xC900, 0xE000
CACHE, DECODED, STACK, SENTINEL = 0xD000, 0xD100, 0xF000, 0x3000
COLUMNS, CACHED = 0xA000, 0xA100   # g_TerrainColumns[2][32], g_TerrainCached[2][32][ROWS]
STUB = f"""
    .module stub
    .globl _g_MissionTileColors, _g_MissionTileLimit, _g_MissionTileX, _g_MissionTileY
    .globl _g_VDP_Command, _VDP_CommandSetupR32, _VDP_CommandSetupR36
    .globl _g_TerrainColumns, _g_TerrainCached
    _g_TerrainColumns = {COLUMNS:#06x}
    _g_TerrainCached = {CACHED:#06x}
    _g_MissionTileColors = {COLORS:#06x}
    _g_MissionTileLimit = {LIMITS:#06x}
    _g_MissionTileX = {TILE_X:#06x}
    _g_MissionTileY = {TILE_Y:#06x}
    _g_VDP_Command = {COMMAND:#06x}
    .area _CODE
_VDP_CommandSetupR32:
    ld a, #32
    jr log
_VDP_CommandSetupR36:
    ld a, #36
log:
    push de
    ld hl, ({LOG_POINTER:#06x})
    ld (hl), a
    inc hl
    ex de, hl
    ld hl, #{COMMAND:#06x}
    ld bc, #15
    ldir
    ld ({LOG_POINTER:#06x}), de
    pop de
    ld bc, #0xA5A5        ; the real setup clobbers A, B, C and HL
    ld hl, #0x5A5A
    ret
"""


def model(cache, decoded, x, y, colors, limits, tile_x, tile_y):
    """The C loop of Terrain_DrawColumn (decoded ends with the 65534 sentinel).
    Rows panned below the playfield (y % 256 >= 172) update the cache only."""
    decoded, cache = decoded + [65534], cache + [0x1234]
    log, row, i = [], 0, 0
    while True:
        k = 0
        while decoded[i + k] == cache[i + k]:
            k += 1
        row += k
        if row >= ROWS:
            return log, cache[:ROWS], y
        i += k
        y += k * 8
        tile, count, color = decoded[i], 1, colors[decoded[i]]
        if color != 255:
            while row + count < ROWS and decoded[i + count] == tile:
                count += 1
        else:
            while row + count < ROWS and count < limits[tile] and decoded[i + count] == tile + count:
                count += 1
        height = count * 8
        if y % 256 + height > 172:
            height = 172 - y % 256
        if y % 256 >= 172:
            pass                      # panned below the playfield: cache only
        elif color != 255:
            log.append(('HMMV', x, y, 8, height, color * 17))
        else:
            log.append(('HMMM', tile_x[tile], tile_y[tile], x, y, 8, height))
        cache[i:i + count] = decoded[i:i + count]
        row += count
        i += count
        y += count * 8


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class ColumnRunsZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', f'-DTERRAIN_MAP_ROWS={ROWS}', '-c', str(ROOT / 'src/msx/column_ops.c'),
                        '-o', str(work) + '/'], check=True, capture_output=True)
        (work / 'stub.s').write_text(STUB)
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=work, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'column_ops.rel', 'stub.rel', '-o', 'column_ops.ihx'], cwd=work, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'column_ops.map').read_text(), re.M))
        cls.entry, cls.column_x, cls.column_y = symbols['_Column_Runs'], symbols['_g_ColumnX'], symbols['_g_ColumnY']
        cls.dirty, cls.dirty_range = symbols['_Terrain_DirtyOverlay'], symbols['_g_DirtyRange']
        cls.machine = z80.Z80Machine()
        for line in (work / 'column_ops.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                cls.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        cls.machine.set_memory_block(SENTINEL, b'\x76')
        cls.machine.set_breakpoint(SENTINEL)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_dirty_overlay_marks_the_columns_it_covers(self):
        # The C it replaced: for each column from left & ~7 while < right,
        # mark the ring column's map column and rows first..last invalid.
        rng, m = random.Random(5), self.machine
        size = 2 * 32 * 2 + 2 * 32 * ROWS * 2
        for _ in range(3000):
            left = rng.randrange(0, 9000)
            right = left + rng.choice([rng.randrange(-4, 80), 2, 8, 64, 256])
            page, first = rng.randrange(2), rng.randrange(ROWS)
            last = rng.randrange(first, ROWS)
            before = bytes(rng.randrange(256) for _ in range(size))
            m.set_memory_block(COLUMNS, before[:128])
            m.set_memory_block(CACHED, before[128:])
            m.set_memory_block(self.dirty_range, struct.pack('<2H3B', left, right & 0xFFFF, page, first, last))
            m.set_memory_block(STACK - 2, SENTINEL.to_bytes(2, 'little'))
            m.sp, m.pc = STACK - 2, self.dirty
            m.ticks_to_stop = 100000
            while m.pc != SENTINEL:
                assert not m.run() & m._TICKS_LIMIT_HIT
            want = bytearray(before)
            column = left & ~7
            while column < right:
                slot = (column & 255) >> 3
                want[(page * 32 + slot) * 2:(page * 32 + slot) * 2 + 2] = b'\xff\xff'
                for row in range(first, last + 1):
                    o = 128 + ((page * 32 + slot) * ROWS + row) * 2
                    want[o:o + 2] = b'\xff\xff'
                column += 8
            got = bytes(m.memory[COLUMNS:COLUMNS + 128]) + bytes(m.memory[CACHED:CACHED + size - 128])
            self.assertEqual(got, bytes(want), (left, right, page, first, last))

    def words(self, values):
        return b''.join(v.to_bytes(2, 'little') for v in values)

    def run_column(self, cache, decoded, x, y, tables):
        m = self.machine
        colors, limits, tile_x, tile_y = tables
        m.set_memory_block(COLORS, bytes(colors))
        m.set_memory_block(LIMITS, bytes(limits))
        m.set_memory_block(TILE_X, bytes(tile_x))
        m.set_memory_block(TILE_Y, self.words(tile_y))
        m.set_memory_block(COMMAND, bytes([0x77] * 15))
        m.set_memory_block(LOG_POINTER, LOG.to_bytes(2, 'little'))
        m.set_memory_block(CACHE, self.words(cache + [0x1234]))
        m.set_memory_block(DECODED, self.words(decoded + [65534]))
        m.set_memory_block(self.column_x, bytes([x]))
        m.set_memory_block(self.column_y, y.to_bytes(2, 'little'))
        m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
        m.sp, m.pc, m.hl, m.de, m.ix = STACK - 2, self.entry, CACHE, DECODED, 0x1234
        m.ticks_to_stop = 1000000
        while m.pc != SENTINEL:
            self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
        self.assertEqual((m.sp, m.ix), (STACK, 0x1234))
        end = int.from_bytes(bytes(m.memory[LOG_POINTER:LOG_POINTER + 2]), 'little')
        log, raw = [], bytes(m.memory[LOG:end])
        for at in range(0, len(raw), 16):
            tag, block = raw[at], raw[at + 1:at + 16]
            w = lambda o: int.from_bytes(block[o:o + 2], 'little')
            self.assertEqual(block[13], 0)                      # ARG
            if tag == 36:
                self.assertEqual(block[14], 0xC0)
                log.append(('HMMV', w(4), w(6), w(8), w(10), block[12]))
            else:
                self.assertEqual((tag, block[14]), (32, 0xD0))
                log.append(('HMMM', w(0), w(2), w(4), w(6), w(8), w(10)))
        data = bytes(m.memory[CACHE:CACHE + 2 * ROWS])
        cache_out = [int.from_bytes(data[i:i + 2], 'little') for i in range(0, len(data), 2)]
        y_out = int.from_bytes(bytes(m.memory[self.column_y:self.column_y + 2]), 'little')
        return log, cache_out, y_out, 1000000 - m.ticks_to_stop

    def test_runs_match_the_c_loop(self):
        rng = random.Random(7)
        worst = 0
        for trial in range(1500):
            colors = [rng.randrange(16) if rng.random() < 0.3 else 255 for _ in range(TILES)]
            limits = [rng.randint(1, 9) for _ in range(TILES)]
            tile_x = [rng.randrange(0, 256, 8) for _ in range(TILES)]
            tile_y = [512 + rng.randrange(512) for _ in range(TILES)]
            decoded, left = [], ROWS
            while left:
                kind, n = rng.random(), rng.randint(1, left)
                start = rng.randrange(TILES - 20)
                if kind < 0.4:
                    decoded += [start] * n          # repeated tile (solid-colour runs)
                elif kind < 0.8:
                    decoded += list(range(start, start + n))   # stacked atlas tiles
                else:
                    decoded += [rng.randrange(TILES) for _ in range(n)]
                left -= n
            cache = [d if rng.random() < 0.4 else rng.choice([65535, rng.randrange(TILES)]) for d in decoded]
            if trial % 10 == 0:
                cache = list(decoded)                        # nothing to draw
            x = rng.randrange(0, 256, 8)
            y = rng.choice([0, 256]) + 24 + 8 * rng.randrange(7)   # close-view pan 0..6 rows
            expected = model(list(cache), decoded, x, y, colors, limits, tile_x, tile_y)
            log, cache_out, y_out, ticks = self.run_column(cache, decoded, x, y, (colors, limits, tile_x, tile_y))
            self.assertEqual(log, expected[0], trial)
            self.assertEqual(cache_out, expected[1], trial)
            self.assertEqual(y_out, expected[2], trial)
            worst = max(worst, ticks)
        print(f'\nColumn_Runs: at most {worst} T-states per column (stubbed VDP setup)')


if __name__ == '__main__':
    unittest.main()
