"""The cockpit window (src/msx/cockpit.c) on an emulated Z80, against the
model in tools/convert_cockpit.py: the scene it computes from the plane's
place, and the picture its VDP commands compose (the commands are logged by a
stub and replayed here) on map a.
"""
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
import warnings

try:
    import z80
except ImportError:  # optional dev dependency (requirements.txt)
    z80 = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
FLAGS = ['-mz80', '--opt-code-speed', '-DTARGET=TARGET_ROM_ASCII8', '-DROM_SIZE=512', '-DMSX_VERSION=MSX_2P',
         f'-I{ROOT}', f'-I{ROOT}/MSXgl/engine/src', f'-I{ROOT}/MSXgl/engine/content', f'-I{ROOT}/MSXgl/tools',
         f'-I{ROOT}/src', f'-I{ROOT}/src/generated/map_a', '-DWINGS_FLIGHT_MAX_Y=1200u']
LOG, STACK, SENTINEL = 0xD000, 0xF000, 0x3000
# The VDP: each command's registers (g_VDP_Command, 15 bytes) appended to a
# log at LOG + 2 (LOG holds the end).
STUB = """
    .module stub
    .globl _VDP_CommandSetupR32, _VDP_CommandSetupR36, _VDP_CommandWait, _VDP_WriteVRAM_128K, _Scenery_Read
    .globl _g_VDP_Command, _g_Planes, _g_Island, _g_IslandWrecks
    .area _CODE
_VDP_CommandSetupR32:
_VDP_CommandSetupR36:
    ld hl, #_g_VDP_Command
    ld de, (0xD000)
    ld bc, #15
    ldir
    ld (0xD000), de
    ret
_VDP_CommandWait:
_VDP_WriteVRAM_128K:
_Scenery_Read:
    ret
    .area _DATA
_g_VDP_Command: .ds 15
_g_Planes: .ds 512
_g_Island: .ds 1024
_g_IslandWrecks: .ds 1
"""


