"""Enemy planes on map a (docs/enemy-planes.md, steps 1..3).

tools/planes_smoke.tcl flies four phases on map a's release ROM:
1. a torpedo plane chased west and shot down by the gun: +350, it falls,
   comes to rest and the kill counts (dashboard "01" and an icon);
2. a torpedo plane's drop: its torpedo hits the carrier (hull 4 -> 3), the
   pilot window's arrow showing while it is armed;
3. another's torpedo carpet-bombed before it reaches the carrier;
4. the carrier at one hit left: the next torpedo sinks it, and the crash
   that follows ends the game.

During the chase the script pins the target's altitude and its turn
countdown: a chased torpedo plane weaves and breaks after hits (both
unit-tested in tests/test_planes.py). Missed frame deadlines are counted."""
import argparse
import os
from pathlib import Path
import struct

from verify_ships import run

ROOT = Path(__file__).resolve().parents[1]
PLANE = 40          # bytes per Plane (SDCC packs)
MISSED_LIMIT = 30


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/planes-ntsc')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    rom = ROOT / 'out/mission-flight/mission-flight.rom'
    data = rom.read_bytes()
    run(args, out, rom, script='tools/planes_smoke.tcl')
    assert rom.read_bytes() == data, 'ROM changed during verification'
    report = (out / 'emulator-report.txt').read_text(errors='replace')
    assert report.rstrip().endswith('PASS'), report[-3000:]

    from convert_dashboard import compose, layout, PILOT_WIDTH, arrow_frames, KILL_ICONS_MAX
    from verify_world_flight import vram_image
    import re
    header = (ROOT / 'src/generated/dashboard.h').read_text()
    define = lambda n: int(re.search(rf'#define {n} (\d+)', header)[1])
    pilot_x, pilot_y = define('HUD_PILOT_X'), define('HUD_PILOT_Y')
    arrows = arrow_frames()
    palette = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    spots = layout()
    s = {}
    for line in report.splitlines():
        if not line.startswith('snapshot '): continue
        _, name, page, world, y, pose, wave, heave, ship, camera = line.split()
        page = int(page)
        def read(suffix): return (out / f'{name}.{suffix}').read_bytes()
        vram, game, state = read('vram'), list(read('game')), read('state')
        score, kills = struct.unpack_from('<IH', state, 0)
        # Every loaded tile-cache slot against the ROM.
        for slot, strip in enumerate(read('slots')):
            if strip == 255: continue
            want = data[32 * 8192 + strip * 256:32 * 8192 + strip * 256 + 256]
            got = b''.join(vram[0x10000 + ((slot >> 5) * 256 + 180 + row) * 128 + (slot & 31) * 4:][:4] for row in range(64))
            assert got == want, (name, 'tile slot', slot)
        # The dashboard with the kills (digits and icons), the pilot window aside.
        gauges = tuple(read('gauges'))
        hud = compose(ammo=game[4], weapon=game[3], lives=game[2], oil=gauges[0], fuel=gauges[1],
                      oil_lamp=bool(gauges[2] & 1), fuel_lamp=bool(gauges[2] & 2), score=min(score, 999999),
                      kills=min(kills, 99), kill_icons=min(kills, KILL_ICONS_MAX))
        if game[0] == 3:
            for row in range(40):
                for col in range(8, 256):
                    if spots['pilot_y'] <= row < spots['pilot_y'] + 24 and spots['pilot_x'] <= col < spots['pilot_x'] + PILOT_WIDTH: continue
                    value = (vram[page * 32768 + (172 + row) * 128 + col // 2] >> (0 if col & 1 else 4)) & 15
                    assert value == hud[row * 256 + col], (name, 'dashboard', col, 172 + row, value, hud[row * 256 + col])
        planes = read('planes')
        slots = [dict(state=planes[i * PLANE], beh=planes[i * PLANE + 1], health=struct.unpack_from('<h', planes, i * PLANE + 4)[0],
                      x=struct.unpack_from('<h', planes, i * PLANE + 24)[0], alt=struct.unpack_from('<h', planes, i * PLANE + 30)[0])
                 for i in range(4)]
        ships = read('ships')
        enemy = read('enemy')
        vram_image(vram, palette, int(camera), page, int(heave), struct.unpack('b', read('fine'))[0]).save(out / f'{name}-vram.png')
        s[name] = dict(phase=game[0], lives=game[2], world=int(world), score=score, kills=kills, planes=slots,
                       carrier=ships[222], torpedo=enemy[14], vram=vram, page=page)

    required = ['start', 'shot_down', 'gun_kill', 'armed', 'carrier_hit', 'torpedo_destroyed', 'carrier_sunk', 'game_over']
    assert set(required) <= s.keys(), set(required) - s.keys()
    assert s['start']['kills'] == 0 and s['start']['carrier'] == 4
    down = [p for p in s['shot_down']['planes'] if p['state'] == 4]
    assert down and down[0]['health'] < 96 and s['shot_down']['score'] >= 350, s['shot_down']
    assert s['shot_down']['kills'] == 0   # counted at rest
    assert s['gun_kill']['kills'] == 1 and not any(p['state'] for p in s['gun_kill']['planes']), s['gun_kill']
    # The arrow: ltar when the player is right of the plane (or level), rtar
    # left of it, at the pilot window's top centre, over the view.
    a = s['armed']
    armed = [p for p in a['planes'] if p['state'] and p['beh'] & 7 == 4]
    assert armed, a['planes']
    which = 0 if a['world'] - armed[0]['x'] >= 0 else 1
    pixels, ax = arrows[which]
    for yy in range(5):
        for xx in range(16):
            v = pixels[yy * 16 + xx]
            if not v: continue
            col, row = pilot_x + ax + xx, 172 + pilot_y + yy
            got = (a['vram'][a['page'] * 32768 + row * 128 + col // 2] >> (0 if col & 1 else 4)) & 15
            assert got == v, ('arrow', which, xx, yy, got, v)
    assert s['carrier_hit']['carrier'] == 3
    assert s['torpedo_destroyed']['carrier'] == 3 and s['torpedo_destroyed']['torpedo'] == 0
    assert s['carrier_sunk']['carrier'] == 0
    assert s['game_over']['phase'] == 8, s['game_over']['phase']
    missed = sum(1 for l in report.splitlines() if l.startswith('missed '))
    print(f'missed frame deadlines: {missed}')
    assert missed <= MISSED_LIMIT, missed
    for line in report.splitlines():
        if line.startswith(('shot down', 'running', 'carrier', 'torpedo destroyed', 'torpedo plane')): print(line)
    print(f'PASS: planes {len(s)} snapshots; {args.machine}')


if __name__ == '__main__':
    main()
