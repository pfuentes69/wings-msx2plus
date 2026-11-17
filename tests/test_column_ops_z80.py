"""Terrain column helpers (src/msx/column_ops.c) on an emulated Z80."""
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

ROOT = Path(__file__).resolve().parents[1]
ROWS = 19
RUN, OUT, CACHE, STACK, SENTINEL = 0xD000, 0xD100, 0xD200, 0xF000, 0x3000


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class ColumnOpsZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', f'-DTERRAIN_MAP_ROWS={ROWS}', '-DTERRAIN_UNIFORM_COUNT=3', '-c', str(ROOT / 'src/msx/column_ops.c'),
                        '-o', str(work) + '/'], check=True, capture_output=True)
        # Column_Runs (tested in test_column_runs_z80.py) needs these symbols.
        (work / 'stub.s').write_text('''
    .module stub
    .globl _g_TerrainUniformColor, _g_TileSourceX, _Terrain_TileY
    .globl _g_VDP_Command, _VDP_CommandSetupR32, _VDP_CommandSetupR36
    .globl _g_TerrainColumns, _g_TerrainCached
    _g_TerrainColumns = 0xA000
    _g_TerrainCached = 0xA100
    _g_TerrainUniformColor = 0xD400
    _g_TileSourceX = 0xD600
    _g_VDP_Command = 0xC800
    .area _CODE
_Terrain_TileY:
    ret
_VDP_CommandSetupR32:
_VDP_CommandSetupR36:
    ret
''')
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=work, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'column_ops.rel', 'stub.rel', '-o', 'column_ops.ihx'], cwd=work, check=True, capture_output=True)
        cls.symbols = dict((n, int(a, 16)) for a, n in
                           re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'column_ops.map').read_text(), re.M))
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

    def call(self, name, hl, de):
        m = self.machine
        m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
        m.sp, m.pc, m.hl, m.de, m.ix, m.iy = STACK - 2, self.symbols[name], hl, de, 0x1234, 0x5678
        m.ticks_to_stop = 100000
        while m.pc != SENTINEL:
            self.assertFalse(m.run() & m._TICKS_LIMIT_HIT, 'did not return')
        self.assertEqual((m.sp, m.ix), (STACK, 0x1234))
        return m.a, 100000 - m.ticks_to_stop

    def words(self, address, count):
        data = bytes(self.machine.memory[address:address + 2 * count])
        return [int.from_bytes(data[i:i + 2], 'little') for i in range(0, len(data), 2)]

    def test_decode_expands_runs(self):
        rng = random.Random(1)
        for _ in range(3000):
            runs, left = [], ROWS
            while left:
                count = rng.randint(1, left) if rng.random() < 0.7 else 1
                runs.append((count, rng.randrange(65536)))
                left -= count
            if rng.random() < 0.2:  # zero-length runs are skipped
                runs.insert(rng.randrange(len(runs)), (0, rng.randrange(65536)))
            data = b''.join(bytes([c]) + t.to_bytes(2, 'little') for c, t in runs)
            self.machine.set_memory_block(RUN, data)
            self.machine.set_memory_block(OUT, bytes(2 * (ROWS + 1)))
            self.call('_Column_Decode', RUN, OUT)
            expected = [t for c, t in runs for _ in range(c)]
            self.assertEqual(self.words(OUT, ROWS + 1), expected + [0], runs)

    def test_equal_counts_leading_matches(self):
        rng = random.Random(2)
        ticks = 0
        for trial in range(3000):
            decoded = [rng.randrange(600) for _ in range(ROWS)] + [65534]
            cache = list(decoded[:ROWS])
            first = rng.randrange(ROWS + 1)
            if first < ROWS:
                cache[first] = rng.choice([65535, decoded[first] ^ rng.choice([1, 256, 257])])
            for i in range(first + 1, ROWS):
                if rng.random() < 0.3:
                    cache[i] = 65535
            start = rng.randrange(ROWS)
            self.machine.set_memory_block(CACHE, b''.join(v.to_bytes(2, 'little') for v in cache))
            self.machine.set_memory_block(OUT, b''.join(v.to_bytes(2, 'little') for v in decoded))
            result, used = self.call('_Column_Equal', CACHE + 2 * start, OUT + 2 * start)
            expected = 0
            while start + expected < ROWS and cache[start + expected] == decoded[start + expected]:
                expected += 1
            self.assertEqual(result, expected, (trial, start, cache, decoded))
            ticks += used
        self.assertLess(ticks / 3000, 900)  # plain Z80 T-states per call


if __name__ == '__main__':
    unittest.main()
