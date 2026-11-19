"""Hand-written Z80 flight step (src/core/flight.c) against its C reference,
on an emulated Z80.

The step runs the original's tick (Flight_Tick, banked) on the first of every
12 steps and otherwise only moves the plane. Here Flight_Tick is a stub that
records its arguments, so the test checks the call and the per-step motion;
tests/test_flight_model.py covers the tick itself. Set
WINGS_FLIGHT_STEP_Z80_STEPS for a longer run.
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
STATE, XPTR, ARGS, STACK, SENTINEL = 0xD000, 0xD040, 0xD100, 0xF000, 0x3000
# Pass-through banked call and a Flight_Tick stub that records state, world, input.
STUB = """
    .module stub
    .globl ___sdcc_bcall_ehl, _Flight_Tick, b_Flight_Tick
    b_Flight_Tick = 0
    .area _CODE
___sdcc_bcall_ehl:
    jp (hl)
_Flight_Tick:
    ld hl, #2
    add hl, sp
    ld de, #0xD100
    ld bc, #5
    ldir
    ld hl, #0xD105
    inc (hl)
    ret
"""
NATIVE_STUB = """
#include <stdint.h>
uint8_t g_Args[6];
void Flight_Tick(void* state, uint16_t world, uint8_t input)
{
    (void)state; g_Args[2] = world & 255; g_Args[3] = world >> 8; g_Args[4] = input; ++g_Args[5];
}
"""
# SDCC FlightState layout (packed): see src/core/flight.h.
LAYOUT = [('x', 0, 2, False), ('y', 2, 4, False), ('vx', 6, 2, True), ('vy', 8, 2, True),
          ('frame', 10, 1, False), ('facing_left', 11, 1, False), ('mode', 12, 1, False),
          ('turn', 13, 1, False), ('turn_clock', 14, 1, False), ('step', 15, 1, False),
          ('landing', 16, 1, False), ('fast_roll', 17, 1, False), ('throttle', 18, 1, False),
          ('xrem', 19, 1, True), ('yrem', 20, 1, True), ('speed', 21, 2, True), ('climb', 23, 2, True),
          ('path', 25, 2, True), ('cancel', 27, 2, True), ('boost', 29, 2, True)]


class Flight(ctypes.Structure):
    _fields_ = [('x', ctypes.c_uint16), ('y', ctypes.c_uint32), ('vx', ctypes.c_int16), ('vy', ctypes.c_int16),
                ('frame', ctypes.c_uint8), ('facing_left', ctypes.c_uint8), ('mode', ctypes.c_uint8),
                ('turn', ctypes.c_uint8), ('turn_clock', ctypes.c_uint8), ('step', ctypes.c_uint8),
                ('landing', ctypes.c_uint8), ('fast_roll', ctypes.c_uint8), ('throttle', ctypes.c_uint8),
                ('xrem', ctypes.c_int8), ('yrem', ctypes.c_int8),
                ('speed', ctypes.c_int16), ('climb', ctypes.c_int16), ('path', ctypes.c_int16),
                ('cancel', ctypes.c_int16), ('boost', ctypes.c_int16)]


def pack(state):
    data = bytearray(31)
    for name, offset, size, signed in LAYOUT:
        data[offset:offset + size] = (getattr(state, name) % (1 << 8 * size)).to_bytes(size, 'little')
    return bytes(data)


def snapshot(state):
    return tuple(getattr(state, name) for name, *_ in LAYOUT)


def unpack(memory):
    out = []
    for name, offset, size, signed in LAYOUT:
        value = int.from_bytes(bytes(memory[STATE + offset:STATE + offset + size]), 'little')
        if signed and value >= 1 << (8 * size - 1):
            value -= 1 << 8 * size
        out.append(value)
    return tuple(out)


class Z80Step:
    def __init__(self, workdir):
        workdir.mkdir()
        sdcc = shutil.which('sdcc')
        for source in ('flight.c', 'flight_steps.c'):
            subprocess.run([sdcc, '-mz80', '--opt-code-speed', *DEFINES, '-I', str(ROOT / 'src/core'),
                            '-c', str(ROOT / 'src/core' / source), '-o', str(workdir) + '/'],
                           check=True, capture_output=True)
        (workdir / 'stub.s').write_text(STUB)
        subprocess.run([shutil.which('sdasz80'), '-o', 'stub.rel', 'stub.s'], cwd=workdir, check=True, capture_output=True)
        subprocess.run([sdcc, '-mz80', '--no-std-crt0', '--code-loc', '0x4000', '--data-loc', '0xC000',
                        'flight.rel', 'flight_steps.rel', 'stub.rel', '-o', 'flight.ihx'], cwd=workdir, check=True, capture_output=True)
        symbols = dict((n, int(a, 16)) for a, n in
                       re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)', (workdir / 'flight.map').read_text(), re.M))
        self.entry = symbols['_Flight_StepWorldSample']
        self.many_entry = symbols['_Flight_StepMany']
        self.machine = z80.Z80Machine()
        for line in (workdir / 'flight.ihx').read_text().split():
            count, address, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                self.machine.set_memory_block(address, bytes.fromhex(line[9:9 + 2 * count]))
        self.machine.set_memory_block(SENTINEL, b'\x76')
        self.machine.set_breakpoint(SENTINEL)
        self.ticks = {}

    def load(self, state, x):
        self.machine.set_memory_block(STATE, pack(state))
        self.machine.set_memory_block(XPTR, x.to_bytes(4, 'little'))
        self.machine.set_memory_block(ARGS, bytes(6))

    def step(self, input_):
        m = self.machine
        tick = m.memory[STATE + 15] == 0
        m.set_memory_block(STACK - 4, bytes([SENTINEL & 255, SENTINEL >> 8, input_, 1]))
        m.sp, m.pc, m.hl, m.de, m.ix, m.iy = STACK - 4, self.entry, STATE, XPTR, 0x1234, 0x5678
        budget = 100000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:
            assert not m.run() & m._TICKS_LIMIT_HIT, 'did not return'
        assert m.sp == STACK, 'callee did not remove its two argument bytes'
        assert m.ix == 0x1234 and m.iy == 0x5678, 'IX/IY not preserved'
        self.ticks.setdefault(tick, []).append(budget - m.ticks_to_stop)

    def many(self, n):
        """Flight_StepMany(state, x, n): sdcccall(1), n on the stack."""
        m = self.machine
        m.set_memory_block(STACK - 3, bytes([SENTINEL & 255, SENTINEL >> 8, n]))
        m.sp, m.pc, m.hl, m.de, m.ix, m.iy = STACK - 3, self.many_entry, STATE, XPTR, 0x1234, 0x5678
        budget = 100000
        m.ticks_to_stop = budget
        while m.pc != SENTINEL:
            assert not m.run() & m._TICKS_LIMIT_HIT, 'did not return'
        # SDCC C code keeps IX (its frame pointer); IY is the caller's to save.
        assert m.ix == 0x1234, 'IX not preserved'
        self.ticks.setdefault('many', []).append(budget - m.ticks_to_stop)
        return m.sp

    def x(self):
        return int.from_bytes(bytes(self.machine.memory[XPTR:XPTR + 4]), 'little')

    def args(self):
        return bytes(self.machine.memory[ARGS:ARGS + 6])


@unittest.skipUnless(z80 and shutil.which('sdcc') and shutil.which('sdasz80'), 'needs the z80 package and SDCC')
class FlightStepZ80Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        temp = Path(cls.temp.name)
        (temp / 'stub.c').write_text(NATIVE_STUB)
        library = temp / 'flight.so'
        subprocess.run([shutil.which('cc') or 'cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        *DEFINES, str(ROOT / 'src/core/flight.c'), str(ROOT / 'src/core/flight_steps.c'), str(temp / 'stub.c'), '-o', str(library)], check=True)
        cls.native = ctypes.CDLL(str(library))
        cls.asm = Z80Step(temp / 'asm')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_assembly_matches_c_reference(self):
        rng = random.Random(1)
        args = (ctypes.c_uint8 * 6).in_dll(self.native, 'g_Args')
        done, total = 0, int(os.environ.get('WINGS_FLIGHT_STEP_Z80_STEPS', 30000))
        while done < total:
            rem = lambda: rng.choice([0, rng.randrange(-11, 12)])
            state = Flight(x=rng.randrange(65536), y=rng.randrange(100 * 256, 1200 * 256),
                           vx=rng.randrange(-300, 301), vy=rng.randrange(-520, 521), step=rng.randrange(12),
                           xrem=rem(), yrem=rem(), speed=rng.randrange(1401), climb=rng.randrange(-4500, 3001),
                           mode=rng.randrange(3), facing_left=rng.randrange(2), turn=rng.randrange(26))
            x = rng.randrange(200 * 256, 7400 * 256)
            native_x = ctypes.c_uint32(x)
            self.asm.load(state, x)
            ctypes.memset(args, 0, 6)
            for _ in range(rng.choice([1, 12, 40])):
                input_ = rng.randrange(16)
                self.native.Flight_StepWorldSample(ctypes.byref(state), ctypes.byref(native_x), input_, 1)
                self.asm.step(input_)
                self.assertEqual(unpack(self.asm.machine.memory), snapshot(state), done)
                self.assertEqual(self.asm.x(), native_x.value, done)
                got = self.asm.args()
                self.assertEqual((got[2:6]), bytes(args)[2:6], done)
                if args[5]:
                    self.assertEqual(int.from_bytes(got[0:2], 'little'), STATE)
                done += 1
        print(f"\nZ80 flight step: {max(self.asm.ticks[False])} T-states per step, "
              f"{max(self.asm.ticks.get(True, [0]))} with the (stubbed) tick call")

    def test_many_steps_match_single_steps(self):
        """Flight_StepMany(n) (world_flight.c batches quiet steps with it)
        equals n single steps inside a tick, on the Z80 and natively."""
        rng = random.Random(2)
        for done in range(int(os.environ.get('WINGS_FLIGHT_STEP_Z80_STEPS', 30000)) // 3):
            rem = lambda: rng.choice([0, rng.randrange(-11, 12)])
            c = rng.randrange(1, 12)
            n = rng.randrange(1, 13 - c)
            fields = dict(x=rng.randrange(65536), y=rng.randrange(100 * 256, 1200 * 256),
                          vx=rng.randrange(-300, 301), vy=rng.randrange(-520, 521), step=c,
                          xrem=rem(), yrem=rem(), speed=rng.randrange(1401), mode=rng.randrange(3))
            x = rng.randrange(200 * 256, 7400 * 256)
            single, batched = Flight(**fields), Flight(**fields)
            single_x, batched_x = ctypes.c_uint32(x), ctypes.c_uint32(x)
            for _ in range(n):
                self.native.Flight_StepWorldSample(ctypes.byref(single), ctypes.byref(single_x), 0, 0)
            self.native.Flight_StepMany(ctypes.byref(batched), ctypes.byref(batched_x), n)
            self.assertEqual(snapshot(batched), snapshot(single), (done, c, n))
            self.assertEqual(batched_x.value, single_x.value, (done, c, n))
            self.asm.load(Flight(**fields), x)
            sp = self.asm.many(n)
            self.assertEqual(unpack(self.asm.machine.memory), snapshot(single), (done, c, n))
            self.assertEqual(self.asm.x(), single_x.value, (done, c, n))
        self.sp_after_many = sp
        print(f"\nFlight_StepMany: up to {max(self.asm.ticks['many'])} T-states for up to 11 steps")


if __name__ == '__main__':
    unittest.main()
