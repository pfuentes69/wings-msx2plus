"""Verify a full-height V9958 ring streamer on an emulated MSX2+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def world_pixel(x, y):
    block = (x % 4096) // 8
    top = 100 + (block * 13 + (block // 8) * 7) % 64
    if 32 + (block // 64) % 8 * 4 <= y < 36 + (block // 64) % 8 * 4:
        return 11
    if y >= 192:
        return 13
    return 0 if y < top else 3 + (block // 8) % 12


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/hardware-scroll')
    args = parser.parse_args()
    if not args.emulator:
        parser.error('openmsx is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / 'verification.json').unlink(missing_ok=True)
    (output / 'emulator-report.txt').unlink(missing_ok=True)
    personal = Path(os.environ.get('OPENMSX_HOME', Path.home() / '.openMSX'))
    env = dict(os.environ, OPENMSX_HOME=str(output / 'openmsx-home'), WINGS_ROOT=str(ROOT),
               WINGS_TEST_OUT=str(output), SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA', str(personal / 'share'))
    rom = ROOT / 'out/hardware-scroll/hardware-scroll.rom'
    with (output / 'openmsx.log').open('w') as log:
        subprocess.run([args.emulator, '-machine', args.machine, '-cart', str(rom),
                        '-script', str(ROOT / 'tools/hardware_scroll_smoke.tcl')],
                       env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                       timeout=100, check=True)
    report = (output / 'emulator-report.txt').read_text()
    assert report.rstrip().endswith('PASS'), report[-2000:]
    snapshots, renders, intervals = {}, [], []
    columns = offscreen_checks = 0
    colors = {0: (0, 0, 0)}
    for line in report.splitlines():
        parts = line.split()
        if parts[0] == 'render_ms':
            renders.append(float(parts[1]))
        elif parts[0] == 'interval_ms':
            intervals.append(float(parts[1]))
        elif parts[0] == 'columns':
            columns = int(parts[1])
        elif parts[0] == 'offscreen_checks':
            offscreen_checks = int(parts[1])
        elif parts[0] == 'snapshot':
            name, camera, paused, reverse = parts[1], *map(int, parts[2:])
            snapshots[name] = dict(camera=camera, paused=paused, reverse=reverse)
            regs = (output / f'{name}.regs').read_bytes()
            assert regs[25] & 3 == 3 and regs[2] & 32, name
            assert regs[26] == (((camera & 511) + 7) // 8) & 63, name
            assert regs[27] == (-camera) % 8, name
            assert (output / f'{name}.palette').read_bytes() == bytes([
                0,0, 0,0, 0x11,6, 0x33,7, 0x17,1, 0x27,3, 0x51,5, 0x27,6,
                0x71,1, 0x73,3, 0x61,6, 0x66,6, 0x11,7, 0x22,2, 0x44,4, 0x77,7]), name
            vram = (output / f'{name}.vram').read_bytes()
            for y in range(212):
                # First eight display pixels are masked by R#25.
                for x in range(8, 256):
                    ring = (camera + x) % 512
                    address = (ring // 256) * 32768 + y * 128 + (ring % 256) // 2
                    actual = (vram[address] & 15) if ring % 2 else vram[address] >> 4
                    assert actual == world_pixel(camera + x, y), (name, x, y, actual)
            assert not any(vram[65536:]), f'{name}: writes escaped the ring'
            image = Image.open(output / f'{name}.png').convert('RGB')
            assert image.size == (320, 240), (name, image.size)
            pixels = image.load()
            for y in range(212):
                for x in range(256):
                    index = world_pixel(camera + x, y) if x >= 8 else 0
                    rgb = pixels[32 + x, 14 + y]
                    if index not in colors:
                        assert rgb not in colors.values(), (name, 'palette colors collapsed', index, rgb)
                        colors[index] = rgb
                    assert rgb == colors[index], (name, 'raster mismatch', x, y, index, rgb)
    required = {'forward_wrap', 'reverse_wrap', 'paused', 'still_paused', 'reversed'}
    required.update(('page_before', 'page_after', 'ring_before', 'ring_after',
                     'reverse_page_before', 'reverse_page_after'))
    required.update(f'fine_{phase}' for phase in range(8))
    assert required <= snapshots.keys(), required - snapshots.keys()
    assert snapshots['paused']['camera'] == snapshots['still_paused']['camera']
    assert snapshots['paused']['paused'] == snapshots['still_paused']['paused'] == 1
    assert columns == offscreen_checks and columns > 550
    pal = bool((output / 'forward_wrap.regs').read_bytes()[9] & 2)
    target = 40 if pal else 1000 / 30
    assert len(intervals) > 1000
    assert min(intervals) > target - 2 and max(intervals) < target + 2
    assert max(renders) < target
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256(rom.read_bytes()).hexdigest(),
                   target_fps=25 if pal else 30, publication_samples=len(intervals),
                   publication_ms=dict(min=min(intervals), median=statistics.median(intervals), max=max(intervals)),
                   redraw_ms=dict(min=min(renders), median=statistics.median(renders), max=max(renders)),
                   missed_deadlines=0, streamed_columns=columns, offscreen_write_checks=offscreen_checks,
                   snapshots=snapshots,
                   checks=['full-height visible VRAM', 'rendered raster pixels and left mask',
                           'all eight fine-scroll phases', 'forward and reverse world wrap',
                           'page and ring seams in both directions',
                           'pause and keyboard reversal', 'untouched upper 64 KiB',
                           'VBlank register publication', '25/30 Hz deadlines'])
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: {len(snapshots)} snapshots; max update {max(renders):.2f} ms')


if __name__ == '__main__':
    main()
