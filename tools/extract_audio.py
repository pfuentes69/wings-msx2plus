"""Extract source-preserving Amiga audio, instruments and music metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import wave


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_hunks(data):
    pos = 0
    def take(size):
        nonlocal pos
        if size < 0 or pos + size > len(data):
            raise ValueError('truncated HUNK data')
        result = data[pos:pos + size]
        pos += size
        return result
    def word():
        return int.from_bytes(take(4), 'big')
    if word() != 1011:
        raise ValueError('not an Amiga HUNK executable')
    while True:
        n = word()
        if not n:
            break
        take(n * 4)
    table, first, last = word(), word(), word()
    count = last - first + 1
    if not 0 < count <= table <= 256 or first != 0:
        raise ValueError('unsupported HUNK segment table')
    sizes = [word() & 0x3fffffff for _ in range(count)]
    segments = []
    current = None
    while pos < len(data):
        # Observed compiler overlay trailer; no overlay data is present.
        if data[pos:] == bytes.fromhex('000003f50000000000000000'):
            pos = len(data)
            break
        tag = word()
        if tag in (1001, 1002, 1003):
            if current is not None or len(segments) >= count:
                raise ValueError('unexpected HUNK segment')
            size = word() * 4
            if size > sizes[len(segments)] * 4:
                raise ValueError('HUNK payload exceeds allocated segment')
            current = dict(type=tag, file_offset=pos, bytes=size, symbols={}, relocations=[])
            current['payload'] = take(size) if tag != 1003 else b''
            segments.append(current)
        elif tag == 1004 and current is not None:
            while True:
                n = word()
                if not n:
                    break
                target = word()
                if target >= count:
                    raise ValueError('invalid relocation target')
                offsets = [word() for _ in range(n)]
                if any(o % 2 or o + 4 > current['bytes'] for o in offsets):
                    raise ValueError('relocation outside segment')
                current['relocations'].extend((o, target) for o in offsets)
        elif tag == 1008 and current is not None:
            while True:
                n = word()
                if not n:
                    break
                name = take(n * 4).rstrip(b'\0').decode('ascii')
                value = word()
                if value > current['bytes'] or name in current['symbols']:
                    raise ValueError('invalid HUNK symbol')
                current['symbols'][name] = value
        elif tag == 1009 and current is not None:
            take(word() * 4)
        elif tag == 1010 and current is not None:
            current = None
        else:
            raise ValueError(f'unsupported/unexpected HUNK tag {tag}')
    if current is not None or len(segments) != count:
        raise ValueError('incomplete HUNK file')
    return segments


def read_8svx(data):
    if len(data) < 12 or data[:4] != b'FORM' or data[8:12] != b'8SVX':
        raise ValueError('not IFF/8SVX')
    if int.from_bytes(data[4:8], 'big') + 8 != len(data):
        raise ValueError('8SVX FORM length mismatch')
    pos, chunks = 12, {}
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError('truncated 8SVX chunk header')
        key, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], 'big')
        end = pos + 8 + size
        if end + size % 2 > len(data) or key in chunks:
            raise ValueError('invalid/truncated/duplicate 8SVX chunk')
        chunks[key] = data[pos + 8:end]
        pos = end + size % 2
    vhdr = chunks.get(b'VHDR', b'')
    if len(vhdr) != 20 or b'BODY' not in chunks:
        raise ValueError('missing BODY or invalid VHDR')
    one, repeat, cycle, rate, octaves, compression, volume = struct.unpack('>IIIHBBI', vhdr)
    if not rate or octaves != 1 or compression != 0 or chunks.get(b'CHAN', b'\0\0\0\0') != b'\0\0\0\0':
        raise ValueError('only uncompressed single-octave mono 8SVX is supported')
    pcm = chunks[b'BODY']
    if not pcm or one + repeat != len(pcm):
        raise ValueError('VHDR sample counts do not match BODY')
    return pcm, dict(name=chunks.get(b'NAME', b'').split(b'\0')[0].decode('ascii'),
                     rate_hz=rate, one_shot_samples=one, repeat_samples=repeat,
                     samples_per_hi_cycle=cycle, octaves=octaves, compression=compression,
                     volume_fixed16=volume, signed_pcm_sha256=sha(pcm))


def wav_bytes(pcm, rate):
    # Amiga 8-bit PCM is signed; 8-bit PCM WAV uses unsigned offset binary.
    import io
    out = io.BytesIO()
    with wave.open(out, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(1)
        wav.setframerate(rate)
        wav.writeframes(bytes(v ^ 0x80 for v in pcm))
    return out.getvalue()


def extract(source, sfx_rate):
    if not 1000 <= sfx_rate <= 96000:
        raise ValueError('SFX preview rate outside supported bounds')
    song_data = (source / 'wofsongs').read_bytes()
    player_data = (source / 'songplay').read_bytes()
    segments = read_hunks(song_data)
    read_hunks(player_data)
    music = segments[1]
    data, symbols = music['payload'], music['symbols']
    first_song = symbols['song1']
    if first_song % 4 or not 0 < first_song <= 128:
        raise ValueError('unsupported music song table')
    slots = list(struct.unpack_from(f'>{first_song // 4}I', data))
    song_symbols = {v: k for k, v in symbols.items() if k.startswith('song') and k != 'songs'}
    if any(v not in song_symbols for v in slots):
        raise ValueError('song slot does not reference a known song symbol')
    files = {'music/kh.Wings_of_Fury': song_data, 'music/songplay': player_data}
    report = dict(source_directory=str(source), music=dict(format='Kris Hatlelid two-file module',
        module_sha256=sha(song_data), player_sha256=sha(player_data),
        slots=[dict(subsong=i, data_offset=v, symbol=song_symbols[v]) for i, v in enumerate(slots)],
        unique_song_definitions=len(set(slots)), data_segment_file_offset=music['file_offset']),
        effects=[], instruments=[])
    for p in sorted((source / 'sounds').iterdir()):
        if not p.is_file():
            continue
        pcm = p.read_bytes()
        if not pcm:
            raise ValueError('empty effect sample')
        dest = f'effects/{p.name}.wav'
        files[dest] = wav_bytes(pcm, sfx_rate)
        signed = [v if v < 128 else v - 256 for v in pcm]
        report['effects'].append(dict(name=p.name, source_sha256=sha(pcm), bytes=len(pcm),
            sample_min=min(signed), sample_max=max(signed), wav=dest, wav_sha256=sha(files[dest]),
            preview_rate_hz=sfx_rate, rate_status='assumed preview rate; original playback is period-dependent',
            duration_at_preview_rate=len(pcm) / sfx_rate, encoding='raw signed 8-bit mono candidate; WAV bytes XOR 0x80'))
    # Only walk complete FORM containers within the music data segment.
    pos = 0
    while True:
        pos = data.find(b'FORM', pos)
        if pos < 0:
            break
        if pos + 12 > len(data):
            raise ValueError('truncated embedded FORM')
        size = int.from_bytes(data[pos + 4:pos + 8], 'big') + 8
        if size < 12 or pos + size > len(data):
            raise ValueError('embedded FORM outside music segment')
        blob = data[pos:pos + size]
        pcm, metadata = read_8svx(blob)
        name = metadata['name']
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in name):
            raise ValueError('unsafe instrument name')
        base = f'instruments/{name}'
        if base + '.8svx' in files:
            raise ValueError('duplicate instrument name')
        files[base + '.8svx'] = blob
        files[base + '.wav'] = wav_bytes(pcm, metadata['rate_hz'])
        report['instruments'].append(dict(file_offset=music['file_offset'] + pos, bytes=len(blob),
            form_sha256=sha(blob), wav=base + '.wav', wav_sha256=sha(files[base + '.wav']), **metadata))
        pos += size
    return files, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='recovered Wings_of_Fury directory')
    parser.add_argument('output', type=Path, help='new output directory; refuses overwrite')
    parser.add_argument('--sfx-rate', type=int, default=8363, help='assumed SFX audition rate, NOT a recovered original rate')
    args = parser.parse_args()
    files, report = extract(args.source, args.sfx_rate)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, blob in files.items():
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['effects'])} SFX preview WAVs, {len(report['instruments'])} exact 8SVX instruments + WAVs, music pair and {len(report['music']['slots'])} song slots")


if __name__ == '__main__':
    main()