class Cockpit:
    def __init__(self, workdir):
        sdcc = shutil.which('sdcc')
        for source in ('src/msx/cockpit.c', 'src/generated/cockpit_art.c'):
            subprocess.run([sdcc, *FLAGS, '-c', str(ROOT / source), '-o', str(workdir) + '/'], check=True, capture_output=True)
        (workdir / 'stub.s').write_text(STUB)
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=workdir, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'cockpit.rel', 'cockpit_art.rel', 'stub.rel', '-o', 'cockpit.ihx'], cwd=workdir, check=True, capture_output=True)
        self.symbols = dict((n, int(a, 16)) for a, n in
                            re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (workdir / 'cockpit.map').read_text(), re.M))
        self.machine = z80.Z80Machine()
        for line in (workdir / 'cockpit.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                self.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        self.machine.set_memory_block(SENTINEL, b'\x76')
        self.machine.set_breakpoint(SENTINEL)
        state = self.symbols['_g_Cockpit']
        self.machine.set_memory_block(state, bytes(19) + b'\xff\xff\xff')   # nothing composed, nothing shown
        self.ticks = []

    def wreck(self, huts):
        """The huts' wrecked flags (IslandBuilding: 8 bytes, wrecked at +3)."""
        island = self.symbols['_g_Island']
        for i in range(8):
            self.machine.set_memory_block(island + 8 * i + 3, bytes([1 if i in huts else 0]))
        wrecks = self.symbols['_g_IslandWrecks']
        self.machine.set_memory_block(wrecks, bytes([(self.machine.memory[wrecks] + 1) & 255]))

    def call(self, entry, stack=b'', **registers):
        m = self.machine
        m.set_memory_block(STACK - 2 - len(stack), bytes([SENTINEL & 255, SENTINEL >> 8]) + stack)
        m.sp, m.pc, m.ix = STACK - 2 - len(stack), self.symbols[entry], 0x1234
        for name, value in registers.items(): setattr(m, name, value)
        budget = 400000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:
            assert not m.run() & m._TICKS_LIMIT_HIT, 'did not return'
        assert m.ix == 0x1234, 'IX not preserved'
        return budget - m.ticks_to_stop

    def render(self, page, x, altitude, left):
        """Cockpit_Draw(page, x, y, facing_left): sdcccall(1), page in A, x in
        DE, y and facing on the stack. Returns its T-states."""
        y = 1200 - altitude
        return self.call('_Cockpit_Draw', bytes([y & 255, y >> 8, left]), a=page, de=x)

    def draw(self, page, x, altitude, left):
        """A render, the idle time after it (Cockpit_Work), the next render
        of the page: the VDP commands issued."""
        m = self.machine
        m.set_memory_block(LOG, (LOG + 2).to_bytes(2, 'little'))
        self.ticks.append(self.render(page, x, altitude, left))
        self.work_ticks = self.call('_Cockpit_Work')
        self.render(page, x, altitude, left)
        end = int.from_bytes(bytes(m.memory[LOG:LOG + 2]), 'little')
        raw = bytes(m.memory[LOG + 2:end])
        return [raw[i:i + 15] for i in range(0, len(raw), 15)]

    def scene(self):
        state = self.symbols['_g_Cockpit']
        return bytes(self.machine.memory[state:state + 19])


class VRAM:
    """Pixels by (x, y), y up to 1023, for the commands the cockpit uses."""
    def __init__(self):
        self.pixels = {}

    def run(self, command):
        sx, sy, dx, dy, nx, ny = (int.from_bytes(command[i:i + 2], 'little') for i in range(0, 12, 2))
        clr, arg, cmd = command[12:15]
        assert arg == 0, 'left to right, top down'
        op = cmd & 0xF0
        for yy in range(ny):
            for xx in range(nx):
                if op == 0xC0:      # HMMV: bytes, two pixels each
                    self.pixels[(dx + xx, dy + yy)] = clr >> 4 if (dx + xx) % 2 == 0 else clr & 15
                elif op in (0x90, 0xD0):   # LMMM (TIMP), HMMM
                    c = self.pixels.get((sx + xx, sy + yy), 0)
                    if op == 0x90 and cmd & 15 == 8 and not c: continue
                    assert op == 0xD0 or cmd & 15 == 8, hex(cmd)
                    self.pixels[(dx + xx, dy + yy)] = c
                else:
                    raise AssertionError(f'unexpected command {cmd:02x}')


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class CockpitZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter('ignore')
        import convert_cockpit
        cls.model = convert_cockpit
        cls.temp = tempfile.TemporaryDirectory()
        cls.cockpit = Cockpit(Path(cls.temp.name))
        art = (ROOT / 'src/generated/cockpit_art.c').read_text()
        xs = [int(v) for v in re.search(r'g_CockpitSlotX\[COCKPIT_SLOTS\] = \{([^}]*)\}', art).group(1).split(',')]
        ys = [int(v) for v in re.search(r'g_CockpitSlotY\[COCKPIT_SLOTS\] = \{([^}]*)\}', art).group(1).split(',')]
        header = (ROOT / 'src/generated/cockpit_art.h').read_text()
        cls.window = tuple(int(re.search(rf'#define COCKPIT_WINDOW_{a} (\d+)', header).group(1)) for a in 'XY')
        slots, _ = convert_cockpit.art()
        cls.vram = VRAM()
        for s in range(1, len(xs)):
            for y in range(24):
                for x in range(48):
                    cls.vram.pixels[(xs[s] + x, ys[s] + y)] = slots[s][y * 48 + x]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self, page, x, altitude, left, huts=()):
        commands = self.cockpit.draw(page, x, altitude, left)
        want = self.model.scene('a', x, altitude, left, 0, set(huts))
        self.assertEqual(self.cockpit.scene(), want, (x, altitude, left))
        for c in commands: self.vram.run(c)
        wx, wy = self.window
        got = bytes(self.vram.pixels.get((wx + xx, page * 256 + 172 + wy + yy), 255) for yy in range(24) for xx in range(46))
        self.assertEqual(got, self.model.compose(want), (x, altitude, left))
        return commands

    def test_views_match_the_model(self):
        self.cockpit.wreck(())
        cases = [(7032, 0, 1), (7300, 0, 1), (6700, 0, 1), (7032, 0, 0), (6620, 30, 1), (7590, 30, 1),
                 (6000, 40, 0), (6400, 20, 0), (4400, 60, 1), (3600, 40, 1), (3200, 40, 1), (2900, 10, 1),
                 (2700, 90, 1), (1000, 150, 0), (500, 186, 0), (500, 187, 1), (40, 50, 1), (7600, 50, 0)]
        rng = random.Random(1)
        cases += [(rng.randrange(0, 7608), rng.randrange(0, 256), rng.randrange(2)) for _ in range(150)]
        for page, (x, altitude, left) in enumerate(cases):
            self.check(page & 1, x, altitude, left)

    def test_a_wrecked_hut_changes_the_view(self):
        self.cockpit.wreck(())
        self.check(0, 2900, 20, 1)
        try:
            self.cockpit.wreck({0, 1})
            self.check(1, 2900, 20, 1, huts={0, 1})
        finally:
            self.cockpit.wreck(())

    def test_an_unchanged_scene_issues_no_commands(self):
        self.check(0, 3100, 40, 1)
        self.check(1, 3100, 40, 1)   # copied to the other page
        self.assertEqual(self.check(1, 3100, 40, 1), [])
        self.assertEqual(self.check(1, 3101, 41, 1), [])   # same column, same rows

    def test_without_idle_time_renders_compose_a_step_each(self):
        self.check(0, 3300, 40, 1)
        m = self.cockpit.machine
        state = self.cockpit.symbols['_g_Cockpit']
        generation = m.memory[state + 19]
        for k in range(4):
            self.cockpit.render(0, 3200, 40, 1)
            self.assertEqual(m.memory[state + 19], generation, k)   # waiting, then a step a render
        self.cockpit.render(0, 3200, 40, 1)
        self.assertNotEqual(m.memory[state + 19], generation)
        self.assertEqual(self.cockpit.scene(), self.model.scene('a', 3200, 40, 1))

    def test_cost(self):
        self.cockpit.ticks.clear()
        rng = random.Random(2)
        for _ in range(40):
            self.check(0, rng.randrange(0, 4200), rng.randrange(0, 150), rng.randrange(2))
        work = []
        for _ in range(40):
            self.check(0, rng.randrange(0, 4200), rng.randrange(0, 150), rng.randrange(2))
            work.append(self.cockpit.work_ticks)
        print(f'\ncockpit window: a render worst {max(self.cockpit.ticks)} T-states, mean {sum(self.cockpit.ticks) // len(self.cockpit.ticks)};'
              f' composing (idle time) worst {max(work)}, mean {sum(work) // len(work)}')


if __name__ == '__main__':
    unittest.main()
