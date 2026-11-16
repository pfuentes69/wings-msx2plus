"""The MSX-MUSIC driver (src/msx/sound_fm.c) and the per-field sound
routine (src/msx/sound.c), compiled with SDCC and run on an emulated Z80.

The BIOS slot reads are emulated with a fake slot holding the signature.
The driver runs from its RAM copy, as on the machine, and every port write
is checked against the YM2413's timing: 12 cycles after an address write,
84 after a data write (one cycle is one T-state at 3.58 MHz)."""
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
DEFINES = ['-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
           '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u']
INCLUDES = ['-I', str(ROOT / 'MSXgl/engine/src'), '-I', str(ROOT), '-I', str(ROOT / 'src'), '-I', str(ROOT / 'src/msx')]
STACK, SENTINEL, RDSLT, WRSLT = 0xF000, 0x3000, 0x000C, 0x0014
SOUND_SCREAM, SOUND_SCREECH, SOUND_CLANG, SOUND_SPLASH, SOUND_BOOM = 1, 2, 3, 4, 5
# A caller for Sound_FMEngine with its arguments in RAM.
HELPER = """
#include "sound_fm.h"
unsigned short g_TestPeriod;
unsigned char g_TestVolume;
void Test_Engine(void) { Sound_FMEngine(g_TestPeriod, g_TestVolume); }
"""


