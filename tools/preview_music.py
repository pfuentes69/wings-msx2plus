#!/usr/bin/env python3
"""Record the music as the game plays it, to WAV files: OUTPUT/music-fm.wav
(MSX-MUSIC) and OUTPUT/music-psg.wav (the PSG alone), each with a .log of
when the player starts and stops. From the end of loading: the title and
credits (subsong 1), the story (subsong 2) from about 20 s, rank selection
(subsong 4) after Escape at --rank-at seconds (docs/music.md). Needs openMSX
and the built mission ROM."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def record(output, machine, no_fm, rank_at, stop_at):
    with tempfile.TemporaryDirectory() as home:
        settings = Path(home) / 'headless.xml'
        settings.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings>'
                            '<setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting>'
                            '</settings></settings>')
        env = dict(os.environ, WINGS_ROOT=str(ROOT), WINGS_RECORD=str(output), WINGS_NO_FM='1' if no_fm else '0',
                   WINGS_RANK_AT=str(rank_at), WINGS_STOP_AT=str(stop_at), OPENMSX_HOME=home, SDL_AUDIODRIVER='dummy')
        env.setdefault('OPENMSX_USER_DATA', str(Path.home() / '.openMSX/share'))
        subprocess.run([shutil.which('openmsx'), '-setting', str(settings), '-machine', machine,
                        '-cart', str(ROOT / 'out/mission-flight/mission-flight.rom'), '-romtype', 'ASCII8',
                        '-script', str(ROOT / 'tools/preview_music.tcl')], env=env, check=True, timeout=600,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not output.exists(): raise SystemExit(f'no recording: {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--machine', default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--rank-at', type=float, default=50)
    parser.add_argument('--stop-at', type=float, default=85)
    parser.add_argument('--psg-only', action='store_true')
    parser.add_argument('--fm-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, no_fm in (('music-fm.wav', False), ('music-psg.wav', True)):
        if (no_fm and args.fm_only) or (not no_fm and args.psg_only): continue
        record(args.output.resolve() / name, args.machine, no_fm, args.rank_at, args.stop_at)
        print(args.output / name)


if __name__ == '__main__':
    main()
