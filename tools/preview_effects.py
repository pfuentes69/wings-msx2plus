#!/usr/bin/env python3
"""Record each one-shot effect alone, as the game plays it, to WAV files:
OUTPUT/effects-fm.wav (MSX-MUSIC with the PSG) and OUTPUT/effects-psg.wav
(the PSG alone). Needs openMSX and the built mission ROM. The order is boom,
splash, clang, screech, scream, 1.5 s apart (docs/sound-effects.md)."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def record(output, machine, no_fm):
    with tempfile.TemporaryDirectory() as home:
        settings = Path(home) / 'headless.xml'
        settings.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings>'
                            '<setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting>'
                            '</settings></settings>')
        env = dict(os.environ, WINGS_ROOT=str(ROOT), WINGS_RECORD=str(output), WINGS_NO_FM='1' if no_fm else '0',
                   OPENMSX_HOME=home, SDL_AUDIODRIVER='dummy')
        env.setdefault('OPENMSX_USER_DATA', str(Path.home() / '.openMSX/share'))
        subprocess.run([shutil.which('openmsx'), '-setting', str(settings), '-machine', machine,
                        '-cart', str(ROOT / 'out/mission-flight/mission-flight.rom'), '-romtype', 'ASCII8',
                        '-script', str(ROOT / 'tools/preview_effects.tcl')], env=env, check=True, timeout=300,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not output.exists(): raise SystemExit(f'no recording: {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, no_fm in (('effects-fm.wav', False), ('effects-psg.wav', True)):
        record(args.output.resolve() / name, args.machine, no_fm)
        print(args.output / name)


if __name__ == '__main__':
    main()