class Machine:
    def __init__(self, workdir):
        sdcc = shutil.which('sdcc')
        for source in (ROOT / 'src/msx/sound.c', ROOT / 'src/msx/sound_fm.c', workdir / 'helper.c'):
            subprocess.run([sdcc, '-mz80', '--opt-code-speed', *DEFINES, *INCLUDES, '-c', str(source),
                            '-o', str(workdir) + '/'], check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'sound.rel', 'sound_fm.rel', 'helper.rel', '-o', 'sound.ihx'],
                       cwd=workdir, check=True, capture_output=True)
        self.symbols = dict((n, int(a, 16)) for a, n in
                            re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (workdir / 'sound.map').read_text(), re.M))
        self.image = []
        for line in (workdir / 'sound.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                self.image.append((address, bytes.fromhex(line[9:9 + 2 * count])))
        self.reset()

    def reset(self, slots=None):
        """slots: {slot id: {address: byte}}, the memory the BIOS's RDSLT sees."""
        self.machine = m = z80.Z80Machine()
        for address, data in self.image:
            m.set_memory_block(address, data)
        m.set_memory_block(0xC000, bytes(0x3000))           # RAM is not cleared at boot: zero it here
        m.set_memory_block(0xFCC1, bytes(4))                # EXPTBL: no expanded slots
        for address in (SENTINEL, RDSLT, WRSLT):
            m.set_memory_block(address, b'\x76')
            m.set_breakpoint(address)
        self.slots = slots or {}
        self.slot_writes = []
        self.writes = []                                    # (port, value, T-state)
        self.clock = 0
        m.set_output_callback(lambda port, value: self.writes.append((port & 255, value, self.clock + self.budget - m.ticks_to_stop)))

    def call(self, name, budget=2_000_000):
        m = self.machine
        m.set_memory_block(STACK - 2, bytes([SENTINEL & 255, SENTINEL >> 8]))
        m.sp, m.pc = STACK - 2, self.symbols['_' + name]
        self.budget = m.ticks_to_stop = budget
        while True:
            assert not m.run() & m._TICKS_LIMIT_HIT, f'{name} did not return'
            if m.pc == SENTINEL:
                break
            if m.pc not in (RDSLT, WRSLT):
                continue                                    # the emulator's frame boundary
            # The BIOS: RDSLT reads a byte of another slot, WRSLT writes one;
            # both return with interrupts off. Return to the caller.
            if m.pc == RDSLT:
                m.a = self.slots.get(m.a, {}).get(m.hl, 0xFF)
            elif m.pc == WRSLT:
                self.slot_writes.append((m.a, m.hl, m.e))
            ret = m.memory[m.sp] | m.memory[m.sp + 1] << 8
            m.sp += 2
            m.pc = ret
        spent = budget - m.ticks_to_stop
        self.clock += spent
        return spent

    def byte(self, name, offset=0):
        return self.machine.memory[self.symbols['_' + name] + offset]

    def word(self, name, offset=0):
        return self.byte(name, offset) | self.byte(name, offset + 1) << 8

    def poke(self, name, *values, offset=0):
        self.machine.set_memory_block(self.symbols['_' + name] + offset, bytes(values))

    def fm(self, since=0):
        """The YM2413 writes since index since, as (register, value)."""
        out, register = [], None
        for port, value, _ in self.writes[since:]:
            if port == 0x7C:
                register = value
            elif port == 0x7D:
                out.append((register, value))
        return out

    def field(self):
        """One field: the line interrupt's sound call. Returns its FM writes."""
        start = len(self.writes)
        self.call('Sound_Field')
        return self.fm(start)


def signature(text, address=0x4018):
    return {address + i: ord(c) for i, c in enumerate(text)}


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class SoundFMZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        workdir = Path(cls.temp.name)
        (workdir / 'helper.c').write_text(HELPER)
        cls.sound = Machine(workdir)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def loaded(self, slots=None):
        s = self.sound
        s.reset({2: signature('APRLOPLL')} if slots is None else slots)
        s.call('Sound_Reset')
        s.call('Sound_InitFM')
        # The PSG effects (Sound_LoadEffects, segment 22): none here.
        steps = s.symbols['_g_SoundSteps']
        for i in range(6):
            s.poke('g_SoundEffects', steps & 255, steps >> 8, offset=2 * i)
        s.poke('g_SoundGunRate', 6)
        for _ in range(3):
            s.field()                                       # the engine's first (silent) values, 2 a field
        return s

    def test_finds_built_in_msx_music_and_loads_the_driver(self):
        s = self.loaded()
        self.assertEqual(s.byte('g_SoundFM'), 1)
        size = s.symbols['_FM_DriverEnd'] - s.symbols['_FM_Driver']
        self.assertLessEqual(size, 300)
        code = bytes(s.machine.memory[s.symbols['_FM_Driver']:s.symbols['_FM_Driver'] + size])
        self.assertEqual(bytes(s.machine.memory[s.symbols['_g_FMDriver']:s.symbols['_g_FMDriver'] + size]), code)
        init = s.fm()
        self.assertIn((0x0E, 0x20), init)                                   # rhythm mode
        self.assertEqual([v for r, v in init if r < 8], [0x21, 0xA1, 0x0C, 0x0F, 0xF0, 0xF0, 0x0F, 0x0F])
        self.assertEqual(s.slot_writes, [])

    def test_an_fm_pac_is_found_and_enabled(self):
        s = self.loaded({1: {**signature('PAC2OPLL'), 0x7FF6: 0x10}})
        self.assertEqual(s.byte('g_SoundFM'), 1)
        self.assertEqual(s.slot_writes, [(1, 0x7FF6, 0x11)])

    def test_without_msx_music_the_psg_plays_alone(self):
        s = self.loaded({})
        self.assertEqual(s.byte('g_SoundFM'), 0)
        s.poke('g_SoundRequest', SOUND_BOOM)
        self.assertEqual(s.field(), [])
        self.assertTrue(any(port == 0xA0 for port, _, _ in s.writes))   # the PSG still runs

    def test_engine_registers_are_written_when_they_change(self):
        s = self.loaded()
        s.poke('g_TestPeriod', 335 & 255, 335 >> 8)
        s.poke('g_TestVolume', 64)
        s.call('Test_Engine')
        # fnum 131,700 / 335 = 393, the second channel 1/32 higher; block 2,
        # keyed on. At most 2 engine writes a field.
        self.assertEqual([s.field() for _ in range(4)],
                         [[(0x10, 393 & 255), (0x20, 0x15)], [(0x11, 405 & 255), (0x21, 0x15)],
                          [(0x30, 0x03), (0x31, 0x05)], []])
        s.poke('g_TestVolume', 40)                          # on deck: 3 + 24 / 4
        s.call('Test_Engine')
        self.assertEqual(s.field(), [(0x30, 0x09), (0x31, 0x0B)])
        s.poke('g_TestVolume', 0)                           # silent: keyed off too
        s.call('Test_Engine')
        self.assertEqual([s.field() for _ in range(2)], [[(0x20, 0x05), (0x21, 0x05)], [(0x30, 0x0F), (0x31, 0x0F)]])

    def test_guns_hit_the_snare_and_hi_hat_at_their_rate(self):
        s = self.loaded()
        s.poke('g_SoundGun', 12)
        fields = [s.field() for _ in range(18)]
        self.assertEqual([i + 1 for i, writes in enumerate(fields) if writes], [6, 12, 18])
        # hi-hat 5, snare 3; snare and hi-hat keyed off, then on again
        self.assertEqual(fields[5], [(0x37, 0x53), (0x0E, 0x20), (0x0E, 0x29)])

    def expected(self, script, atten, budget=4):
        """Interpret a script from its RAM bytes: the writes of each field,
        at most budget a field (the rest waits a field)."""
        fields, current, i = [], [], 0
        while True:
            if len(current) == budget:
                fields.append(current)
                current = []
            register, value = script[i], script[i + 1]
            i += 2
            if register == 0xFE:
                fields.append(current)
                return fields
            if register == 0xFF:
                fields.append(current)
                fields.extend([] for _ in range(value - 1))
                current = []
                continue
            if register & 0xF0 == 0x30:
                low = min(15, (value & 15) + atten)
                high = min(15, (value >> 4) + atten) if register >= 0x37 else value >> 4
                value = high << 4 | low
            current.append((register, value))

    def test_effects_play_their_scripts_quieter_with_distance(self):
        for effect in (SOUND_SCREAM, SOUND_SCREECH, SOUND_CLANG, SOUND_SPLASH, SOUND_BOOM):
            for atten in (0, 3):
                with self.subTest(effect=effect, atten=atten):
                    s = self.loaded()
                    pointer = s.word('g_FMScripts', 2 * effect)
                    script = bytes(s.machine.memory[pointer:pointer + 400])
                    want = self.expected(script, atten)
                    s.poke('g_SoundRequestAtten', atten)
                    s.poke('g_SoundRequest', effect)
                    got = [s.field() for _ in range(len(want) + 3)]
                    self.assertEqual(got, want + [[], [], []])
                    self.assertGreater(len(want), 10)

    def test_every_write_respects_the_chip_timing_and_the_budget(self):
        s = self.loaded()
        s.poke('g_TestPeriod', 400 & 255, 400 >> 8)
        s.poke('g_TestVolume', 64)
        s.call('Test_Engine')
        s.poke('g_SoundGun', 12)
        s.poke('g_SoundEngineVolume', 8)
        worst = 0
        for effect in (SOUND_CLANG, SOUND_BOOM, SOUND_SCREAM, SOUND_SPLASH, SOUND_SCREECH):
            s.poke('g_SoundRequest', effect)
            for _ in range(60):
                worst = max(worst, s.call('Sound_Field'))
        fm = [(port, t) for port, _, t in s.writes if port in (0x7C, 0x7D)]
        for (port, t), (next_port, next_t) in zip(fm, fm[1:]):
            if port == 0x7C:
                self.assertEqual(next_port, 0x7D)
                self.assertGreaterEqual(next_t - t, 12)
            else:
                self.assertGreaterEqual(next_t - t, 84)
        print(f'\nSound_Field with MSX-MUSIC: at most {worst} T-states per field')
        self.assertLess(worst, 3000)                      # docs/sound-budget.md


if __name__ == '__main__':
    unittest.main()
