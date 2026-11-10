"""Extract a standard 880 KiB Amiga OFS disk; unsupported formats fail explicitly."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BLOCK_SIZE = 512


def extract_ofs(image):
    if len(image) != 880 * 1024 or image[:4] != b'DOS\x00':
        raise ValueError('only standard 880 KiB DOS0/OFS ADF images are supported')
    blocks = len(image) // BLOCK_SIZE
    seen = set()
    files = {}

    def block(number):
        if not 2 <= number < blocks:
            raise ValueError(f'block pointer outside filesystem: {number}')
        data = image[number * BLOCK_SIZE:(number + 1) * BLOCK_SIZE]
        if sum(struct.unpack('>128I', data)) & 0xffffffff:
            raise ValueError(f'invalid block checksum: {number}')
        return data

    def u32(data, offset):
        return struct.unpack_from('>I', data, offset)[0]

    def walk(number, parent):
        if number in seen:
            raise ValueError(f'filesystem cycle/shared block: {number}')
        seen.add(number)
        data = block(number)
        if u32(data, 0) != 2:
            raise ValueError('expected filesystem header block')
        length = data[432]
        if not 1 <= length <= 30:
            raise ValueError('invalid OFS filename length')
        name = data[433:433 + length].decode('latin1')
        if name in ('.', '..') or any(c in name for c in '/\\\x00'):
            raise ValueError('unsafe OFS filename')
        kind = u32(data, 508)
        if kind in (1, 2):
            if (number == blocks // 2) != (kind == 1):
                raise ValueError('unexpected root/directory type')
            folder = parent if kind == 1 else parent / name
            for offset in range(24, 312, 4):
                child = u32(data, offset)
                while child:
                    walk(child, folder)
                    child = u32(block(child), 496)
        elif kind == 0xfffffffd:
            size, pointer = u32(data, 324), u32(data, 16)
            payload = bytearray()
            sequence = 1
            while pointer:
                if pointer in seen:
                    raise ValueError('file data cycle/shared block')
                seen.add(pointer)
                chunk = block(pointer)
                amount = u32(chunk, 12)
                if u32(chunk, 0) != 8 or u32(chunk, 4) != number or u32(chunk, 8) != sequence or not 1 <= amount <= 488:
                    raise ValueError('invalid OFS data block header/sequence/length')
                if len(payload) + amount > size:
                    raise ValueError('OFS data exceeds declared file size')
                payload.extend(chunk[24:24 + amount])
                pointer = u32(chunk, 16)
                sequence += 1
            if len(payload) != size:
                raise ValueError('OFS file size mismatch')
            dest = parent / name
            if dest in files:
                raise ValueError('duplicate OFS path')
            files[dest] = bytes(payload)
        else:
            raise ValueError(f'unsupported filesystem entry type {kind:#x}')

    walk(blocks // 2, Path())
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='original ADF')
    parser.add_argument('output', type=Path, help='new output directory (must not exist)')
    args = parser.parse_args()
    image = args.input.read_bytes()
    files = extract_ofs(image)
    report_path = args.output.with_name(args.output.name + '-manifest.json')
    if report_path.exists():
        parser.error('output manifest already exists')
    args.output.mkdir(parents=True, exist_ok=False)
    for name, payload in files.items():
        dest = args.output / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        print(f'{len(payload):7d} {name}')
    # Put provenance alongside, never inside the recovered game's namespace.
    report = dict(source=str(args.input), sha256=hashlib.sha256(image).hexdigest(),
                  files=[dict(path=str(name), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                         for name, data in files.items()])
    with report_path.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(f'{len(files)} files extracted')


if __name__ == '__main__':
    main()
