"""Boot the ROM, exercise real keyboard input, and verify both SCREEN 5 pages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator', default=shutil.which('openmsx'))
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/screen5-smoke')
    args = parser.parse_args()
    if not args.emulator:
        parser.error('openmsx is not installed/on PATH')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'emulator-report.txt'
    report.unlink(missing_ok=True)
    env = dict(os.environ, OPENMSX_HOME=str(output / 'openmsx-home'),
               WINGS_ROOT=str(ROOT), WINGS_TEST_OUT=str(output), SDL_AUDIODRIVER='dummy')
    # Isolate writes while retaining the user's custom machine definitions/ROMs.
    personal_home = Path(os.environ.get('OPENMSX_HOME', Path.home() / '.openMSX'))
    env.setdefault('OPENMSX_USER_DATA', str(personal_home / 'share'))
    command = [args.emulator, '-machine', args.machine, '-cart', str(ROOT / 'out/wings.rom'),
               '-script', str(ROOT / 'tools/screen5_smoke.tcl')]
    with (output / 'openmsx.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=45, check=True)
    text = report.read_text()
    if not text.rstrip().endswith('PASS'):
        raise RuntimeError(f'emulator checks did not finish; inspect {output}')
    palette = (ROOT / 'assets_msx/hellcat/palette.bin').read_bytes()
    states = [('initial', 'hc05', 0), ('key1', 'hc01', 1), ('held1', 'hc01', 1),
              ('key3', 'hc09', 0), ('return2', 'hc05', 1)]
    for name, frame, page in states:
        packed = (ROOT / f'assets_msx/hellcat/{frame}.sc5').read_bytes()
        vram = (output / (name + '.vram')).read_bytes()
        assert (output / (name + '.palette')).read_bytes() == palette, name + ' palette mismatch'
        regs = (output / (name + '.regs')).read_bytes()
        assert regs[0] & 14 == 6 and regs[1] & 64, name + ' is not visible SCREEN 5'
        assert regs[9] & 128, name + ' is not 212 lines'
        base = page * 32768
        for y in range(32):
            address = base + (88 + y) * 128 + 52
            assert vram[address:address + 24] == packed[y * 24:(y + 1) * 24], f'{name}: row {y} differs'
        # The surrounding scene must remain entirely sky.
        for y in range(212):
            row = bytearray(vram[base + y * 128:base + (y + 1) * 128])
            if 88 <= y < 120:
                row[52:76] = bytes(24)
            assert not any(row), f'{name}: unexpected pixels in scene row {y}'
    timings = [float(line.split()[1]) for line in text.splitlines() if line.startswith('render_ms ')]
    latencies = [float(line.split()[1]) for line in text.splitlines() if line.startswith('selection_latency_ms ')]
    assert len(timings) == 3 and len(latencies) == 3, 'missing profiling samples'
    assert text.splitlines().count('flip_in_vblank 1') == 3, 'page flips were not all in VBlank'
    assert max(timings) < 1000 / 60, 'render exceeds one NTSC frame'
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256((ROOT / 'out/wings.rom').read_bytes()).hexdigest(),
                   verified_snapshots=len(states), render_ms=timings, selection_latency_ms=latencies,
                   checks=['keyboard selections and held key', 'VRAM rows', 'palette bytes', 'SCREEN 5 / 212 lines',
                           'page flips during VBlank', 'no stale pixels outside drawing areas'])
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: {len(states)} snapshots; render {min(timings):.2f}–{max(timings):.2f} ms; screenshots in {output}')


if __name__ == '__main__':
    main()
