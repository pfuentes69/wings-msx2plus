"""The original's music for the MSX (docs/music.md), from the decoded songs
(tools/decode_songs.py, docs/research/amiga-music.md).

  python tools/convert_music.py          # src/generated/music_data.c/.h, assets_msx/music/*.txt
  python tools/convert_music.py --check  # compare with what is generated

Each song keeps the original's four tracks. A track is a byte stream:
  0x00..0x7F  a note, its sounding MIDI pitch; then its gate (ticks it
              sounds) and the ticks to the next command, each one byte
              1..255, or 0 and two bytes (little-endian)
  0x80 + i    the following notes use the song's instrument i
  0x90 + a    their attenuation a (0..15, 3 dB a step)
  0xA0        a rest: the ticks to the next command, as above
  0xFF        the end: the track starts again (every track loops with the
              song, all four the same length)
An instrument says how a track plays on MSX-MUSIC (a preset on the
track's own FM channel, or a rhythm drum) and on the PSG alone (a channel,
or none; a drum's kind), with an octave shift for each.
"""
import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
OUT_C = ROOT / 'src/generated/music_data.c'
OUT_H = ROOT / 'src/generated/music_data.h'
OUT_TXT = ROOT / 'assets_msx/music'
SONGS = (0, 1, 2, 4)          # subsong 3 is subsong 1
PSG_CLOCK = 3579545 / 2       # AY-3-8910 at 1.79 MHz: f = clock / (16 * period)
OPLL_RATE = 3579545 / 72      # YM2413: f = fnum * rate / 2 ** (19 - block)
MIDI_LOW, MIDI_HIGH = 12, 107
# OPLL presets.
VIOLIN, GUITAR, PIANO, FLUTE, CLARINET, OBOE, TRUMPET, ORGAN, HORN, SYNTH, HARPSICHORD, VIBES, SYNTH_BASS, BASS, EGUITAR = range(1, 16)
# Rhythm-mode drums (register 0x0E bits) and the PSG's drum kinds.
BD, SD, TOM, CYM, HH = 0x10, 0x08, 0x04, 0x02, 0x01
KICK, SNARE, METAL = 0, 1, 2
NONE = 255
# Per song and track: how each of its instruments plays. Melodic:
# (kind 0, FM preset, FM shift, PSG channel, PSG shift); drums: (kind 1,
# rhythm bit, 0, PSG channel, PSG drum kind). The PSG has three channels:
# the drums take over theirs while a hit sounds.
ARRANGEMENT = {
    0: {0: {'RoomBrass2.iff': (0, TRUMPET, 0, 0, 0)},
        1: {'RoomBrass2.iff': (0, HORN, 0, 2, 0)},
        2: {'SyntheBass.iff': (0, SYNTH_BASS, 12, 1, 12)},
        3: {'BassDrum3': (1, BD, 0, 2, KICK), 'sdrum1.iff': (1, SD, 0, 2, SNARE)}},
    1: {0: {'RoomBrass2.iff': (0, TRUMPET, 0, 0, 0)},
        1: {'RoomBrass2.iff': (0, HORN, 0, 2, 0)},
        2: {'SyntheBass.iff': (0, SYNTH_BASS, 12, 1, 12)},
        3: {'BassDrum3': (1, BD, 0, 2, KICK), 'sdrum1.iff': (1, SD, 0, 2, SNARE)}},
    # The drone: C2 and C1 on organs; the original's C0 (16 Hz) an octave
    # up on FM, left out on the PSG; the fanfare on a trumpet.
    2: {0: {'omlead.iff': (0, ORGAN, 0, 0, 0)},
        1: {'omlead.iff': (0, ORGAN, 0, 1, 0)},
        2: {'omlead.iff': (0, SYNTH, 12, NONE, 0), 'Mechanic1.iff': (1, CYM, 0, 2, METAL),
            'sdrum1.iff': (1, TOM, 0, 2, SNARE)},
        3: {'RoomBrass2.iff': (0, TRUMPET, 0, 2, 0)}},
    4: {0: {'omlead.iff': (0, ORGAN, 0, 0, 0)},
        1: {'omlead.iff': (0, ORGAN, 0, 1, 0)},
        2: {'omlead.iff': (0, SYNTH, 12, NONE, 0)},
        3: {'sdrum1.iff': (1, SD, 0, 2, SNARE)}},
}


def attenuation(volume):
    """Paula volume 0..64 as 3 dB steps (0 loudest, 15 silent)."""
    if volume <= 0: return 15
    return min(15, round(-20 * math.log10(volume / 64) / 3))


def number(value):
    return bytes([value]) if 1 <= value <= 255 else bytes([0, value & 255, value >> 8])


def track_stream(events, song, track, loop, instruments):
    """A track's byte stream from its decoded notes (ticks from 0)."""
    out, at, inst, att = bytearray(), 0, None, None
    notes = [e for e in events if e['type'] == 'note']
    for i, e in enumerate(notes):
        start, end = e['tick'], e['end_tick']
        if start > at:
            out += b'\xa0' + number(start - at)
            at = start
        arrangement = ARRANGEMENT[song][track][e['instrument']]
        key = (track, e['instrument'])
        if key not in instruments: instruments[key] = (len(instruments), arrangement)
        index = instruments[key][0]
        if index != inst: out.append(0x80 + index); inst = index
        a = attenuation(e['volume'])
        if a != att: out.append(0x90 + a); att = a
        nxt = notes[i + 1]['tick'] if i + 1 < len(notes) else loop
        pitch = round(e['midi']) if e['midi'] is not None else 60   # drums: unpitched
        gate = max(1, min(round(end) - start, nxt - start))
        assert 0 <= pitch < 128 and nxt > start
        out.append(pitch); out += number(gate) + number(nxt - start)
        at = nxt
    if at < loop:
        out += b'\xa0' + number(loop - at)
    out.append(0xFF)
    return bytes(out)


