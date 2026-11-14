"""Hand-written Z80 flight step against the C reference, on an emulated Z80.

Builds src/core/flight.c twice with SDCC (the Z80 assembly variant and the
C variant via WINGS_FLIGHT_C), runs each on the `z80` package emulator and
compares every FlightState field and the world x after each step with the
native C reference. Set WINGS_FLIGHT_Z80_STEPS for a longer run.
"""
import ctypes
import os
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
DEFINES = ['-DWINGS_P1_FLIGHT', '-DMISSION_TERRAIN', '-DWINGS_FLIGHT_MAX_Y=1200u',
           '-DWINGS_WORLD_WIDTH=7608u', '-DWINGS_WORLD_START=7032u']
FIELDS = [('x', ctypes.c_uint16), ('y', ctypes.c_uint32), ('vx', ctypes.c_int16), ('vy', ctypes.c_int16),
          ('frame', ctypes.c_uint8), ('facing_left', ctypes.c_uint8), ('mode', ctypes.c_uint8),
          ('turn_ticks', ctypes.c_uint8), ('target_left', ctypes.c_uint8), ('ground_tick', ctypes.c_uint8)]
STATE, XPTR, STACK, SENTINEL = 0xD000, 0xD020, 0xF000, 0x3000


class Flight(ctypes.Structure):
    _fields_ = FIELDS


def pack(state, x):
    data = bytearray(16)
    data[0:2] = state.x.to_bytes(2, 'little')
    data[2:6] = state.y.to_bytes(4, 'little')
    data[6:8] = (state.vx & 0xFFFF).to_bytes(2, 'little')
    data[8:10] = (state.vy & 0xFFFF).to_bytes(2, 'little')
    data[10:16] = bytes([state.frame, state.facing_left, state.mode, state.turn_ticks,
                         state.target_left, state.ground_tick])
    return bytes(data), x.to_bytes(4, 'little')


def snapshot(state, x):
    return tuple(getattr(state, name) for name, _ in FIELDS) + (x,)


def unpack(memory):
    def signed(value):
        return value - 65536 if value >= 32768 else value
    m = bytes(memory[STATE:STATE + 16])
    return (int.from_bytes(m[0:2], 'little'), int.from_bytes(m[2:6], 'little'),
            signed(int.from_bytes(m[6:8], 'little')), signed(int.from_bytes(m[8:10], 'little')),
            *m[10:16], int.from_bytes(bytes(memory[XPTR:XPTR + 4]), 'little'))


