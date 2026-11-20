"""Decode the Amiga Wings of Fury music (Kris Hatlelid replayer) into note events.

Reads the two original files, `wofsongs` (song data and six 8SVX instruments)
and `songplay` (the replayer), and replays the song data with the replayer's
own state machine (songplay CODE 0x4f4..0x846), one CIA-A timer tick at a
time. Nothing is executed or relocated; the tables (periods, durations) are
read from songplay's DATA hunk at the addresses its code uses.

See docs/research/amiga-music.md for the format and the evidence.

    python3 tools/decode_songs.py --summary
    python3 tools/decode_songs.py --song 4             # event listing
    python3 tools/decode_songs.py --json OUT.json      # all songs, all events
    python3 tools/decode_songs.py --midi               # assets_src/audio/music/song<N>.mid
"""
import argparse
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_audio import read_hunks, read_8svx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'reference_assets/original_files/Wings_of_Fury'
MUSIC_OUT = ROOT / 'assets_src/audio/music'

PAULA_PAL = 3546895      # Paula clock (period -> sample rate), PAL
PAULA_NTSC = 3579545
ECLOCK_PAL = 709379      # CIA E clock (timer ticks), PAL
ECLOCK_NTSC = 715909
UNIQUE_SONGS = (0, 1, 2, 4)   # subsong 3 is song2 again (same pointer as 1)

# songplay CODE bytes the decoder relies on (offset: hex). Checked on load.
REPLAYER_GUARDS = {
    0x5e8: 'b27c00d96c2a',                 # cmp.w #$d9,d1 ; bge  (>= 0xd9: command)
    0x5ee: '08010007',                     # btst #7,d1 (tie flag)
    0x606: 'c27c007fd2700004',             # and.w #$7f,d1 ; add.w 4(a0,d0.w),d1 (transpose)
    0x6aa: '13c200bfe501',                 # 0xdd: move.b d2,$bfe501 (CIA-A TAHI)
    0x6c2: '13c200bfe401',                 # 0xde: move.b d2,$bfe401 (CIA-A TALO)
    0x708: '43f9',                         # lea durations,a1
    0x80a: '927c001be549',                 # sub.w #$1b,d1 ; lsl.w #2,d1
    0x810: '43f9',                         # lea periods,a1
    0x81a: '242a0008e7aa82c2',             # move.l 8(a2),d2 (samplesPerHiCycle) ; lsl.l d3,d2 ; divu d2,d1
    0x382: '33fc0020',                     # initial track volume 32
    0x986: '7253',                         # notes per octave = 83 / ctOctave
}

# True waveform cycle (samples) of each pitched instrument, measured by
# autocorrelation of its sample data (peaks at k x cycle, k = 1..6). The
# VHDR's samplesPerHiCycle, which the replayer uses, is 4, 16 and 8 times
# smaller, so every note sounds 2, 4 or 3 octaves below the replayer's
# nominal pitch. Unpitched instruments have no entry.
TRUE_CYCLE = {'RoomBrass2.iff': 31.85, 'SyntheBass.iff': 128.9, 'omlead.iff': 129.3}

# General MIDI rendering of each instrument (for listening only).
GM_PROGRAM = {'RoomBrass2.iff': 61, 'SyntheBass.iff': 38, 'omlead.iff': 80}   # 0-based programs
GM_DRUM = {'BassDrum3': 36, 'sdrum1.iff': 38, 'Mechanic1.iff': 39}           # kick, snare, hand clap
ROLE = {'RoomBrass2.iff': 'brass (melodic)', 'SyntheBass.iff': 'bass', 'omlead.iff': 'drone',
        'BassDrum3': 'bass drum', 'sdrum1.iff': 'snare drum', 'Mechanic1.iff': 'metallic percussion'}

NOTE_NAMES = 'C C# D D# E F F# G G# A A# B'.split()


def note_name(midi):
    return f'{NOTE_NAMES[midi % 12]}{midi // 12 - 1}'


def u32(b, o):
    return struct.unpack('>I', b[o:o + 4])[0]


def u16(b, o):
    return struct.unpack('>H', b[o:o + 2])[0]


