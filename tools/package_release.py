#!/usr/bin/env python3
"""Package a release for real hardware: the built mission ROM (map a,
out/mission-flight/mission-flight.rom) as WOFMSX2P.ROM with README.TXT
(docs/release/README.txt, the version and the ROM's SHA-256 filled in, CRLF
line ends for MSX-DOS), in package/wings-of-fury-msx2plus-<version>/ and its
.zip. Build and verify the ROM first (./build.sh projname=mission-flight and
the verifiers).

  python3 tools/package_release.py 0.1.0
"""
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROM = ROOT / 'out/mission-flight/mission-flight.rom'
README = ROOT / 'docs/release/README.txt'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('version')
    args = parser.parse_args()
    rom = ROM.read_bytes()
    if len(rom) != 1024 * 1024:
        raise SystemExit(f'{ROM}: {len(rom)} bytes, expected 1 MiB')
    if rom[:2] != b'AB':
        raise SystemExit(f'{ROM}: no ROM header')
    sha = hashlib.sha256(rom).hexdigest()
    text = README.read_text().format(version=args.version, sha256=sha).replace('\n', '\r\n')
    name = f'wings-of-fury-msx2plus-{args.version}'
    folder = ROOT / 'package' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'WOFMSX2P.ROM').write_bytes(rom)
    (folder / 'README.TXT').write_text(text, newline='')
    archive = ROOT / 'package' / f'{name}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(folder / 'WOFMSX2P.ROM', f'{name}/WOFMSX2P.ROM')
        z.write(folder / 'README.TXT', f'{name}/README.TXT')
    print(archive)
    print('WOFMSX2P.ROM sha256', sha)


if __name__ == '__main__':
    main()
