"""Ship step 6: the P4 gate scripted on map j's release ROM (docs/ships.md).

tools/ships_smoke.tcl flies the gate in openMSX: rockets destroy the
battleship's first six guns (the ship stays afloat), a landing and the
service's torpedo, two hits sink the battleship (the second torpedo from
the F1 refill cheat), a second landing, a torpedo released out of range runs
out without damage, the destroyer sunk, the mission complete, and a third
landing brings the next mission's briefing. This checks its snapshots: the
ships' state, score and bonuses, the ticker's text drawn from the font,
the dashboard, the tile cache against the ROM, and saves a VRAM preview of
each. Missed frame deadlines are counted, not failed (WINGS_ALLOW_MISSED):
heavy ship scenes still run late (docs/ships.md, Cost)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SHIP_BONUS = (2500, 4500)        # destroyer, battleship (mission_ships.h)
GUN_POINTS = 200
# Smoke-path frames (src/generated/hellcat_frames.h).
ROCKET_FRAMES = set(range(46, 87))
SPLASH_FRAMES = set(range(87, 97))   # spl1..spl6, ric0, 8thscale spl1..spl3
# Missed frame deadlines over the whole run (21 NTSC, 9 PAL on 2026-11-18):
# a regression guard, not a target.
MISSED_LIMIT = 50


def run(args, out, rom):
    env = dict(os.environ, WINGS_ROOT=str(ROOT), WINGS_TEST_OUT=str(out), WINGS_ROM=str(rom),
               WINGS_HEADLESS='1' if args.headless else '0', WINGS_NO_FM='0', WINGS_RECORD='',
               WINGS_ALLOW_MISSED='1', OPENMSX_HOME=str(out / 'openmsx-home'), SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA', str(Path.home() / '.openMSX/share'))
    settings = []
    if args.headless:
        config = out / 'headless.xml'
        config.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings>'
                          '<setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting>'
                          '</settings></settings>')
        settings = ['-setting', str(config)]
    with (out / 'openmsx.log').open('w') as log:
        with subprocess.Popen([shutil.which('openmsx'), '-control', 'stdio', *settings, '-machine', args.machine,
                               '-cart', str(rom), '-romtype', 'ASCII8', '-script', str(ROOT / 'tools/ships_smoke.tcl')],
                              cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE) as emulator:
            # A Tcl error outside a guarded callback leaves openMSX running:
            # stop at the first one the log reports.
            deadline = time.monotonic() + args.timeout
            try:
                while emulator.poll() is None:
                    assert time.monotonic() < deadline, f'openMSX timed out after {args.timeout} s'
                    log.flush()
                    assert 'While executing' not in (out / 'openmsx.log').read_text(errors='replace'), \
                        (out / 'openmsx.log').read_text(errors='replace')[-2000:]
                    time.sleep(1)
                assert emulator.returncode == 0, 'openMSX failed'
            finally:
                if emulator.poll() is None: emulator.kill(); emulator.wait()


def text_rows(text):
    """The ticker's text as 12 rows of pixels (src/msx/message.c): odd
    glyphs get a blank column."""
    from convert_font import glyphs
    height, first, last, font = glyphs()
    rows = [[] for _ in range(height)]
    for c in text:
        width, bits = font[c if first <= c <= last else first]
        for r in range(height): rows[r] += bits[r] + [0] * (width & 1)
    return rows


def ships_state(raw):
    """g_Ships (src/core/ships.h; SDCC packs the struct)."""
    return dict(down=list(raw[0:40]), guns_down=struct.unpack_from('<H', raw, 121)[0],
                splashes=raw[212], hits=struct.unpack_from('<H', raw, 215)[0], present=raw[217],
                hull=list(raw[218:223]), hull_hits=struct.unpack_from('<H', raw, 223)[0],
                step=list(raw[225:229]), sinking=raw[237], left=raw[238])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/ships-ntsc')
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    (out / 'verification.json').unlink(missing_ok=True)
    rom = ROOT / 'out/mission-flight-j/mission-flight.rom'
    data = rom.read_bytes()
    run(args, out, rom)
    assert rom.read_bytes() == data, 'ROM changed during verification'
    report = (out / 'emulator-report.txt').read_text(errors='replace')
    assert report.rstrip().endswith('PASS'), report[-3000:]

    from convert_dashboard import compose, layout, PILOT_WIDTH
    from verify_world_flight import vram_image
    palette = (ROOT / 'assets_msx/mission_a/palette.bin').read_bytes()
    spots = layout()
    snapshots = {}
    for line in report.splitlines():
        if not line.startswith('snapshot '): continue
        _, name, page, world, y, pose, wave, heave, ship, camera = line.split()
        page = int(page)
        def read(suffix): return (out / f'{name}.{suffix}').read_bytes()
        assert read('rom') == data[:32768], (name, 'mapper restoration')
        vram = read('vram')
        game = list(read('game'))
        # The tile cache: every loaded slot holds its strip's 8 tiles (ROM
        # banks from 32, 256 bytes a strip), as 64 rows of 4 bytes at rows
        # 180.. of VRAM page 2 or 3.
        for slot, strip in enumerate(read('slots')):
            if strip == 255: continue
            want = data[32 * 8192 + strip * 256:32 * 8192 + strip * 256 + 256]
            got = b''.join(vram[0x10000 + ((slot >> 5) * 256 + 180 + row) * 128 + (slot & 31) * 4:][:4] for row in range(64))
            assert got == want, (name, 'tile slot', slot, 'strip', strip)
        # The dashboard: ammo, weapon, lives, gauges and score (the pilot
        # window aside).
        gauges = tuple(read('gauges'))
        score = struct.unpack('<I', read('score'))[0]
        hud = compose(ammo=game[4], weapon=game[3], lives=game[2], oil=gauges[0], fuel=gauges[1],
                      oil_lamp=bool(gauges[2] & 1), fuel_lamp=bool(gauges[2] & 2), score=min(score, 999999))
        for row in range(40):
            for col in range(8, 256):
                if spots['pilot_y'] <= row < spots['pilot_y'] + 24 and spots['pilot_x'] <= col < spots['pilot_x'] + PILOT_WIDTH: continue
                value = (vram[page * 32768 + (172 + row) * 128 + col // 2] >> (0 if col & 1 else 4)) & 15
                assert value == hud[row * 256 + col], (name, 'dashboard', col, 172 + row, value, hud[row * 256 + col])
        # The ticker at the top (src/msx/message.c): the text pixel `ticker`
        # at the band's right edge, ink 11 on the sky.
        band, ticker = struct.unpack('<BH', read('band'))
        text = read('text').split(b'\0')[0]
        if band:
            rows = text_rows(text)
            for row in range(band):
                for col in range(8, 256):
                    ring = (ticker + 1 + col) % 256
                    p = ticker - 255 + col
                    want = 11 if 1 <= row <= 12 and 0 <= p < len(rows[0]) and rows[row - 1][p] else 0
                    value = (vram[page * 32768 + row * 128 + ring // 2] >> (0 if ring % 2 else 4)) & 15
                    assert value == want, (name, 'ticker', col, row, value, want, text)
        smoke = read('smoke')
        frames = [smoke[1 + 5 * i + 4] for i in range(smoke[0])]
        state = read('state')
        torpedo = read('torpedo')
        vram_image(vram, palette, int(camera), page, int(heave), struct.unpack('b', read('fine'))[0]).save(out / f'{name}-vram.png')
        snapshots[name] = dict(phase=game[0], lives=game[2], weapon=game[3], stock=game[4], cursor=game[6],
                               world=int(world), y=int(y), camera=int(camera), score=score, band=band,
                               text=text.decode('latin-1') if band else '', frames=frames,
                               scale=read('view')[0], gone=read('gone')[0], ships=ships_state(read('ships')),
                               torpedo=dict(live=torpedo[14], life=torpedo[15]),
                               mission=dict(map=state[8], number=state[9]))

    s = snapshots
    required = ['rank', 'briefing', 'start', 'rockets_fired', 'guns_down', 'landing1_arrest', 'landing1_landed',
                'service_torpedo', 'battleship_hit', 'battleship_struck', 'battleship_sinking', 'battleship_gone',
                'landing2_arrest', 'landing2_landed', 'service_torpedo_again', 'torpedo_running', 'torpedo_expired',
                'destroyer_struck', 'destroyer_sinking', 'destroyer_gone', 'landing3_arrest', 'landing3_landed',
                'mission_briefing', 'mission_two']
    assert set(required) <= s.keys(), set(required) - s.keys()
    def ships(name): return s[name]['ships']
    # The sortie with rockets: 15, both ships afloat.
    start = ships('start')
    assert s['start']['weapon'] == 1 and s['start']['stock'] == 15 and start['present'] == 1
    assert start['hull'][:2] == [1, 2] and start['left'] == 2 and s['start']['gone'] == 0 and not any(start['down'])
    # Rockets in the air, then the battleship's first six guns down: +200
    # each, and the ship is not neutralised (OBJ-02).
    assert set(s['rockets_fired']['frames']) & ROCKET_FRAMES, ('no rocket drawn', s['rockets_fired']['frames'])
    down = ships('guns_down')
    killed = sum(down['down'])
    assert killed >= 2 and sum(down['down'][8:14]) == killed, down['down'][:22]
    assert s['guns_down']['score'] == killed * GUN_POINTS
    assert down['hull'][:2] == [1, 2] and down['left'] == 2 and not down['sinking']
    # The service re-arms with the torpedo: 1.
    assert s['service_torpedo']['phase'] == 7 and s['service_torpedo']['cursor'] == 2
    for name in ('landing1_landed', 'landing2_landed', 'landing3_landed'):
        assert s[name]['y'] == 1160 and s[name]['lives'] == 3, (name, s[name]['y'], s[name]['lives'])
    # The battleship: one hit, then the second (the F1 refill) sinks it.
    hit = ships('battleship_hit')
    assert hit['hull'][:2] == [1, 1] and hit['hull_hits'] == 1 and not hit['sinking'] and hit['left'] == 2
    struck = ships('battleship_struck')
    assert struck['hull'][:2] == [1, 0] and struck['hull_hits'] == 2 and struck['left'] == 2
    sinking = s['battleship_sinking']
    assert sinking['scale'] == 1 and ships('battleship_sinking')['step'][1] >= 30, (sinking['scale'], ships('battleship_sinking')['step'])
    assert sinking['score'] == killed * GUN_POINTS + SHIP_BONUS[1], sinking['score']
    assert sinking['band'] and 'Battleship sunk' in sinking['text'] and '4500' in sinking['text'], sinking['text']
    gone = s['battleship_gone']
    assert gone['gone'] & 2 and ships('battleship_gone')['left'] == 1, (gone['gone'], ships('battleship_gone')['left'])
    # The second landing's service offers the torpedo again.
    assert s['service_torpedo_again']['cursor'] == 2
    # Released out of range: it runs (the wake), then runs out with no hit.
    running = s['torpedo_running']
    assert running['torpedo']['live'] == 2 and set(running['frames']) & SPLASH_FRAMES, (running['torpedo'], running['frames'])
    expired = ships('torpedo_expired')
    assert s['torpedo_expired']['torpedo']['live'] == 0 and expired['hull'][0] == 1 and expired['hull_hits'] == 2
    # The destroyer: one hit sinks it; the bonus and the mission.
    assert ships('destroyer_struck')['hull'][0] == 0 and ships('destroyer_struck')['hull_hits'] == 3
    sinking = s['destroyer_sinking']
    assert sinking['score'] == killed * GUN_POINTS + sum(SHIP_BONUS), sinking['score']
    assert sinking['band'] and 'Destroyer sunk' in sinking['text'] and '2500' in sinking['text'], sinking['text']
    assert s['destroyer_gone']['gone'] == 3 and ships('destroyer_gone')['left'] == 0
    # Mission complete: the third landing goes down to the next mission's
    # briefing; its sortie starts with the ships restored (StartMission).
    brief = s['mission_briefing']
    assert brief['phase'] == 1 and brief['mission']['number'] == 2 and brief['lives'] == 3, brief
    two = s['mission_two']
    restored = ships('mission_two')
    assert two['phase'] == 3 and two['weapon'] == 0 and two['stock'] == 30, two   # the loadout's default: bombs
    assert restored['hull'][:2] == [1, 2] and restored['left'] == 2 and two['gone'] == 0 and not any(restored['down']) \
        and not restored['sinking'] and restored['step'][:2] == [0, 0], restored

    heard = {int(l.split()[1]) for l in report.splitlines() if l.startswith('sound ')}
    assert {4, 5} <= heard, ('effects heard', sorted(heard))
    missed = sum(1 for l in report.splitlines() if l.startswith('missed '))
    overruns = int(next(l.split()[1] for l in report.splitlines() if l.startswith('pan_overruns ')))
    print(f'missed frame deadlines: {missed}; pan step overruns: {overruns}')
    assert missed <= MISSED_LIMIT, ('missed frame deadlines', missed)
    for line in report.splitlines():
        if line.startswith(('torpedo ', 'battleship ', 'destroyer ', 'rockets done', 'touchdown')): print(line)
    summary = dict(machine=args.machine, rom_sha256=hashlib.sha256(data).hexdigest(), missed_deadlines=missed,
                   pan_overruns=overruns, snapshots=snapshots)
    (out / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'PASS: ships {len(snapshots)} snapshots; {args.machine}')


if __name__ == '__main__':
    main()
