#!/usr/bin/env python3
"""Check the banked ASCII8 code layout of a linked mission ROM (Intel HEX).

Resident code (address bits 16-23 == 0) must stay in windows 0..2
(4000h-9FFFh) because window 3 is switched by banked calls. Each banked
segment N is linked at (N << 16) | A000h and must fit in A000h-BFFFh.
Code segments must not overlap raw data banks or lie outside the ROM.
Exits non-zero on any violation so MSXgl's post-build step fails.
"""
import argparse
from pathlib import Path
import sys

SEGMENT = 0x2000
RESIDENT = (0x4000, 0xA000)
BANKED = (0xA000, 0xC000)


def read_hex(path):
    """Return {segment: set(addresses)} from an Intel HEX file."""
    used, base = {}, 0
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(':'):
            raise ValueError(f'{path}:{number}: not an Intel HEX record')
        data = bytes.fromhex(line[1:])
        count, address, kind = data[0], int.from_bytes(data[1:3], 'big'), data[3]
        if len(data) != count + 5 or sum(data) & 0xFF:
            raise ValueError(f'{path}:{number}: bad length or checksum')
        payload = data[4:4 + count]
        if kind == 0:
            for offset in range(count):
                full = base + address + offset
                used.setdefault(full >> 16, set()).add(full & 0xFFFF)
        elif kind == 1:
            break
        elif kind == 2:
            base = int.from_bytes(payload, 'big') << 4
        elif kind == 4:
            base = int.from_bytes(payload, 'big') << 16
    return used


def check(used, rom_kib, code_segments, data_banks):
    """Return (errors, report lines)."""
    errors, report = [], []
    segments_in_rom = rom_kib * 1024 // SEGMENT
    resident = used.get(0, set())
    outside = [a for a in resident if not RESIDENT[0] <= a < RESIDENT[1]]
    if outside:
        errors.append(f'resident code reaches {max(outside):04X}h; window 3 (A000h) is banked')
    top = max(resident, default=RESIDENT[0] - 1) + 1
    report.append(f'resident 4000h-{top - 1:04X}h: {top - RESIDENT[0]} bytes, '
                  f'{RESIDENT[1] - top} free of {RESIDENT[1] - RESIDENT[0]}')
    for segment in sorted(code_segments):
        if segment < 3 or segment >= segments_in_rom:
            errors.append(f'code segment {segment} is resident or outside the {rom_kib} KiB ROM')
        if segment in data_banks:
            errors.append(f'code segment {segment} overlaps a raw data bank')
    for segment in sorted(s for s in used if s):
        addresses = used[segment]
        if segment not in code_segments:
            errors.append(f'segment {segment} holds code but is not a declared code segment')
            continue
        bad = [a for a in addresses if not BANKED[0] <= a < BANKED[1]]
        if bad:
            errors.append(f'segment {segment} code at {min(bad):04X}h is outside A000h-BFFFh')
        top = max(addresses) + 1
        report.append(f'segment {segment:2} A000h-{top - 1:04X}h: {top - BANKED[0]} bytes, '
                      f'{BANKED[1] - top} free')
    return errors, report


def parse_list(text):
    return {int(item) for item in text.split(',') if item}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('ihx')
    parser.add_argument('--rom-kib', type=int, required=True)
    parser.add_argument('--code-segments', type=parse_list, default=set())
    parser.add_argument('--data-banks', type=parse_list, default=set())
    args = parser.parse_args(argv)
    errors, report = check(read_hex(args.ihx), args.rom_kib, args.code_segments, args.data_banks)
    for line in report:
        print(f'ROM layout: {line}')
    for line in errors:
        print(f'ROM layout error: {line}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