class Z80Flight:
    """One SDCC build of flight.c loaded into an emulated Z80."""

    def __init__(self, workdir, extra, keeps_iy):
        self.keeps_iy = keeps_iy  # SDCC treats IY as caller-saved; the assembly keeps it anyway
        workdir.mkdir()
        sdcc = shutil.which('sdcc')
        subprocess.run([sdcc, '-mz80', '--opt-code-speed', *DEFINES, *extra, '-I', str(ROOT / 'src/core'),
                        '-c', str(ROOT / 'src/core/flight.c'), '-o', str(workdir) + '/'],
                       check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'flight.rel', '-o', 'flight.ihx'], cwd=workdir, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (workdir / 'flight.map').read_text(), re.M))
        self.entry = symbols['_Flight_StepWorldSample']
        self.machine = z80.Z80Machine()
        for line in (workdir / 'flight.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                self.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        self.machine.set_memory_block(SENTINEL, b'\x76')
        self.machine.set_breakpoint(SENTINEL)
        self.ticks = self.calls = 0

    def step(self, input_, sample):
        m = self.machine
        m.set_memory_block(STACK - 4, bytes([SENTINEL & 255, SENTINEL >> 8, input_, sample]))
        m.sp, m.pc, m.hl, m.de, m.ix, m.iy = STACK - 4, self.entry, STATE, XPTR, 0x1234, 0x5678
        budget = 100000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:  # run() also returns at emulated frame boundaries
            assert not m.run() & m._TICKS_LIMIT_HIT, 'did not return'
        assert m.sp == STACK, 'callee did not remove its two argument bytes'
        assert m.ix == 0x1234, 'IX (SDCC frame pointer) not preserved'
        assert not self.keeps_iy or m.iy == 0x5678, 'IY not preserved'
        self.ticks += budget - m.ticks_to_stop
        self.calls += 1

    def load(self, state, x):
        data, xdata = pack(state, x)
        self.machine.set_memory_block(STATE, data)
        self.machine.set_memory_block(XPTR, xdata)


@unittest.skipUnless(z80 and shutil.which('sdcc'), 'needs the z80 package and SDCC')
class FlightZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        temp = Path(cls.temp.name)
        library = temp / 'flight.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        *DEFINES, str(ROOT / 'src/core/flight.c'), '-o', str(library)], check=True)
        cls.native = ctypes.CDLL(str(library))
        cls.asm = Z80Flight(temp / 'asm', [], True)
        cls.c = Z80Flight(temp / 'c', ['-DWINGS_FLIGHT_C'], False)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_random(self, targets, steps, seed):
        rng = random.Random(seed)
        done = 0
        while done < steps:
            state = Flight(
                x=rng.randrange(65536),
                y=rng.choice([0, 1, 255, rng.randrange(1200 * 256 + 1), 1200 * 256, 1200 * 256 - 1, 1160 * 256]),
                vx=rng.randrange(-260, 261), vy=rng.randrange(-200, 201), frame=rng.randrange(3),
                facing_left=rng.randrange(2), mode=rng.randrange(4),
                turn_ticks=rng.choice([0, 0, 1, 2, rng.randrange(256)]), target_left=rng.randrange(2),
                ground_tick=rng.randrange(6))
            x = rng.choice([0, 256, 6593 * 256 + rng.randrange(-5000, 5000) * 256,
                            rng.randrange(7608 * 256), 7607 * 256, 6657 * 256, 6658 * 256 - 1])
            native_x = ctypes.c_uint32(x)
            for target in targets:
                target.load(state, x)
            hold = rng.randrange(16)
            for step in range(rng.choice([1, 10, 200, 600])):
                if rng.random() < 0.05:
                    hold = rng.randrange(16)
                input_ = hold if rng.random() < 0.9 else rng.randrange(16)
                self.native.Flight_StepWorldSample(ctypes.byref(state), ctypes.byref(native_x), input_, step & 1)
                expected = snapshot(state, native_x.value)
                for target in targets:
                    target.step(input_, step & 1)
                    self.assertEqual(unpack(target.machine.memory), expected, (seed, done, input_))
                done += 1

    def test_assembly_matches_c_reference(self):
        self.run_random([self.asm], int(os.environ.get('WINGS_FLIGHT_Z80_STEPS', 150000)), 1)

    def test_sdcc_compiled_c_matches_native(self):
        self.run_random([self.c], 20000, 2)

    def test_takeoff_climb_dive_and_turns(self):
        # Deterministic: leftward deck takeoff at full power (lifts off at
        # step 769 from x=6860), climb into the top limit, stall, dive into
        # the sea limit, reverse twice and coast.
        state = Flight(x=0, y=1160 * 256, vx=0, vy=0, frame=1, facing_left=1, mode=0,
                       turn_ticks=0, target_left=1, ground_tick=0)
        native_x = ctypes.c_uint32(6860 * 256)
        self.asm.load(state, native_x.value)
        script = [8 | 1] * 3000 + [1] * 600 + [4] * 3000 + [2] * 400 + [8 | 4] * 400 + [0] * 300
        modes = set()
        for input_ in script:
            self.native.Flight_StepWorldSample(ctypes.byref(state), ctypes.byref(native_x), input_, 0)
            self.asm.step(input_, 0)
            self.assertEqual(unpack(self.asm.machine.memory), snapshot(state, native_x.value))
            modes.add(state.mode)
        self.assertEqual(modes, {0, 1, 2, 3})

    def test_assembly_is_faster(self):
        self.asm.ticks = self.asm.calls = self.c.ticks = self.c.calls = 0
        self.run_random([self.asm, self.c], 3000, 3)
        asm, c = self.asm.ticks / self.asm.calls, self.c.ticks / self.c.calls
        # Plain Z80 T-states per step (MSX adds an M1 wait per opcode fetch).
        # Measured 2026-11-14: ~1,600 assembly vs ~3,700 SDCC-compiled C.
        self.assertLess(asm, 1800, asm)
        self.assertLess(asm * 2, c, (asm, c))


if __name__ == '__main__':
    unittest.main()
