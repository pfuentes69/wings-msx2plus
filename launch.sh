#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
./build.sh
exec openmsx -machine Panasonic_FS-A1WX-512K -cart out/wings.rom