class Module:
    """The song data, instruments and replayer tables."""

    def __init__(self, wofsongs, songplay):
        self.wofsongs_bytes, self.songplay_bytes = wofsongs, songplay
        sp = read_hunks(songplay)
        code, self.spdata = sp[0]['payload'], sp[1]['payload']
        for off, hexbytes in REPLAYER_GUARDS.items():
            if code[off:off + len(hexbytes) // 2].hex() != hexbytes:
                raise ValueError(f'songplay CODE 0x{off:x} differs from the decoded replayer')
        self.duration_base = u32(code, 0x70a)        # $254
        self.period_base = u32(code, 0x812)          # $134, entry for note 0x1b
        # durations: 20 byte pairs (length in ticks, gate in ticks)
        self.durations = []
        o = self.duration_base
        while o + 1 < len(self.spdata) and self.spdata[o]:
            self.durations.append((self.spdata[o], self.spdata[o + 1]))
            o += 2
        # period table: longwords; the replayer reads base + 4 * (note - 0x1b)
        first = self.period_base - 4 * 0x1b
        while first >= 4 and u32(self.spdata, first - 4):
            first -= 4
        self.table_first_note = (first - self.period_base) // 4 + 0x1b    # note number of the first entry
        self.periods = []
        o = first
        while o < self.duration_base:
            self.periods.append(u32(self.spdata, o))
            o += 4
        # The table is NTSC-Paula-clock / frequency of MIDI note (index): entry 0 is MIDI 0.
        self.midi_offset = -self.table_first_note
        assert abs(PAULA_NTSC / self.periods[0] - 440 * 2 ** ((0 - 69) / 12)) < 0.01

        ws = read_hunks(wofsongs)
        self.data, self.symbols = ws[1]['payload'], ws[1]['symbols']
        self.song_ptrs = [u32(self.data, 4 * i) for i in range(5)]
        self.song_names = {v: k for k, v in self.symbols.items() if k.startswith('song') and k != 'songs'}
        self.instruments = {}            # 8SVX data offset -> info (+pcm)
        self.voices = {}                 # voice struct offset -> info
        for so in set(self.song_ptrs):
            for idx in range(1, 64):
                vo = u32(self.data, so + 0x10 + 4 * idx)
                if vo == 0:
                    break
                self.voice(vo)
            self.voice(u32(self.data, so + 0x10))

    def voice(self, vo):
        if vo in self.voices:
            return self.voices[vo]
        d = self.data
        name = {v: k for k, v in self.symbols.items()}.get(vo, f'voice@{vo:x}')
        svx = u32(d, vo + 0xa)
        inst = None
        if svx:
            if svx not in self.instruments:
                size = u32(d, svx + 4) + 8
                pcm, info = read_8svx(d[svx:svx + size])
                info['pcm'] = pcm
                info['data_offset'] = svx
                self.instruments[svx] = info
            inst = self.instruments[svx]
        v = dict(offset=vo, name=name, instrument=inst,
                 vib_upper=u16(d, vo + 0x12), vib_lower=u16(d, vo + 0x14), vib_step=struct.unpack('>h', d[vo + 0x16:vo + 0x18])[0],
                 vib_speed=u16(d, vo + 0x18), vib_delay=u16(d, vo + 0x1a), vibrato=u16(d, vo + 0x1e) != 0,
                 arpeggio=u16(d, vo + 0x22) != 0, arp_steps=[struct.unpack('>h', d[vo + 0x24 + 2 * i:vo + 0x26 + 2 * i])[0] for i in range(4)])
        self.voices[vo] = v
        return v

    def song_voice(self, song, index):
        return self.voice(u32(self.data, self.song_ptrs[song] + 0x10 + 4 * index))


def pitch_of(module, inst, note, paula=PAULA_PAL):
    """Paula period, nominal MIDI, sounding MIDI (float) and Hz of a note on an instrument."""
    idx = note + module.midi_offset
    if not 0 <= idx < len(module.periods):
        raise ValueError(f'note {note} outside the period table')
    cycle = inst['samples_per_hi_cycle']
    shift = max(0, inst['octaves'] - note // (83 // inst['octaves']) - 1)
    period = module.periods[idx] // (cycle << shift)          # divu.w: integer quotient
    true_cycle = TRUE_CYCLE.get(inst['name'])
    if true_cycle is None:
        return period, idx, None, None
    hz = paula / (period * true_cycle)
    return period, idx, 69 + 12 * math.log2(hz / 440), hz


class Track:
    def __init__(self, n):
        self.n = n
        self.active = True
        self.seq_off = 0
        self.ptr = None
        self.count = 0          # $e
        self.release = 0        # $10
        self.voice_index = None
        self.volume = 32        # $1e
        self.hold = 0           # $38 (command 0xe0)
        self.tie = 0            # $3a
        self.sounding = None    # event dict of the note the channel is playing


def decode(module, song, loops=1, timer_lo=0, pal=True):
    """Replay subsong `song` for `loops` passes. Returns a dict with the events."""
    d = module.data
    sdef = module.song_ptrs[song]
    seqs = [u32(d, sdef + 4 * t) for t in range(4)]
    tracks = [Track(t) for t in range(4)]
    for t in tracks:
        t.ptr = u32(d, seqs[t.n])
    eclock = ECLOCK_PAL if pal else ECLOCK_NTSC
    paula = PAULA_PAL if pal else PAULA_NTSC
    timer = [None, timer_lo]
    events = [[] for _ in range(4)]
    tempo = []
    loop_ticks = [None] * 4
    passes = [0] * 4
    tick = 0
    unknown = set()

    def end_sound(t, at, why):
        ev = t.sounding
        if ev is not None and ev['end_tick'] is None:
            ev['end_tick'] = min(at, ev['sample_end_tick']) if ev['sample_end_tick'] is not None else at
            ev['end_reason'] = why if ev['sample_end_tick'] is None or at <= ev['sample_end_tick'] else 'sample end'
        t.sounding = None

    while not all(p >= loops for p in passes) and tick < 200000:
        for t in tracks:
            if passes[t.n] >= loops or not t.active:
                continue
            if t.count:
                t.count -= 1
                if t.count == t.release and t.hold != 1 and t.tie == 0:
                    if t.sounding is not None:
                        t.sounding['gate_ticks'] = tick - t.sounding['tick']
                    end_sound(t, tick, 'release')
                continue
            while True:          # read commands until a note (0x5de)
                c, a = d[t.ptr], d[t.ptr + 1]
                if c < 0xd9:
                    break
                if c == 0xd9:
                    t.seq_off += 6
                    t.ptr = u32(d, seqs[t.n] + t.seq_off)
                    continue
                if c == 0xdb:
                    passes[t.n] += 1
                    if loop_ticks[t.n] is None:
                        loop_ticks[t.n] = tick
                    t.seq_off = 0
                    t.ptr = u32(d, seqs[t.n])
                    if passes[t.n] >= loops:
                        end_sound(t, tick, 'song end')
                        break
                    continue
                if c == 0xda:
                    t.active = False
                    break
                if c == 0xdc:
                    t.voice_index = a
                elif c in (0xdd, 0xde):
                    timer[0 if c == 0xdd else 1] = a
                    if timer[0] is not None:
                        val = timer[0] * 256 + timer[1]
                        if not tempo or tempo[-1]['timer'] != val:
                            tempo.append(dict(tick=tick, timer=val, tick_s=val / eclock))
                elif c == 0xdf:
                    t.volume = a
                    if t.sounding is not None:
                        t.sounding.setdefault('volume_changes', []).append((tick, a))
                    events[t.n].append(dict(type='volume', tick=tick, volume=a))
                elif c == 0xe0:
                    t.hold = a
                    events[t.n].append(dict(type='hold', tick=tick, value=a))
                else:
                    unknown.add(c)
                t.ptr += 2
            if passes[t.n] >= loops or not t.active:
                continue
            raw, dur_index = d[t.ptr], d[t.ptr + 1]
            t.ptr += 2
            transpose = struct.unpack('>h', d[seqs[t.n] + t.seq_off + 4:seqs[t.n] + t.seq_off + 6])[0]
            if raw & 0x80:
                if t.tie == 0:
                    t.tie = 2
            else:
                t.tie = 0
            note = (raw & 0x7f) + transpose
            length, gate = module.durations[dur_index]
            t.count = length - 1
            t.release = length - 1 - gate
            v = module.song_voice(song, t.voice_index)
            inst = v['instrument']
            if inst is None:                       # voice 0: no sample, a rest
                events[t.n].append(dict(type='rest', tick=tick, duration=length))
                continue
            if t.tie == 1:                         # tied: no retrigger, pitch unchanged
                if t.sounding is not None:
                    t.sounding['duration'] += length
                    t.sounding['tied_notes'].append(note)
                continue
            if t.tie:
                t.tie -= 1
            # Without a release the channel's DMA is still on: Paula keeps the
            # new period and volume at once, but reaches the new sample start
            # only when the current block (whole sample or loop) ends.
            prev = t.sounding
            delayed = prev is not None and (prev['sample_end_tick'] is None or prev['sample_end_tick'] > tick)
            end_sound(t, tick, 'next note')
            period, nominal, midi, hz = pitch_of(module, inst, note, paula)
            rate = paula / period
            sample_end = None
            if inst['repeat_samples'] == 0:
                sample_end = tick + inst['one_shot_samples'] / rate / (tempo[-1]['tick_s'] if tempo else 1)
            ev = dict(type='note', tick=tick, duration=length, gate=None if (t.hold == 1 or t.tie) else gate,
                      raw=raw, transpose=transpose, note=note, voice=t.voice_index, instrument=inst['name'],
                      volume=t.volume, period=period, sample_rate=round(rate, 1), nominal_midi=nominal,
                      midi=None if midi is None else round(midi, 2), hz=None if hz is None else round(hz, 2),
                      sustained=bool(t.tie), tied_notes=[], end_tick=None, end_reason=None,
                      restart='after current block' if delayed else 'immediate',
                      sample_end_tick=None if sample_end is None else round(sample_end, 2))
            if v['arpeggio']:
                ev['arpeggio'] = v['arp_steps']
            if v['vibrato']:
                ev['vibrato'] = dict(upper=v['vib_upper'], lower=v['vib_lower'], step=v['vib_step'],
                                     speed=v['vib_speed'], delay=v['vib_delay'])
            events[t.n].append(ev)
            t.sounding = ev
        tick += 1
    for t in tracks:
        end_sound(t, tick, 'song end')
    for evs in events:
        for ev in evs:
            if ev['type'] == 'note' and ev['end_tick'] is not None:
                ev['end_tick'] = round(ev['end_tick'], 2)
    tick_s = tempo[0]['tick_s'] if tempo else None
    return dict(song=song, definition=module.song_names.get(sdef, hex(sdef)), events=events, tempo=tempo,
                loop_ticks=loop_ticks, ticks=tick, tick_s=tick_s, unknown_commands=sorted(unknown),
                timer_lo=timer_lo, pal=pal)


def seconds(result, tick):
    """Time of a tick (constant tempo: every song sets one value only)."""
    t, last_tick = 0.0, 0
    tick_s = result['tempo'][0]['tick_s']
    for ch in result['tempo']:
        if ch['tick'] > tick:
            break
        t += (ch['tick'] - last_tick) * tick_s
        last_tick, tick_s = ch['tick'], ch['tick_s']
    return t + (tick - last_tick) * tick_s


def channel_stats(result):
    rows = []
    for ch, evs in enumerate(result['events']):
        notes = [e for e in evs if e['type'] == 'note']
        insts = {}
        for e in notes:
            insts.setdefault(e['instrument'], []).append(e)
        desc = []
        for name, es in insts.items():
            pitched = [e for e in es if e['midi'] is not None]
            if pitched:
                lo = min(round(e['midi']) for e in pitched)
                hi = max(round(e['midi']) for e in pitched)
                rng = f'{note_name(lo)}..{note_name(hi)} (MIDI {lo}..{hi})'
            else:
                rng = 'notes ' + ','.join(str(n) for n in sorted({e['note'] for e in es}))
            desc.append(dict(instrument=name, role=ROLE.get(name, '?'), notes=len(es), range=rng))
        rows.append(dict(channel=ch, notes=len(notes), rests=sum(e['type'] == 'rest' for e in evs),
                         tied=sum(len(e['tied_notes']) for e in notes),
                         volumes=sorted({e['volume'] for e in notes}), instruments=desc))
    return rows


def data_size(module, song):
    """Bytes of the song's own data: unique patterns (2 bytes per entry) and pattern lists."""
    d = module.data
    sdef = module.song_ptrs[song]
    patterns, entries = {}, 0
    for t in range(4):
        seq, off = u32(d, sdef + 4 * t), 0
        while True:
            start = p = u32(d, seq + off)
            entries += 1
            while d[p] not in (0xd9, 0xda, 0xdb):
                p += 2
            patterns[start] = p + 2 - start
            if d[p] != 0xd9:
                break
            off += 6
    return dict(unique_patterns=len(patterns), pattern_bytes=sum(patterns.values()), list_entries=entries,
                original_bytes=sum(patterns.values()) + 6 * entries, compact_bytes=sum(patterns.values()) + 3 * entries)


def summary(module, results):
    out = []
    for r in results:
        loop = r['loop_ticks'][0]
        same = len(set(r['loop_ticks'])) == 1
        tick_s = r['tick_s']
        bpm = 60 / (24 * tick_s)
        out.append(f"== subsong {r['song']} ({r['definition']})")
        out.append(f"  tempo: CIA timer {r['tempo'][0]['timer']} -> tick {tick_s * 1000:.2f} ms "
                   f"({1 / tick_s:.2f} Hz); 24 ticks/quarter = {bpm:.1f} bpm; tempo changes: "
                   f"{len(set(x['timer'] for x in r['tempo'])) - 1}")
        out.append(f"  loop: whole song, from tick 0; length {loop} ticks = {seconds(r, loop):.3f} s "
                   f"({loop / 96:.0f} bars of 96 ticks); all tracks equal: {same}")
        size = data_size(module, r['song'])
        out.append(f"  data: {size['unique_patterns']} unique patterns ({size['pattern_bytes']} bytes), "
                   f"{size['list_entries']} pattern-list entries; {size['original_bytes']} bytes as stored, "
                   f"{size['compact_bytes']} with 3-byte list entries")
        if r['unknown_commands']:
            out.append(f"  unknown commands: {r['unknown_commands']}")
        for row in channel_stats(r):
            out.append(f"  ch{row['channel']}: {row['notes']} notes, {row['rests']} rests, {row['tied']} tied, "
                       f"volume {row['volumes']}")
            for i in row['instruments']:
                out.append(f"      {i['instrument']:<15} {i['role']:<20} {i['notes']:>4} notes  {i['range']}")
    return '\n'.join(out)


def listing(module, r):
    out = [f"subsong {r['song']} ({r['definition']}), tick {r['tick_s'] * 1000:.3f} ms, loop {r['loop_ticks'][0]} ticks"]
    for x in r['tempo']:
        out.append(f"  tempo @ tick {x['tick']}: timer {x['timer']} ({x['tick_s'] * 1000:.3f} ms)")
    for ch, evs in enumerate(r['events']):
        out.append(f'-- channel {ch}')
        for e in evs:
            t = f"{e['tick']:>6} {seconds(r, e['tick']):8.3f}s"
            if e['type'] == 'note':
                p = (f"{note_name(round(e['midi'])):<4} midi {e['midi']:6.2f} {e['hz']:8.2f} Hz"
                     if e['midi'] is not None else f"(unpitched)  {e['sample_rate']:7.0f} Hz rate")
                gate = 'sustain' if e['gate'] is None else f"gate {e['gate']}"
                tie = f" +tied{e['tied_notes']}" if e['tied_notes'] else ''
                tie += ' [sample restarts after the current block]' if e['restart'] != 'immediate' else ''
                out.append(f"  {t} NOTE {e['note']:>3} {p} {e['instrument']:<14} vol {e['volume']:>2} "
                           f"dur {e['duration']:>3} {gate} end {e['end_tick']} ({e['end_reason']}){tie}")
            elif e['type'] == 'rest':
                out.append(f"  {t} rest dur {e['duration']}")
            else:
                out.append(f"  {t} {e['type']} {e.get('volume', e.get('value'))}")
    return '\n'.join(out)


def midi_file(module, r):
    """Standard MIDI file, format 1, 24 ticks per quarter = 1 replayer tick per MIDI tick."""
    def vlq(n):
        out = [n & 0x7f]
        n >>= 7
        while n:
            out.append(0x80 | (n & 0x7f))
            n >>= 7
        return bytes(reversed(out))

    def chunk(evs):
        evs.sort(key=lambda x: (x[0], x[1]))
        body, now = bytearray(), 0
        for at, _, data in evs:
            body += vlq(at - now) + data
            now = at
        body += vlq(0) + b'\xff\x2f\x00'
        return b'MTrk' + struct.pack('>I', len(body)) + bytes(body)

    tracks = []
    head = [(0, 0, b'\xff\x03' + vlq(len(n := f"Wings of Fury subsong {r['song']}".encode())) + n)]
    for x in r['tempo']:
        us = round(24 * x['tick_s'] * 1e6)
        head.append((x['tick'], 1, b'\xff\x51\x03' + us.to_bytes(3, 'big')))
    loop = r['loop_ticks'][0]
    head.append((0, 2, b'\xff\x06' + vlq(9) + b'loopStart'))
    head.append((loop, 2, b'\xff\x06' + vlq(7) + b'loopEnd'))
    tracks.append(chunk(head))
    for ch, evs in enumerate(r['events']):
        out = [(0, 0, b'\xff\x03' + vlq(len(n := f'Paula {ch}'.encode())) + n)]
        program = None
        for e in evs:
            if e['type'] != 'note':
                continue
            vel = max(1, min(127, e['volume'] * 2))
            start, end = e['tick'], max(e['tick'] + 1, math.ceil(e['end_tick']))
            if e['instrument'] in GM_DRUM:
                chan, key = 9, GM_DRUM[e['instrument']]
                end = min(end, start + 6)
            else:
                chan, key = ch, round(e['midi'])
                gp = GM_PROGRAM.get(e['instrument'], 0)
                if gp != program:
                    out.append((start, 0, bytes([0xc0 | chan, gp])))
                    program = gp
            out.append((start, 2, bytes([0x90 | chan, key, vel])))
            out.append((end, 1, bytes([0x80 | chan, key, 0])))
        tracks.append(chunk(out))
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(tracks), 24) + b''.join(tracks)


def to_json(module, results):
    out = dict(source=dict(wofsongs=str(SOURCE / 'wofsongs'), songplay=str(SOURCE / 'songplay')),
               instruments=[{k: v for k, v in i.items() if k != 'pcm'} | dict(true_cycle=TRUE_CYCLE.get(i['name']))
                            for i in module.instruments.values()],
               songs=[])
    for r in results:
        rr = {k: v for k, v in r.items()}
        rr['loop_seconds'] = seconds(r, r['loop_ticks'][0])
        for evs in rr['events']:
            for e in evs:
                e['seconds'] = round(seconds(r, e['tick']), 4)
        out['songs'].append(rr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--wofsongs', default=str(SOURCE / 'wofsongs'))
    ap.add_argument('--songplay', default=str(SOURCE / 'songplay'))
    ap.add_argument('--song', type=int, action='append', help='subsong 0..4 (repeatable; default 0,1,2,4)')
    ap.add_argument('--summary', action='store_true', help='per-song summary')
    ap.add_argument('--json', help='write all events as JSON to this file')
    ap.add_argument('--midi', nargs='?', const=str(MUSIC_OUT), help='write song<N>.mid into this directory')
    ap.add_argument('--loops', type=int, default=1, help='passes through the song (default 1)')
    ap.add_argument('--ntsc', action='store_true', help='NTSC clocks (default PAL)')
    ap.add_argument('--timer-lo', type=int, default=0, help='CIA-A timer A low byte (never written by the songs; default 0)')
    args = ap.parse_args()
    module = Module(Path(args.wofsongs).read_bytes(), Path(args.songplay).read_bytes())
    songs = args.song or list(UNIQUE_SONGS)
    results = [decode(module, s, args.loops, args.timer_lo, not args.ntsc) for s in songs]
    if args.summary:
        print(summary(module, results))
    if args.json:
        Path(args.json).write_text(json.dumps(to_json(module, results), indent=1))
        print('wrote', args.json)
    if args.midi:
        out = Path(args.midi)
        out.mkdir(parents=True, exist_ok=True)
        for r in results:
            p = out / f"song{r['song']}.mid"
            p.write_bytes(midi_file(module, r))
            print('wrote', p)
    if not (args.summary or args.json or args.midi):
        for r in results:
            print(listing(module, r))


if __name__ == '__main__':
    main()
