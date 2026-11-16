"""Sample-profile the release mission ROM during the P0/P1 smoke run on openMSX.

Runs tools/p0_smoke.tcl with tools/profile_sampler.tcl and prints where gameplay
CPU time goes, split by simulation/render and guns idle/active. Samples are in
emulated time, so the profile does not change the game's timing.
"""
import argparse
import bisect
import collections
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
# Leaf routines whose samples are also attributed to the caller (word at SP).
LEAF_HELPERS = {'BIOS', '_VDP_CommandWait', '_VDP_CommandSetupR32', '_VDP_CommandSetupR36', '_memcpy'}
BUILD = ROOT / 'out/mission-flight'


def symbols():
    """Code addresses: map globals plus module statics rebased from .sym files."""
    table, modules = {}, collections.defaultdict(dict)
    for addr, name, module in re.findall(r'^\s+([0-9A-F]{8})\s+(_\w+)\s+(\w*)\s*$',
                                         (BUILD / 'mission-flight.map').read_text(), re.M):
        if name.startswith(('s__', 'l__')):
            continue
        table[int(addr, 16)] = name
        if module:
            modules[module][name] = int(addr, 16)
    for module, globals_ in modules.items():
        path = BUILD / f'{module}.sym'
        if not path.exists():
            continue
        # Symbols per area: resident code is in area 0, a banked module's in
        # its segment's area. Rebase only the area holding the code globals.
        areas = collections.defaultdict(dict)
        for area, n, v in re.findall(r'^\s+(\d+) (_\w+)\s+([0-9A-F]{8}) ', path.read_text(), re.M):
            areas[area][n] = int(v, 16)
        code = [n for n, a in globals_.items() if a < 0xC000 or a > 0xFFFF]   # not RAM
        found = [(area, globals_[n] - local[n]) for area, local in areas.items() for n in code if n in local]
        if not found:
            continue
        area, base = collections.Counter(found).most_common(1)[0][0]
        for name, offset in areas[area].items():
            table.setdefault(base + offset, name)
    keys = sorted(table)
    return keys, [table[k] for k in keys]


