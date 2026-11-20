"""The music's byte streams (tools/convert_music.py, docs/music.md) read
back as the player reads them (src/msx/music.c) give the decoded songs'
notes (tools/decode_songs.py): their starts, pitches, gates and
instruments, and every track's loop."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


def play(stream):
    """The notes a track's stream starts, as the player's Read does:
    (tick, pitch, gate, instrument index, attenuation)."""
    notes, tick, i, inst, att = [], 0, 0, 0, 0
    def number():
        nonlocal i
        b = stream[i]; i += 1
        if b: return b
        v = stream[i] | stream[i + 1] << 8; i += 2
        return v
    while stream[i] != 0xFF:
        c = stream[i]; i += 1
        if c >= 0xA0: tick += number()
        elif c >= 0x90: att = c & 15
        elif c >= 0x80: inst = c & 15
        else:
            gate, wait = number(), number()
            notes.append((tick, c, gate, inst, att))
            tick += wait
    return notes, tick


class MusicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from decode_songs import Module, decode, SOURCE
        import convert_music
        cls.convert = convert_music
        module = Module((SOURCE / 'wofsongs').read_bytes(), (SOURCE / 'songplay').read_bytes())
        cls.songs = {s: decode(module, s) for s in convert_music.SONGS}

    def test_generated_files_are_current(self):
        for path, text in self.convert.artifacts().items():
            self.assertEqual(path.read_text(), text, path)

    def test_streams_replay_the_decoded_notes(self):
        for song, r in self.songs.items():
            loop = r['loop_ticks'][0]
            instruments = {}
            for t in range(4):
                stream = self.convert.track_stream(r['events'][t], song, t, loop, instruments)
                notes, length = play(stream)
                self.assertEqual(length, loop, (song, t))   # the track loops with the song
                want = [e for e in r['events'][t] if e['type'] == 'note']
                self.assertEqual(len(notes), len(want), (song, t))
                for (tick, pitch, gate, inst, att), e in zip(notes, want):
                    self.assertEqual(tick, e['tick'])
                    if e['midi'] is not None: self.assertEqual(pitch, round(e['midi']))
                    self.assertLessEqual(abs(tick + gate - e['end_tick']), 1, (song, t, tick))
                    name = next(n for (tt, n), (k, _) in instruments.items() if tt == t and k == inst)
                    self.assertEqual(name, e['instrument'])
                    self.assertEqual(att, self.convert.attenuation(e['volume']))

    def test_every_note_fits_the_pitch_tables(self):
        psg, fm = self.convert.tables()
        for k, period in enumerate(psg):
            self.assertTrue(1 <= period <= 4095, k)
        for k, v in enumerate(fm):
            block, fnum = v >> 9, v & 511
            f = fnum * self.convert.OPLL_RATE / 2 ** (19 - block)
            want = 440 * 2 ** ((self.convert.MIDI_LOW + k - 69) / 12)
            self.assertLess(abs(1200 * __import__('math').log2(f / want)), 10, k)   # within 10 cents

    def test_the_tempo_follows_the_original_on_both_field_rates(self):
        for song, r in self.songs.items():
            tick = r['tick_s']
            for rate, field in ((50, 1 / 50), (60, 1001 / 60000)):
                ticks = round(256 * field / tick) / 256 / field
                self.assertLess(abs(ticks * tick - 1), 0.005, (song, rate))   # within 0.5%


if __name__ == '__main__':
    unittest.main()
