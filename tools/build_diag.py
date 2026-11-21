#!/usr/bin/env python3
"""Build the hardware/loader diagnostic ROMs (docs/diag-rom.md).

tools/diag/wofdiag.asm -> out/diag/WOFDIAG.ROM, a 512 KiB ASCII8 ROM
like the game. Every 8 KiB bank ends with the
tag 'W', n, ~n, '8' that the ROM reads to tell which bank is in a window.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'tools/diag/wofdiag.asm'
OUT = ROOT / 'out/diag'
BANK = 8192
TAG = BANK - 4
NBANKS_ADDR = 0x4010


def assemble():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        subprocess.run(['sdasz80', '-o', '-s', '-l', str(tmp / 'wofdiag.rel'), str(SOURCE)], check=True)
        subprocess.run(['sdldz80', '-i', '-m', str(tmp / 'wofdiag.ihx'), str(tmp / 'wofdiag.rel')], check=True,
                       stdout=subprocess.DEVNULL)
        code = {}
        for line in (tmp / 'wofdiag.ihx').read_text().split():
            count, addr, kind = int(line[1:3], 16), int(line[3:7], 16), int(line[7:9], 16)
            if kind == 0:
                for i in range(count):
                    code[addr + i] = int(line[9 + 2 * i:11 + 2 * i], 16)
        return code


def image(code, banks):
    rom = bytearray(b'\xff' * (banks * BANK))
    for addr, value in code.items():
        if not 0x4000 <= addr < 0x4000 + TAG:
            sys.exit(f'diag code outside bank 0 at {addr:04X}')
        rom[addr - 0x4000] = value
    rom[NBANKS_ADDR - 0x4000] = banks
    for n in range(banks):
        rom[n * BANK + TAG:n * BANK + BANK] = bytes((ord('W'), n, n ^ 0xFF, ord('8')))
    return rom


def main():
    if not shutil.which('sdasz80'): sys.exit('sdasz80 (SDCC) not found')
    code = assemble()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f'code 4000h-{max(code):04X}h')
    for name, banks in (('WOFDIAG.ROM', 64),):
        (OUT / name).write_bytes(image(code, banks))
        print(OUT / name)


if __name__ == '__main__':
    main()