def resolve(keys, names, pc, bank):
    full = (bank << 16) | pc if 0xA000 <= pc < 0xC000 else pc
    if pc < 0x4000:
        return 'BIOS'
    if pc >= 0xC000:
        return 'RAM'
    i = bisect.bisect_right(keys, full) - 1
    return names[i] if i >= 0 else hex(full)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--period', type=float, default=0.0002, help='emulated seconds between samples')
    parser.add_argument('--output', type=Path, default=ROOT / 'tools/.build/profile-ntsc')
    parser.add_argument('--top', type=int, default=25)
    parser.add_argument('--reuse', action='store_true', help='analyse an existing profile.txt')
    parser.add_argument('--count', nargs='*', default=[], help='resident functions whose calls to count')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rom = BUILD / 'mission-flight.rom'
    keys, names = symbols()
    if not args.reuse:
        where = {n: k for k, n in zip(keys, names)}
        calls = ' '.join(f'{n}:{where["_" + n]}' for n in args.count)
        env = dict(os.environ, WINGS_PROFILE_CALLS=calls, WINGS_ROOT=str(ROOT), WINGS_TEST_OUT=str(out), WINGS_HEADLESS='1',
                   WINGS_PROFILE_PERIOD=str(args.period), OPENMSX_HOME=str(out / 'openmsx-home'),
                   SDL_AUDIODRIVER='dummy')
        env.setdefault('OPENMSX_USER_DATA', str(Path.home() / '.openMSX/share'))
        config = out / 'headless.xml'
        config.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings>'
                          '<setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting>'
                          '</settings></settings>')
        with (out / 'openmsx.log').open('w') as log:
            subprocess.run([shutil.which('openmsx'), '-control', 'stdio', '-setting', str(config), '-machine', args.machine,
                            '-cart', str(rom), '-romtype', 'ASCII8', '-script', str(ROOT / 'tools/p0_smoke.tcl'),
                            '-script', str(ROOT / 'tools/profile_sampler.tcl')],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                           timeout=1800, check=True)
        report = (out / 'emulator-report.txt').read_text()
        if not report.rstrip().endswith('PASS'):
            print('WARNING: smoke run did not pass; profile covers the run up to the failure')
    groups = collections.defaultdict(collections.Counter)
    callers = collections.defaultdict(collections.Counter)
    totals = collections.Counter()
    busy = collections.Counter()      # samples with the VDP command engine running
    busy_in = collections.Counter()   # render samples by function while the VDP is busy
    waits = collections.defaultdict(collections.Counter)   # VDP waits by issuing function
    counted = collections.Counter()
    for line in (out / 'profile.txt').read_text().splitlines():
        if line.startswith('call '):
            _, name, guns, count = line.split()
            counted[(name, int(guns))] += int(count)
            continue
        fields = list(map(int, line.split()))
        if len(fields) == 8: fields.insert(7, 0)       # profiles from before ret2
        pc, bank, render, guns, ret, vdp, carrier, ret2, count = fields
        group = ('render' if render else 'sim/idle') + (' +guns' if guns else '')
        if carrier == 2 and render: group = 'render heavy (>85 ms)'
        elif carrier and render: group = 'render over carrier'
        elif carrier: group = 'sim/idle over carrier'
        name = resolve(keys, names, pc, bank)
        groups[group][name] += count
        totals[group] += count
        busy[group] += count * vdp
        if render and vdp:
            busy_in[name] += count
        if name.startswith('__') or name in LEAF_HELPERS:
            callers[(group, name)][resolve(keys, names, ret, bank)] += count
        # Waiting for the VDP: charge the function that issued the command.
        if render and name == '_VDP_CommandWait':
            caller = resolve(keys, names, ret, bank)
            if caller in ('_VDP_CommandSetupR32', '_VDP_CommandSetupR36'):
                caller = resolve(keys, names, ret2, bank)
            waits[group][caller] += count
    carrier_frames = sum(c for (n, g), c in counted.items() if n == 'carrier_frames')
    heavy_frames = sum(c for (n, g), c in counted.items() if n == 'heavyrender_frames')
    per_frame = {'render over carrier': carrier_frames, 'render heavy (>85 ms)': heavy_frames}
    for group in sorted(groups):
        total = totals[group]
        if per_frame.get(group):
            print(f'\n({group}: {per_frame[group]} frames, {total * args.period * 1000 / per_frame[group]:.1f} ms each)')
        print(f'\n== {group}: {total} samples = {total * args.period * 1000:.0f} ms emulated, '
              f'VDP command engine busy {100 * busy[group] / total:.1f}%')
        for name, count in groups[group].most_common(args.top):
            if per_frame.get(group):
                name = f'{name} ({count * args.period * 1000 / per_frame[group]:.2f} ms/frame)'
            extra = ''
            if (group, name) in callers:
                top = callers[(group, name)].most_common(3)
                extra = '  <- ' + ', '.join(f'{caller} {c}' for caller, c in top)
            print(f'{100 * count / total:6.2f}% {count:7d}  {name}{extra}')
    for group in sorted(waits):
        frames = per_frame.get(group)
        print(f'\n== {group}: waiting for the VDP, by the function issuing the next command')
        for name, count in waits[group].most_common(12):
            per = f' ({count * args.period * 1000 / frames:.2f} ms/frame)' if frames else ''
            print(f'{count:7d}  {name}{per}')
    costs = [(int(n.split('_')[2]), int(n.split('_')[3]), c) for (n, g), c in counted.items()
             if n.startswith('frame_cost_')]
    rebuilds = sum(c for (n, g), c in counted.items() if n.startswith('rebuild_cost_'))
    if busy_in:
        print('\n== render functions sampled while the VDP command engine is busy (CPU overlaps VDP)')
        for name, count in busy_in.most_common(8):
            print(f'{count:7d}  {name}')
    if costs:
        frames = sum(c for _, _, c in costs)
        totals_ms = sorted(((s + d, s, d) for s, d, c in costs for _ in range(c)))
        print(f'\n== frame cost over {frames} rendered gameplay frames, excluding {rebuilds} view rebuilds (ms)')
        print(f'   simulation: mean {sum(s * c for s, _, c in costs) / frames:.1f}, max {max(s for s, _, _ in costs)}')
        print(f'   render:     mean {sum(d * c for _, d, c in costs) / frames:.1f}, max {max(d for _, d, _ in costs)}')
        print(f'   sim+render: mean {sum(t for t, _, _ in totals_ms) / frames:.1f}, '
              f'p99 {totals_ms[int(frames * 0.99)][0]}, max {totals_ms[-1][0]} '
              f'(worst: sim {totals_ms[-1][1]} + render {totals_ms[-1][2]})')
    if counted:
        print('\n== calls (gameplay only): name guns-idle guns-active')
        heavy = sorted(((int(n.split('_')[1]) + int(n.split('_')[2]), n) for (n, g), c in counted.items()
                        if n.startswith('heavy_')), reverse=True)
        if heavy:
            print('\n== heaviest gameplay frames (sim+render ms, location):')
            for total, n in heavy[:12]: print(f'{total:5d}  {n}')
        for name in sorted({n for n, _ in counted if not n.startswith(('frame_cost_', 'rebuild_cost_', 'publish_tstates_', 'heavy_', 'heavyrender_', 'carrier_frames'))}):
            print(f'{name:28} {counted[(name, 0)]:8d} {counted[(name, 1)]:8d}')


if __name__ == '__main__':
    main()
