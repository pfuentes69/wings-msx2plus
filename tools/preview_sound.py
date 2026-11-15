"""Render the MSX PSG sound effects to WAV files for listening on the host.

Reads the effect steps from src/msx/sound_update.c and plays them through
a model of src/msx/sound.c (one step per 60 Hz field) and of the AY-3-8910:
square tones at clock / (16 * period), the 17-bit noise generator, the
mixer (tone AND noise), and the logarithmic volume table. Also renders the
engine in its four modes, the cannon and dugout-gun rattles and the lift's
grind. A preview, not a cycle-exact emulation.

    python3 tools/preview_sound.py OUTPUT_DIRECTORY
"""
import argparse
import re
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOCK = 3579545 / 2          # PSG clock on the MSX
RATE = 44100
FIELD = 60
NAMES = ['scream', 'screech', 'clang', 'splash', 'boom']
# AY volume levels (normalized), 0..15.
LEVELS = [0, 0.0106, 0.0150, 0.0222, 0.0320, 0.0466, 0.0665, 0.1039,
          0.1237, 0.1986, 0.2803, 0.3548, 0.4702, 0.6030, 0.7530, 1.0]


def steps():
    """The effects' steps as (fields, volume, dvolume, mix, tone, dtone)."""
    source = (ROOT / 'src/msx/sound_update.c').read_text()
    table = source[source.index('s_Steps[] = {'):source.index('};', source.index('s_Steps[] = {'))]
    table = re.sub(r'/\*.*?\*/', '', table, flags=re.S)
    effects, current = [], []
    for item in re.findall(r'\{([^{}]*)\}|END', table.split('{', 1)[1]):
        if not item:
            effects.append(current); current = []
            continue
        fields = [eval(v.replace('T', '1').replace('N(', '(lambda p: 2 | p << 2)('), {}) for v in item.split(',')]
        current.append(tuple(fields))
    return effects


class Psg:
    def __init__(self):
        self.regs = [0] * 16
        self.phase = [0.0] * 3
        self.level = [1] * 3
        self.noise_phase = 0.0
        self.lfsr = 1
        self.noise = 1

    def render(self, samples):
        out = []
        r = self.regs
        tones = [max(1, r[2 * c] | (r[2 * c + 1] & 15) << 8) for c in range(3)]
        noise_period = max(1, r[6] & 31)
        for _ in range(samples):
            for c in range(3):
                self.phase[c] += CLOCK / (16 * tones[c]) / RATE * 2
                while self.phase[c] >= 1:
                    self.phase[c] -= 1
                    self.level[c] ^= 1
            self.noise_phase += CLOCK / (16 * noise_period) / RATE
            while self.noise_phase >= 1:
                self.noise_phase -= 1
                bit = (self.lfsr ^ (self.lfsr >> 3)) & 1
                self.lfsr = (self.lfsr >> 1) | (bit << 16)
                self.noise = self.lfsr & 1
            value = 0.0
            for c in range(3):
                tone_on = not r[7] >> c & 1
                noise_on = not r[7] >> (c + 3) & 1
                bit = (self.level[c] if tone_on else 1) & (self.noise if noise_on else 1)
                value += LEVELS[r[8 + c] & 15] * bit
            out.append(value / 3)
        return out


def play(fields):
    """fields: a list of register-setting functions, one per field."""
    psg, audio = Psg(), []
    for set_regs in fields:
        set_regs(psg.regs)
        audio += psg.render(RATE // FIELD)
    return audio


def effect_fields(effect):
    fields, volume, tone, index = [], 0, 0, 0
    left = 0
    def start(i):
        nonlocal left, volume, tone
        left, volume, _, _, tone, _ = effect[i]
    start(0)
    while index < len(effect):
        step = effect[index]
        v, t, mix = volume >> 4, tone, step[3]
        def regs(r, v=v, t=t, mix=mix):
            mixer = 0x3f
            if mix & 1: mixer &= ~0x04
            if mix & 2: mixer &= ~0x20; r[6] = mix >> 2
            r[4], r[5], r[10], r[7] = t & 255, t >> 8 & 15, v, 0x80 | mixer
        fields.append(regs)
        volume = max(0, min(255, volume + step[2]))
        tone = (tone + step[5]) & 0xffff
        left -= 1
        if not left:
            index += 1
            if index < len(effect): start(index)
    return fields + [lambda r: r.__setitem__(10, 0)] * 10


def engine_fields(period, volume64, seconds=1.5):
    tone = (period << 1) + (period >> 2)
    volume = volume64 * 11 >> 6
    def regs_for(n):
        t = tone + (tone >> 5 if n & 1 else 0)
        def regs(r):
            r[0], r[1], r[8], r[7] = t & 255, t >> 8, volume, 0x80 | 0x3e
        return regs
    return [regs_for(n) for n in range(int(seconds * FIELD))]


def gun_fields(volume, rate, seconds=1.5):
    def regs_for(n):
        phase = n % rate
        v = volume if phase == 0 else max(volume - 3, 0) if phase == 1 else max(volume - 7, 0) if phase == 2 else 0
        def regs(r):
            r[6], r[9], r[7] = 1, v, 0x80 | 0x2f
        return regs
    return [regs_for(n) for n in range(int(seconds * FIELD))]


def grind_fields(seconds=2):
    def regs_for(n):
        def regs(r):
            r[2], r[3], r[6], r[9], r[7] = 1200 & 255, 1200 >> 8, 20, 10 if n & 7 < 4 else 6, 0x80 | 0x2d
        return regs
    return [regs_for(n) for n in range(int(seconds * FIELD))]


def write(path, audio):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, v * 1.6 - 0.3)) * 32000)) for v in audio))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    renders = {f'effect-{name}': effect_fields(e) for name, e in zip(NAMES, steps())}
    for name, period, volume in (('throttle', 335, 64), ('glide', 385, 49), ('deck-idle', 808, 40), ('failed', 960, 25)):
        renders[f'engine-{name}'] = engine_fields(period, volume)
    renders['gun-cannon'] = gun_fields(12, 6)
    renders['gun-dugout'] = gun_fields(7, 10)
    renders['lift-grind'] = grind_fields()
    for name, fields in renders.items():
        write(args.output / f'{name}.wav', play(fields))
        print(args.output / f'{name}.wav')


if __name__ == '__main__':
    main()
