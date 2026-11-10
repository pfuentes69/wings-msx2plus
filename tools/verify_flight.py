"""Check motion, bounds, frame pacing and every displayed pixel in openMSX."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/flight-smoke')
    args = parser.parse_args()
    if not args.emulator:
        parser.error('openmsx is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'emulator-report.txt'
    report.unlink(missing_ok=True)
    personal = Path(os.environ.get('OPENMSX_HOME', Path.home() / '.openMSX'))
    env = dict(os.environ, OPENMSX_HOME=str(output / 'openmsx-home'), WINGS_ROOT=str(ROOT),
               WINGS_TEST_OUT=str(output), SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA', str(personal / 'share'))
    with (output / 'openmsx.log').open('w') as log:
        subprocess.run([args.emulator, '-machine', args.machine, '-cart', str(ROOT / 'out/wings.rom'),
                        '-script', str(ROOT / 'tools/flight_smoke.tcl')], env=env, cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, timeout=50, check=True)
    text = report.read_text()
    if not text.rstrip().endswith('PASS'):
        raise RuntimeError(f'emulator did not finish; inspect {output}')
    snapshots, renders, intervals = {}, [], []
    palette = (ROOT / 'assets_msx/hellcat/palette.bin').read_bytes()
    for line in text.splitlines():
        parts = line.split()
        if parts[0] == 'render_ms': renders.append(float(parts[1]))
        elif parts[0] == 'interval_ms': intervals.append(float(parts[1]))
        elif parts[0] == 'snapshot':
            name, x, y, frame, left, page, count = parts[1], *map(int, parts[2:])
            assert 0 <= x <= 208 and not x % 2 and 0 <= y <= 180, name
            assert 0 <= frame < 3 and left in (0, 1) and page in (0, 1), name
            snapshots[name] = dict(x=x, y=y, frame=frame, left=left, page=page, renders=count)
            source = ('hc01', 'hc05', 'hc09')[frame] + ('-left' if left else '')
            packed = (ROOT / f'assets_msx/hellcat/{source}.sc5').read_bytes()
            expected = bytearray(32768)
            for row in range(32):
                address = (y + row) * 128 + x // 2
                expected[address:address + 24] = packed[row * 24:(row + 1) * 24]
            vram = (output / f'{name}.vram').read_bytes()
            assert vram[page * 32768:(page + 1) * 32768] == expected, f'{name}: stale or incorrect pixels'
            assert (output / f'{name}.palette').read_bytes() == palette, name
            regs = (output / f'{name}.regs').read_bytes()
            assert regs[0] & 14 == 6 and regs[1] & 64 and regs[9] & 128, name
    assert len(snapshots) == 10, 'missing captures'
    initial, up, coast, down = (snapshots[n] for n in ('initial', 'up_right', 'coast', 'down_left'))
    assert (initial['x'], initial['y'], initial['frame']) == (104, 88, 1)
    assert up['x'] > 104 and up['y'] < 88 and up['frame'] == 0 and up['left'] == 0
    assert coast['x'] > up['x'] and coast['y'] < up['y'] and coast['frame'] == 1
    assert down['x'] < coast['x'] and down['y'] > coast['y'] and down['frame'] == 2 and down['left'] == 1
    for name in ('reset', 'final_reset'):
        state = snapshots[name]
        assert (state['x'], state['y'], state['frame'], state['left']) == (104, 88, 1, 0), name
    for name, axis, limit in (('right_bound', 'x', 208), ('left_bound', 'x', 0),
                              ('top_bound', 'y', 0), ('bottom_bound', 'y', 180)):
        assert snapshots[name][axis] == limit, name
    pal = bool((output / 'initial.regs').read_bytes()[9] & 2)
    target_ms = 40.0 if pal else 1000 / 30
    assert len(renders) > 40 and len(intervals) > 200, 'too few timing samples'
    assert max(renders) < target_ms, 'render over budget'
    assert min(intervals) > target_ms - 2 and max(intervals) < target_ms + 2, 'unstable cadence'
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256((ROOT / 'out/wings.rom').read_bytes()).hexdigest(),
        target_fps=25 if pal else 30, publication_samples=len(intervals),
        publication_ms=dict(min=min(intervals), median=statistics.median(intervals), max=max(intervals)),
        redraw_samples=len(renders), redraw_ms=dict(min=min(renders), median=statistics.median(renders), max=max(renders)),
        missed_deadlines=0, snapshots=snapshots,
        checks=['accelerating directional movement', 'coasting and stop', 'left-facing reflection', 'reset',
                'four screen bounds', 'full-page pixel comparisons without trails', 'palette and mode',
                'VBlank publication', '25/30 Hz frame deadlines'])
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f"PASS: 10 snapshots, {len(intervals)} publications, {summary['target_fps']} fps target; max redraw {max(renders):.2f} ms")


if __name__ == '__main__':
    main()
