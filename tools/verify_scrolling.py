"""Measure the software scenery-strip benchmark and compare all displayed pixels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
from aircraft_scene import AircraftScene, scenery_pixel

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/scrolling-smoke')
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
                        '-script', str(ROOT / 'tools/scrolling_smoke.tcl')], env=env, cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, timeout=50, check=True)
    text = report.read_text()
    if not text.rstrip().endswith('PASS'):
        raise RuntimeError(f'emulator did not finish; inspect {output}')
    scene = AircraftScene()
    snapshots, renders, intervals = {}, [], []
    for line in text.splitlines():
        parts = line.split()
        if parts[0] == 'render_ms': renders.append(float(parts[1]))
        elif parts[0] == 'interval_ms': intervals.append(float(parts[1]))
        elif parts[0] == 'snapshot':
            name = parts[1]
            x, y, frame, page, camera, enabled, paused, reverse = map(int, parts[2:])
            assert 0 <= camera < 512 and camera % 2 == 0, name
            assert page in (0, 1) and enabled in (0, 1), name
            snapshots[name] = dict(x=x, y=y, frame=frame, page=page, camera=camera,
                                   enabled=enabled, paused=paused, reverse=reverse)
            vram = (output / f'{name}.vram').read_bytes()
            expected = scene.page(frame, x, y, camera if enabled else None)
            assert vram[page * 32768:(page + 1) * 32768] == expected, f'{name}: incorrect scenery/compositing'
            assert (output / f'{name}.palette').read_bytes() == scene.palette, name
            regs = (output / f'{name}.regs').read_bytes()
            assert regs[0] & 14 == 6 and regs[1] & 64 and regs[9] & 128, name
            # Rendering must leave both source strips and every atlas rectangle intact.
            for half in range(2):
                for row in range(16):
                    start = (half + 2) * 32768 + (196 + row) * 128
                    strip = bytes(scenery_pixel(half * 256 + col, row) * 16 +
                                  scenery_pixel(half * 256 + col + 1, row) for col in range(0, 256, 2))
                    assert vram[start:start + 128] == strip, f'{name}: scenery cache corrupted'
            for shape in scene.frames:
                data = (scene.folder / shape['file']).read_bytes()
                stride = shape['width'] // 2
                for row in range(shape['height']):
                    start = (shape['atlas_y'] + row) * 128 + shape['atlas_x'] // 2
                    assert vram[start:start + stride] == data[row * stride:(row + 1) * stride], f'{name}: atlas corrupted'
    required = {'baseline', 'enabled', 'overlap', 'turned', 'paused', 'still_paused',
                'reversed', 'disabled', 'sky_restored', 'reenabled',
                'seam_before', 'seam_after', 'wrap_before', 'wrapped'}
    assert set(snapshots) == required, f'missing snapshots: {required - snapshots.keys()}'
    assert snapshots['baseline']['enabled'] == snapshots['disabled']['enabled'] == snapshots['sky_restored']['enabled'] == 0
    assert snapshots['overlap']['y'] == 180 and snapshots['overlap']['enabled'] == 1
    assert snapshots['turned']['frame'] == scene.metadata['pitch_left'][4]
    assert snapshots['paused']['camera'] == snapshots['still_paused']['camera']
    assert snapshots['paused']['paused'] == snapshots['still_paused']['paused'] == 1
    assert snapshots['reversed']['reverse'] == 1 and snapshots['reversed']['paused'] == 0
    assert snapshots['reversed']['camera'] < snapshots['paused']['camera']
    assert snapshots['sky_restored']['y'] == 0 and snapshots['reenabled']['enabled'] == 1
    assert 'forced_overrun PASS' in text, 'late-frame recovery not verified'
    pal = bool((output / 'baseline.regs').read_bytes()[9] & 2)
    target_ms = 40.0 if pal else 1000 / 30
    assert len(renders) > 250 and len(intervals) > 350
    assert max(renders) < target_ms, 'render over budget'
    assert min(intervals) > target_ms - 2 and max(intervals) < target_ms + 2, 'unstable cadence'
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256((ROOT / 'out/wings.rom').read_bytes()).hexdigest(),
        target_fps=25 if pal else 30, publication_samples=len(intervals),
        publication_ms=dict(min=min(intervals), median=statistics.median(intervals), max=max(intervals)),
        redraw_samples=len(renders), redraw_ms=dict(min=min(renders), median=statistics.median(renders), max=max(renders)),
        missed_deadlines=0, forced_overrun_recovery=True, snapshots=snapshots,
        checks=['full-page transparent compositing', '512-pixel strip seams and wrap', 'pause and reverse',
                'toggle restoration', 'immutable VRAM atlas and strip caches', 'VBlank publication', '25/30 Hz deadlines'])
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f"PASS: {len(snapshots)} snapshots, {len(intervals)} publications; max redraw {max(renders):.2f} ms")


if __name__ == '__main__':
    main()
