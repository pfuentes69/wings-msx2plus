"""The cockpit window over the island (docs/cockpit.md), on openMSX.

tools/cockpit_smoke.tcl flies low over map a's island, west then east. The
window must match the converter's model (tools/convert_cockpit.py) in every
snapshot where the page shown holds the buffer's picture, and keep up with
the plane: the picture the window holds must reach the scene the model
gives for the plane's place within a short lag.
"""
import argparse
from pathlib import Path
import shutil
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
LAG_LIMIT = 1.0   # seconds the window may trail the scene (a sample every 0.1 s)


def main():
    warnings.simplefilter('ignore')
    from verify_ships import run
    import convert_cockpit
    from convert_dashboard import arrow_frames
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/cockpit-ntsc')
    args = parser.parse_args()
    out = args.output.resolve()
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rom = ROOT / 'out/mission-flight/mission-flight.rom'
    run(args, out, rom, 'tools/cockpit_smoke.tcl')
    report = (out / 'emulator-report.txt').read_text(errors='replace')
    assert report.rstrip().endswith('PASS'), report[-3000:]
    n = convert_cockpit.SCENE_BYTES
    # Lag: for each sample, how long since the buffer last held the scene
    # the model gives for the plane's place at that sample.
    samples = []
    for line in report.splitlines():
        if not line.startswith('cockpit '): continue
        fields = dict(f.split('=') for f in line.split()[1:])
        scene = bytes(int(v) for v in fields['scene'].split(','))
        x, y, left = int(fields['x']), int(fields['y']), int(fields['left'])
        samples.append((x, 1200 - y, left, scene))
    assert len(samples) > 100, len(samples)
    worst, behind, objects = 0, 0, set()
    for i, (x, alt, left, scene) in enumerate(samples):
        if alt > convert_cockpit.FAR_ALTITUDE: continue
        objects.update(b - 1 for b in scene[8:19] if b)
        # Caught up when the buffer holds the scene of this sample or of
        # the one before (the plane moves between a render and the log).
        held = scene[:n]
        if any(held == convert_cockpit.scene('a', sx, sa, sl) for sx, sa, sl, _ in samples[max(0, i - 1):i + 1]):
            behind = 0
        else:
            behind += 1
            worst = max(worst, behind)
    print(f'{len(samples)} samples; the window trailed the scene at most {worst / 10:.1f} s')
    first = convert_cockpit.FIRST
    shown = {k for k, lo, hi in (('huts', first['HUT'], first['WRECK']), ('dugouts', first['DUGOUT'], first['GUN']))
             if any(lo <= o < hi for o in objects)}
    print(f'targets shown: {sorted(shown)}')
    assert shown == {'huts', 'dugouts'}, shown
    assert worst / 10 <= LAG_LIMIT, worst
    # Snapshots: the window against the model.
    checked = 0
    for line in report.splitlines():
        if not line.startswith('snapshot '): continue
        name, page = line.split()[1], int(line.split()[2])
        cockpit = (out / f'{name}.cockpit').read_bytes()
        if cockpit[n + 1 + page] != cockpit[n]: continue
        want = convert_cockpit.compose(cockpit[:n], arrow_frames())
        vram = (out / f'{name}.vram').read_bytes()
        header = (ROOT / 'src/generated/cockpit_art.h').read_text()
        import re
        wx, wy = (int(re.search(rf'#define COCKPIT_WINDOW_{a} (\d+)', header).group(1)) for a in 'XY')
        for yy in range(24):
            for xx in range(46):
                col, row = wx + xx, page * 256 + 172 + wy + yy
                got = (vram[row * 128 + col // 2] >> (0 if col & 1 else 4)) & 15
                assert got == want[yy * 46 + xx], (name, xx, yy, got, want[yy * 46 + xx])
        checked += 1
    # "THE END" staged its plate in the shown page's rows 212..; the new
    # game's wave frames (rows 212.. of pages 0 and 1, x 48 and 144) are
    # whole again (src/msx/dashboard.c Dashboard_LoadWaves).
    import re as _re
    art = (ROOT / 'src/generated/screen_end_art.c').read_text()
    plate = bytes(int(v, 16) for v in _re.search(r'g_EndPlate\[\d+\] = \{([^}]*)\}', art).group(1).split(',') if v.strip())
    end_page = int(next(l.split()[2] for l in report.splitlines() if l.startswith('snapshot the_end ')))
    vram = (out / 'the_end.vram').read_bytes()
    assert vram[(end_page * 256 + 212) * 128:(end_page * 256 + 212) * 128 + 96] == plate[:96], 'the plate was not staged'
    waves = (ROOT / 'assets_msx/dashboard/waves.sc5').read_bytes()
    for name in [l.split()[1] for l in report.splitlines() if l.startswith('snapshot ')][1:]:
        vram = (out / f'{name}.vram').read_bytes()
        for f in range(12):
            for row in range(11 if f & 3 != 3 else 9):
                wx, wy = (144 if 4 <= f < 8 else 48), 212 + (f & 3) * 11 + (256 if f >= 8 else 0) + row
                assert vram[wy * 128 + wx // 2:wy * 128 + wx // 2 + 48] == waves[(f * 11 + row) * 48:(f * 11 + row) * 48 + 48], (name, 'wave frame', f, row)
    print(f'PASS: cockpit window, {checked} snapshots checked; the wave frames after "THE END"; {args.machine}')


if __name__ == '__main__':
    main()
