"""Bounded Rpck decompressor and PPkc archive reader for Wings of Fury."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import warnings

MAX_EXPANDED = 16 * 1024 * 1024


def unpack_rpck(data, max_size=MAX_EXPANDED):
    """Return non-Rpck bytes unchanged; reject truncated/oversized runs.

    Two supplied archives end in ff00 after the declared output size. These
    bytes are reported as unconsumed padding, never silently interpreted.
    """
    if data[:4] != b'Rpck':
        return data
    if len(data) < 8:
        raise ValueError('truncated Rpck header')
    target = struct.unpack_from('>I', data, 4)[0]
    if target > max_size:
        raise ValueError('Rpck output exceeds size limit')
    out = bytearray()
    pos = 8
    while len(out) < target:
        if pos >= len(data):
            raise ValueError('truncated Rpck control')
        control = data[pos]
        pos += 1
        count = 256 - control if control >= 128 else control + 1
        consumed = count if control >= 128 else 1
        if pos + consumed > len(data):
            raise ValueError('truncated Rpck run')
        if len(out) + count > target:
            raise ValueError('Rpck run exceeds declared output')
        out.extend(data[pos:pos + consumed] if control >= 128 else data[pos:pos + 1] * count)
        pos += consumed
    if pos != len(data):
        tail = data[pos:]
        if tail != b'\xff\x00':
            raise ValueError(f'unrecognized Rpck trailing data: {len(tail)} bytes')
        warnings.warn('Rpck: 2 unconsumed trailing bytes ff00 (observed archive padding)', stacklevel=2)
    return bytes(out)


def read_ppkc(data):
    """Return (name, offset, payload) tuples; offsets are relative to data area."""
    if len(data) < 6 or data[:4] != b'PPkc':
        raise ValueError('missing/truncated PPkc header')
    count = struct.unpack_from('>H', data, 4)[0]
    base = 6 + 8 * count
    if count == 0 or base > len(data):
        raise ValueError('empty or truncated PPkc index')
    offsets = struct.unpack_from(f'>{count}I', data, 6 + 4 * count)
    size = len(data) - base
    if offsets[0] != 0 or any(v > size for v in offsets):
        raise ValueError('PPkc offset outside payload or nonzero first offset')
    if any(a >= b for a, b in zip(offsets, (*offsets[1:], size))):
        raise ValueError('PPkc offsets must delimit nonempty ordered records')
    records = []
    names = set()
    for i, start in enumerate(offsets):
        name_bytes = data[6 + i * 4:10 + i * 4]
        if any(v < 32 or v > 126 for v in name_bytes) or b'/' in name_bytes or b'\\' in name_bytes:
            raise ValueError('unsafe/non-ASCII PPkc name')
        name = name_bytes.decode('ascii')
        if name in names:
            raise ValueError(f'duplicate PPkc name: {name!r}')
        names.add(name)
        end = offsets[i + 1] if i + 1 < count else size
        records.append((name, start, data[base + start:base + end]))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='.shp file or directory containing archives')
    parser.add_argument('output', type=Path, help='new output directory (must not exist)')
    args = parser.parse_args()
    sources = sorted(args.input.glob('*.shp')) if args.input.is_dir() else [args.input]
    if not sources:
        parser.error('no .shp archives found')
    # Parse everything before writing, and never overwrite existing research.
    decoded = [(p, unpack_rpck(p.read_bytes())) for p in sources]
    archives = [(p, data, read_ppkc(data)) for p, data in decoded]
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = []
    for p, data, records in archives:
        (args.output / (p.name + '.unpacked')).write_bytes(data)
        folder = args.output / p.stem
        folder.mkdir()
        for i, (name, offset, payload) in enumerate(records):
            dest = folder / f'{i:03d}_{name}.bin'
            dest.write_bytes(payload)
            manifest.append(dict(archive=str(p), archive_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                                 name=name, offset=offset, bytes=len(payload),
                                 sha256=hashlib.sha256(payload).hexdigest(), file=str(dest.relative_to(args.output))))
        print(f'{p.name}: {len(records)} records')
    (args.output / 'records.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
