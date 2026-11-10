"""Exercise both mapped turns and compare every captured shape with source-derived pixels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from aircraft_scene import AircraftScene, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/turn-smoke')
    args = parser.parse_args()
    emulator = shutil.which('openmsx')
    if not emulator: parser.error('openmsx is required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'emulator-report.txt'
    report.unlink(missing_ok=True)
    personal = Path(os.environ.get('OPENMSX_HOME', Path.home() / '.openMSX'))
    env = dict(os.environ, OPENMSX_HOME=str(output / 'openmsx-home'), WINGS_ROOT=str(ROOT),
               WINGS_TEST_OUT=str(output), SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA', str(personal / 'share'))
    with (output / 'openmsx.log').open('w') as log:
        subprocess.run([emulator, '-machine', args.machine, '-cart', str(ROOT / 'out/wings.rom'),
            '-script', str(ROOT / 'tools/turn_smoke.tcl')], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=35, check=True)
    text = report.read_text()
    assert text.rstrip().endswith('PASS'), text[-2000:]
    scene, frames, captures, video_hz, edge_cases, fully_clipped = AircraftScene(), [], [], 60, 0, 0
    for line in text.splitlines():
        words = line.split()
        if words[0] == 'video_hz':
            video_hz = int(words[1])
        elif words[0] == 'frame':
            frames.append(dict(time=float(words[1]), shape=int(words[2]), turning=int(words[3]), facing=int(words[4])))
        elif words[0] == 'capture':
            shape, page, x, y = map(int, words[1:])
            assert (x, y) in ((104, 88), (208, 180)), 'stationary turn moved the logical position'
            edge = (x, y) == (208, 180)
            prefix = 'edge-' if edge else ''
            vram = (output / f'{prefix}shape-{shape}.vram').read_bytes()
            expected = scene.page(shape, x, y)
            assert vram[page * 32768:(page + 1) * 32768] == expected, f'incorrect shape {shape}'
            if edge:
                edge_cases += 1
                fully_clipped += not any(expected)
            captures.append(shape)
    def unique_order(values):
        result = []
        for value in values:
            if not result or result[-1] != value: result.append(value)
        return result
    # Newest target is queued, and holding T must initiate only one transition.
    active = [f for f in frames if f['turning']]
    rtl = unique_order([f['shape'] for f in active if not f['facing']])
    ltr = unique_order([f['shape'] for f in active if f['facing']])
    # The final sample is published with the completed-facing flag, so compare the
    # active prefix; following idle frames are validated separately by the script.
    expected_rtl = unique_order(scene.metadata['right_to_left'])
    expected_ltr = unique_order(scene.metadata['left_to_right'])
    for observed, expected in [(rtl, expected_rtl), (ltr, expected_ltr)]:
        if video_hz == 60:
            assert observed == expected[:-1] or observed == expected, (observed, expected)
        else:
            # Six core ticks per PAL presentation sometimes advance two steps.
            positions = [expected.index(shape) for shape in observed]
            assert positions[0] <= 1 and positions[-1] >= len(expected) - 2
            assert all(1 <= b - a <= 2 for a, b in zip(positions, positions[1:]))
    assert edge_cases >= 17 and fully_clipped >= 1, 'missing partial/fully clipped native cases'
    captures = list(dict.fromkeys(captures))
    assert len(captures) >= (29 if video_hz == 60 else 24), 'too few distinct original bank frames'
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256((ROOT / 'out/wings.rom').read_bytes()).hexdigest(),
        video_hz=video_hz, captured_shapes=len(captures), native_edge_cases=edge_cases, fully_clipped_cases=fully_clipped,
        shapes=[scene.frames[i]['name'] for i in captures],
        checks=['both turn sequence orders', 'held-key edge detection', 'unchanged logical pivot',
                'full-page pixel comparisons', 'partial and fully clipped native frames', 'VBlank publication', 'zero missed deadlines'])
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: both turn directions, held T, {len(captures)} distinct shapes and full-page pixel checks')


if __name__ == '__main__':
    main()
