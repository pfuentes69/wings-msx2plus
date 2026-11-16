"""Waves_DrawBand (src/msx/wave_band.c), the Z80 band loop of the wave strip,
against the C it replaced (Waves_DrawBandC), both compiled with SDCC and run
on an emulated Z80. A stub stands in for MSXgl's VDP command setup and logs
each 15-byte command block; the two logs must match for random bands."""
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
COMMAND, LOG_POINTER, LOG, STACK, SENTINEL = 0xC800, 0xC900, 0xD000, 0xF000, 0x3000
STUB = f"""
    .module stub
    .globl _g_VDP_Command, _VDP_CommandSetupR32
    _g_VDP_Command = {COMMAND:#06x}
    .area _CODE
_VDP_CommandSetupR32:
    push de
    ld hl, ({LOG_POINTER:#06x})
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


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class WaveBandZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', '--opt-code-speed', '-DWINGS_WAVES_C_REFERENCE',
                        '-I', str(ROOT / 'MSXgl/engine/src'), '-I', str(ROOT), '-I', str(ROOT / 'src/msx'),
                        '-c', str(ROOT / 'src/msx/wave_band.c'), '-o', str(work) + '/'], check=True, capture_output=True)
        (work / 'stub.s').write_text(STUB)
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=work, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'wave_band.rel', 'stub.rel', '-o', 'band.ihx'], cwd=work, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (work / 'band.map').read_text(), re.M))
        cls.band, cls.asm, cls.c = symbols['_g_WaveBand'], symbols['_Waves_DrawBand'], symbols['_Waves_DrawBandC']
        cls.image = []
        for line in (work / 'band.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                cls.image.append((address, bytes.fromhex(line[9:9 + 2 * count])))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_band(self, entry, band):
        m = z80.Z80Machine()
        for address, data in self.image:
            m.set_memory_block(address, data)
        m.set_memory_block(self.band, struct.pack('<7H3B', *band))
        m.set_memory_block(LOG_POINTER, struct.pack('<H', LOG))
        m.set_memory_block(SENTINEL, b'\x76')
        m.set_breakpoint(SENTINEL)
        m.set_memory_block(STACK - 2, struct.pack('<H', SENTINEL))
        m.sp, m.pc = STACK - 2, entry
        budget = m.ticks_to_stop = 2_000_000
        while m.pc != SENTINEL:
            assert not m.run() & m._TICKS_LIMIT_HIT, 'did not return'
        end = m.memory[LOG_POINTER] | m.memory[LOG_POINTER + 1] << 8
        log = bytes(m.memory[LOG:end])
        return [log[i:i + 15] for i in range(0, len(log), 15)], budget - m.ticks_to_stop

    def test_matches_the_c_loop(self):
        rng = random.Random(7)
        asm_time = c_time = commands = 0
        for case in range(3000):
            frame = rng.randrange(12)
            start = rng.choice([rng.randrange(-30000, 30000), rng.randrange(-300, 8200), rng.randrange(0, 512)])
            end = start + rng.choice([rng.randrange(-5, 300), 248, 249, rng.randrange(1, 4)])
            row = rng.choice([0, 0, 2, rng.randrange(0, 11)])
            height = rng.randrange(1, 12 - row) if row < 11 else 1
            if row < 2 and rng.random() < 0.7:
                height = min(height, 2 - row)
            band = (rng.choice([48, 144]), 212 + (frame & 3) * 11 + (256 if frame >= 8 else 0),
                    rng.randrange(256), rng.randrange(400, 600),
                    start & 0xFFFF, end & 0xFFFF, rng.randrange(65536),
                    row, height, rng.random() < 0.4)
            want, c_ticks = self.run_band(self.c, band)
            got, asm_ticks = self.run_band(self.asm, band)
            self.assertEqual(got, want, (case, band))
            asm_time += asm_ticks; c_time += c_ticks; commands += len(want)
        print(f'\nwave band: {c_time / commands:.0f} T-states per command in C, {asm_time / commands:.0f} in Z80')
        self.assertLess(asm_time, c_time / 2)


if __name__ == '__main__':
    unittest.main()
