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
        local = dict((n, int(v, 16)) for n, v in re.findall(r'^\s+0 (_\w+)\s+([0-9A-F]{8}) ', path.read_text(), re.M))
        anchors = [globals_[n] - local[n] for n in globals_ if n in local]
        if not anchors:
            continue
        base = anchors[0]
        for name, offset in local.items():
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
    counted = collections.Counter()
    for line in (out / 'profile.txt').read_text().splitlines():
        if line.startswith('call '):
            _, name, guns, count = line.split()
            counted[(name, int(guns))] += int(count)
            continue
        pc, bank, render, guns, ret, count = map(int, line.split())
        group = ('render' if render else 'sim/idle') + (' +guns' if guns else '')
        name = resolve(keys, names, pc, bank)
        groups[group][name] += count
        totals[group] += count
        if name.startswith('__') or name in ('BIOS',):
            callers[(group, name)][resolve(keys, names, ret, bank)] += count
    for group in sorted(groups):
        total = totals[group]
        print(f'\n== {group}: {total} samples = {total * args.period * 1000:.0f} ms emulated')
        for name, count in groups[group].most_common(args.top):
            extra = ''
            if (group, name) in callers:
                top = callers[(group, name)].most_common(3)
                extra = '  <- ' + ', '.join(f'{caller} {c}' for caller, c in top)
            print(f'{100 * count / total:6.2f}% {count:7d}  {name}{extra}')
    if counted:
        print('\n== calls (gameplay only): name guns-idle guns-active')
        for name in sorted({n for n, _ in counted}):
            print(f'{name:28} {counted[(name, 0)]:8d} {counted[(name, 1)]:8d}')


if __name__ == '__main__':
    main()