def tables():
    """The PSG tone periods and the OPLL (block << 9 | fnum) for MIDI_LOW..MIDI_HIGH."""
    psg, fm = [], []
    for n in range(MIDI_LOW, MIDI_HIGH + 1):
        f = 440 * 2 ** ((n - 69) / 12)
        psg.append(min(4095, round(PSG_CLOCK / (16 * f))))
        for block in range(8):
            fnum = round(f * 2 ** (19 - block) / OPLL_RATE)
            if fnum < 512: break
        fm.append(block << 9 | fnum)
    return psg, fm


def artifacts():
    from decode_songs import Module, decode, SOURCE
    module = Module((SOURCE / 'wofsongs').read_bytes(), (SOURCE / 'songplay').read_bytes())
    c = ['/* Generated by tools/convert_music.py; do not edit. */',
         '#include "../msx/banking.h"', '#include "music_data.h"', 'WINGS_CODE_SEGMENT(WINGS_SEGMENT_MUSIC)']
    h = ['/* Generated by tools/convert_music.py; do not edit. */', '#pragma once',
         f'#define MUSIC_SONGS {len(SONGS)}', f'#define MUSIC_MIDI_LOW {MIDI_LOW}', f'#define MUSIC_MIDI_HIGH {MIDI_HIGH}',
         '/* An instrument: kind (0 melodic, 1 drum), FM preset or rhythm bit, FM shift,',
         ' * PSG channel (255 none), PSG shift or drum kind. */',
         'typedef struct MusicInstrument { unsigned char kind, fm; signed char fm_shift; unsigned char psg, psg_arg; } MusicInstrument;',
         '/* A song: its tracks, instruments, and the ticks a field (256ths) on PAL and NTSC. */',
         'typedef struct MusicSong { const unsigned char* track[4]; const MusicInstrument* instrument; unsigned char rate_pal, rate_ntsc; } MusicSong;',
         'extern const MusicSong g_MusicSongs[MUSIC_SONGS];',
         'extern const unsigned short g_MusicPSG[MUSIC_MIDI_HIGH - MUSIC_MIDI_LOW + 1];',
         'extern const unsigned short g_MusicFM[MUSIC_MIDI_HIGH - MUSIC_MIDI_LOW + 1];',
         '/* The subsongs, by their index in g_MusicSongs. */']
    texts, songs, total = {}, [], 0
    for k, song in enumerate(SONGS):
        r = decode(module, song)
        loop = r['loop_ticks'][0]
        assert all(t == loop for t in r['loop_ticks']), r['loop_ticks']
        instruments = {}
        streams = [track_stream(r['events'][t], song, t, loop, instruments) for t in range(4)]
        for t, s in enumerate(streams):
            c.append(f'static const unsigned char s_Song{song}Track{t}[{len(s)}] = {{{", ".join(str(b) for b in s)}}};')
            total += len(s)
        entries = sorted(instruments.values())
        c.append(f'static const MusicInstrument s_Song{song}Instruments[{len(entries)}] = {{' +
                 ', '.join('{%d, %d, %d, %d, %d}' % a for _, a in entries) + '};')
        tick = r['tick_s']
        songs.append(f'{{{{s_Song{song}Track0, s_Song{song}Track1, s_Song{song}Track2, s_Song{song}Track3}}, '
                     f's_Song{song}Instruments, {round(256 * 0.02 / tick)}, {round(256 * 1001 / 60000 / tick)}}}')
        h.append(f'#define MUSIC_SUBSONG_{song} {k}')
        texts[OUT_TXT / f'song{song}.txt'] = (f'subsong {song}: loop {loop} ticks, tick {tick * 1000:.3f} ms, '
            f'{sum(len(s) for s in streams)} bytes\n' + ''.join(f'track {t}: {s.hex()}\n' for t, s in enumerate(streams)))
    c.append(f'const MusicSong g_MusicSongs[{len(SONGS)}] = {{' + ', '.join(songs) + '};')
    psg, fm = tables()
    c.append('/* Tone periods (PSG) and block << 9 | fnum (OPLL) from MIDI note MUSIC_MIDI_LOW. */')
    c.append(f'const unsigned short g_MusicPSG[{len(psg)}] = {{{", ".join(map(str, psg))}}};')
    c.append(f'const unsigned short g_MusicFM[{len(fm)}] = {{{", ".join(map(str, fm))}}};')
    h.append(f'/* {total} bytes of tracks. */')
    texts[OUT_C] = '\n'.join(c) + '\n'
    texts[OUT_H] = '\n'.join(h) + '\n'
    return texts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path, text in artifacts().items():
        if args.check:
            assert path.read_text() == text, f'{path} is out of date'
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


if __name__ == '__main__':
    main()
