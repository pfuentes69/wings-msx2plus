"""Vdp_RingCopy (src/msx/vdp_ring.c) on an emulated Z80: a copy onto the
256-px ring page is one command, or two split at x 256 with the source
continuing. A stub logs each command block MSXgl's setup would send."""
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
    ld bc, #0xA5A5
    ld hl, #0x5A5A
    ret
"""


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class VdpRingZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        work = Path(cls.temp.name)
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', '-I', str(ROOT / 'MSXgl/engine/src'), '-I', str(ROOT), '-I', str(ROOT / 'src/msx'),
                        '-c', str(ROOT / 'src/msx/vdp_ring.c'), '-o', str(work) + '/'], check=True, capture_output=True)
        (work / 'stub.s').write_text(STUB)
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=work, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'vdp_ring.rel', 'stub.rel', '-o', 'ring.ihx'], cwd=work, check=True, capture_output=True)
        cls.entry = int(re.search(r'^\s+([0-9A-F]{8})\s+_Vdp_RingCopy', (work / 'ring.map').read_text(), re.M).group(1), 16)
        cls.image = []
        for line in (work / 'ring.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                cls.image.append((address, bytes.fromhex(line[9:9 + 2 * count])))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def copy(self, fields, ring, width):
        m = z80.Z80Machine()
        for address, data in self.image:
            m.set_memory_block(address, data)
        m.set_memory_block(COMMAND, fields)
        m.set_memory_block(LOG_POINTER, struct.pack('<H', LOG))
        m.set_memory_block(SENTINEL, b'\x76')
        m.set_breakpoint(SENTINEL)
        m.set_memory_block(STACK - 2, struct.pack('<H', SENTINEL))
        m.sp, m.pc, m.a, m.de = STACK - 2, self.entry, ring, width
        m.ticks_to_stop = 100000
        while m.pc != SENTINEL:
            assert not m.run() & m._TICKS_LIMIT_HIT
        end = m.memory[LOG_POINTER] | m.memory[LOG_POINTER + 1] << 8
        log = bytes(m.memory[LOG:end])
        return [log[i:i + 15] for i in range(0, len(log), 15)]

    def test_splits_at_the_seam(self):
        rng = random.Random(3)
        for _ in range(4000):
            sx, sy, dy, ny = rng.randrange(256), rng.randrange(1024), rng.randrange(512), rng.randrange(1, 64)
            ring, width = rng.randrange(256), rng.choice([rng.randrange(1, 257), 256 - rng.randrange(256), 1, 256])
            width = max(1, min(256, width))
            cmd, arg = rng.choice([0xD0, 0x98, 0x90]), rng.randrange(256)
            fields = struct.pack('<6H3B', sx, sy, 0x1234, dy, 0x5678, ny, 0x77, arg, cmd)
            want, room = [], 256 - ring
            if width <= room:
                want.append(struct.pack('<6H3B', sx, sy, ring, dy, width, ny, 0x77, arg, cmd))
            else:
                want.append(struct.pack('<6H3B', sx, sy, ring, dy, room, ny, 0x77, arg, cmd))
                want.append(struct.pack('<6H3B', sx + room, sy, 0, dy, width - room, ny, 0x77, arg, cmd))
            self.assertEqual(self.copy(fields, ring, width), want, (ring, width))


if __name__ == '__main__':
    unittest.main()
