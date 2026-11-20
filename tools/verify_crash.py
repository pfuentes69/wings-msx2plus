"""The player's crash on openMSX (docs/crash.md, after
docs/research/amiga-player-crash.md).

tools/crash_smoke.tcl crashes three planes on map a: into the sea (waited
out), into the island (fire held to end it) and, the last, onto the deck
with a dead engine (the game ends). From the log every 0.1 s and the
snapshots this checks the modes (4 slide, 6 sinking, 8 wreck), the slide,
the sinking depth and its waterline, the wreck art, the bursts and smoke,
the island damage, and the timings (12 s, or fire after 2.4 s).
"""
import argparse
from pathlib import Path
import shutil
import struct
import sys
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
DEAD, SINKING, WRECK = 3, 4, 5


def samples(report):
    rows = []
    for line in report.splitlines():
        if not line.startswith('plane '): continue
        rows.append({k: float(v) if k == 't' else int(v) for k, v in (f.split('=') for f in line.split()[1:])})
    return rows


def marks(report):
    out = {}
    for line in report.splitlines():
        if line.startswith('mark '):
            fields = line.split()
            out[fields[1]] = {k: float(v) if k == 't' else int(v) for k, v in (f.split('=') for f in fields[2:])}
    return out


def composite(out, name, page, world, y, pose, wave, heave, ship, camera, scene, terrain):
    """The snapshot's playfield against the pixel model (as verify_p0)."""
    from verify_world_flight import expected_pixels, island_background, vram_row
    from convert_dashboard import arrow_frames
    import convert_cockpit
    game = list((out / f'{name}.game').read_bytes())
    combat = (out / f'{name}.combat').read_bytes()
    vram = (out / f'{name}.vram').read_bytes()
    fine = struct.unpack('b', (out / f'{name}.fine').read_bytes())[0]
    scale, wave_view, pilot = (out / f'{name}.view').read_bytes()
    cockpit = (out / f'{name}.cockpit').read_bytes()
    n = convert_cockpit.SCENE_BYTES
    pilot = convert_cockpit.compose(cockpit[:n], arrow_frames()) if cockpit[n + 1 + page] == cockpit[n] != 255 else None
    stage, depth, lift_tick = (out / f'{name}.lift').read_bytes()
    crew = (out / f'{name}.crew').read_bytes()[0]
    projectiles = [dict(zip(('x', 'y', 'vx', 'vy', 'life', 'kind'), struct.unpack_from('<HHbbBB', combat, i * 8))) for i in range(18)]
    flight = (out / f'{name}.flight').read_bytes()
    wheel, gear, rope = (out / f'{name}.wheel').read_bytes()
    band, ticker = struct.unpack('<BH', (out / f'{name}.band').read_bytes())
    assert band == 0, (name, 'ticker shown')
    raw = (out / f'{name}.smoke').read_bytes()
    smoke = [struct.unpack_from('<HhB', raw, 1 + 5 * i) for i in range(raw[0])]
    expected = expected_pixels(scene, pose, world, y, camera,
        island_background((ROOT / 'assets_msx/mission_a' / ('far.indices' if scale == 8 else 'scene.indices')).read_bytes(),
                          scale, (out / f'{name}.island').read_bytes()),
        terrain['far_width'] if scale == 8 else terrain['width'], scale, wave, pilot, heave, ship,
        projectiles, game[4], game[3], game[2], crew, False, depth, stage != 1, flash=combat[158],
        gauges=tuple((out / f'{name}.gauges').read_bytes()), crash=(out / f'{name}.crash').read_bytes()[0],
        wheel=wheel, gear=gear, deck_level=False, rope=rope, facing_left=bool(flight[11]),
        smoke=[(x & 0xFFFF, row, frame) for x, row, frame in smoke],
        score=struct.unpack('<I', (out / f'{name}.score').read_bytes())[0], fine=fine, band=band,
        sink=(out / f'{name}.sink').read_bytes()[0] if flight[12] == SINKING else None)
    for row in range(212):
        for col in range(8, 256):
            ring = col if row >= 172 else (camera + col) % 256
            sy = row if row >= 172 else vram_row(row, fine, heave)
            want = expected[row][col]
            if want is None: continue
            value = vram[page * 32768 + sy * 128 + ring // 2]
            value = (value >> (0 if ring % 2 else 4)) & 15
            assert value == want, (name, 'composite', col, row, value, want)


def main():
    warnings.simplefilter('ignore')
    from verify_ships import run
    from verify_world_flight import vram_image
    from aircraft_scene import AircraftScene
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--reuse', action='store_true', help='check the last run again')
    parser.add_argument('--timeout', type=float, default=900)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/crash-ntsc')
    args = parser.parse_args()
    out = args.output.resolve()
    if not args.reuse:
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        run(args, out, ROOT / 'out/mission-flight/mission-flight.rom', 'tools/crash_smoke.tcl')
    report = (out / 'emulator-report.txt').read_text(errors='replace')
    assert report.rstrip().endswith('PASS'), report[-3000:]
    palette = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    scene, terrain = AircraftScene(), json.loads((ROOT / 'assets_msx/mission_a/manifest.json').read_text())
    snaps = {}
    for line in report.splitlines():
        if not line.startswith('snapshot '): continue
        name, *v = line.split()[1:]
        page, world, y, pose, wave, heave, ship, camera = map(int, v)
        fine = struct.unpack('b', (out / f'{name}.fine').read_bytes())[0]
        vram_image((out / f'{name}.vram').read_bytes(), palette, camera, page, heave, fine).save(out / f'{name}-vram.png')
        composite(out, name, page, world, y, pose, wave, heave, ship, camera, scene, terrain)
        flight = (out / f'{name}.flight').read_bytes()
        snaps[name] = dict(mode=flight[12], left=flight[11], y=y, crash=(out / f'{name}.crash').read_bytes()[0],
                           sink=(out / f'{name}.sink').read_bytes()[0])
    rows, m = samples(report), marks(report)
    t = lambda key: m[key]['t']
    # 1. The sea: a slide of about a second, then 12 s sinking; the next plane.
    assert 0.5 < t('sea_sinking') - t('sea_contact') < 1.6, (t('sea_contact'), t('sea_sinking'))
    assert 12.0 <= t('sea_next_plane') - t('sea_sinking') < 13.0, t('sea_next_plane') - t('sea_sinking')
    assert m['sea_next_plane']['lives'] == 2
    sinking = [r for r in rows if r['mode'] == SINKING and t('sea_sinking') <= r['t'] < t('sea_next_plane')]
    assert all(r['y'] == 1198 and r['depth'] == r['clock'] // 3 for r in sinking), 'altitude 2, a pixel every 3 ticks'
    assert max(r['depth'] for r in sinking) >= 48
    assert all(r['oil'] == 0 and r['crash'] == 255 for r in sinking)
    assert snaps['sea_slide']['mode'] == DEAD and snaps['sea_sunk']['sink'] >= 30
    # 2. The island: the wreck (hcrf, facing left) burns; fire ends it after 2.4 s.
    assert 0.5 < t('island_wreck') - t('island_contact') < 1.8
    assert snaps['wreck_1']['mode'] == WRECK and snaps['wreck_1']['crash'] == 1 and snaps['wreck_1']['y'] == 1198
    burning = [r for r in rows if r['mode'] == WRECK and t('island_wreck') <= r['t'] < t('fire_held')]
    assert max(r['smoke'] for r in burning) >= 3, 'the wreck smokes'
    assert t('island_next_plane') - t('island_wreck') < 2.4 + 1.6, t('island_next_plane') - t('island_wreck')
    assert m['island_next_plane']['lives'] == 1
    # 3. The last plane: dead engine, onto the deck (35 = 33 + 2), burns 12 s, game over.
    assert m['deck_wreck']['y'] == 1165 and snaps['deck_wreck']['crash'] == 0
    assert 12.0 <= t('game_over') - t('deck_wreck') < 13.0, t('game_over') - t('deck_wreck')
    assert m['game_over']['lives'] == 0
    print(f'PASS: the crash: sea (slide {t("sea_sinking") - t("sea_contact"):.1f} s, next plane '
          f'{t("sea_next_plane") - t("sea_sinking"):.1f} s), island wreck (fire: {t("island_next_plane") - t("island_wreck"):.1f} s), '
          f'deck wreck, game over; {len(snaps)} snapshots against the model; {args.machine}')


if __name__ == '__main__':
    main()
