"""Enemy fighters on map j (docs/enemy-planes.md, step 5).

tools/fighters_smoke.tcl flies three phases on map j's release ROM:
1. into the destroyer's window: two fighters launch 100 ticks apart and the
   parked planes on the decks go from 10 to 8 (drawn);
2. one closes from behind and attacks: it fires (the muzzle flash, the gun
   sound) and its hits cost oil;
3. it is shot down (its evasions pinned, as in tools/planes_smoke.tcl, and
   the oil kept full against the other fighter); the kill counts.

The ships' guns are set destroyed and torpedo planes kept off, so the
damage measured is the fighters'. Missed frame deadlines are counted."""
import argparse
from pathlib import Path
import struct

from verify_ships import run
from convert_mission import TILE_BANK  # the tile strips' first bank

ROOT = Path(__file__).resolve().parents[1]
PLANE = 40
# 28 NTSC with the centred camera, 38 with its lead; 16 after the
# optimisation pass (2026-11-19: the parked list cached, quiet steps batched).
MISSED_LIMIT = 30
FRAME_PARKED = (99 + 20, 99 + 21)            # jp21, jp22 (hellcat_frames.h)
FRAME_FLASH = tuple(range(121, 125))         # fc10, fd10, fc1a, fd1a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/fighters-ntsc')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    rom = ROOT / 'out/mission-flight-j/mission-flight.rom'
    data = rom.read_bytes()
    run(args, out, rom, script='tools/fighters_smoke.tcl')
    assert rom.read_bytes() == data, 'ROM changed during verification'
    report = (out / 'emulator-report.txt').read_text(errors='replace')
    assert report.rstrip().endswith('PASS'), report[-3000:]

    from convert_dashboard import compose, layout, PILOT_WIDTH, KILL_ICONS_MAX
    from verify_world_flight import vram_image
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
        for slot, strip in enumerate(read('slots')):
            if strip == 255: continue
            want = data[TILE_BANK * 8192 + strip * 256:TILE_BANK * 8192 + strip * 256 + 256]
            got = b''.join(vram[0x10000 + ((slot >> 5) * 256 + 180 + row) * 128 + (slot & 31) * 4:][:4] for row in range(64))
            assert got == want, (name, 'tile slot', slot)
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
        smoke = read('smoke')
        frames = [smoke[1 + 5 * i + 4] for i in range(smoke[0])]
        vram_image(vram, palette, int(camera), page, int(heave), struct.unpack('b', read('fine'))[0]).save(out / f'{name}-vram.png')
        s[name] = dict(phase=game[0], kills=kills, oil=state[14], fighters=planes[162], parked=planes[196],
                       firing=any(planes[i * PLANE] == 2 and planes[i * PLANE + 12] for i in range(4)),
                       frames=frames, gun=read('soundgun')[0])

    required = ['start', 'launched', 'attacked', 'damaged', 'fighter_down']
    assert set(required) <= s.keys(), set(required) - s.keys()
    assert s['start']['parked'] == 0 or s['start']['parked'] == 10   # refreshed on the first tick
    launched = s['launched']
    assert launched['fighters'] == 2 and launched['parked'] == 8, launched
    assert set(launched['frames']) & set(FRAME_PARKED), ('no parked plane drawn', launched['frames'])
    attacked = s['attacked']
    assert attacked['firing'] and attacked['gun'] >= 11, attacked
    # The attacker holds 130 px behind: on the 256-px MSX view (the player
    # centred) it and its flash are just off the edge, so no flash is
    # required in the snapshots (docs/enemy-planes.md, open question).
    assert s['damaged']['oil'] < 128, s['damaged']
    down = s['fighter_down']
    assert down['kills'] == 1 and down['fighters'] == 1, down
    missed = sum(1 for l in report.splitlines() if l.startswith('missed '))
    print(f'missed frame deadlines: {missed}')
    assert missed <= MISSED_LIMIT, missed
    flashes = sum(f in FRAME_FLASH for n in s for f in s[n]['frames'])
    print(f'muzzle flashes in the snapshots: {flashes}')
    for line in report.splitlines():
        if line.startswith(('launched', 'firing', 'hit:', 'target', 'shot down')): print(line)
    print(f'PASS: fighters {len(s)} snapshots; {args.machine}')


if __name__ == '__main__':
    main()
