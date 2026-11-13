#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
case "${1:-wings}" in
    wings)
        ./build.sh
        rom=out/wings.rom
        ;;
    world-flight|hardware-scroll|tile-flight|mission-flight|mission-flight-debug)
        ./build.sh "projname=$1"
        rom="out/$1/$1.rom"
        ;;
    *)
        echo "Usage: $0 [wings|world-flight|hardware-scroll|tile-flight|mission-flight|mission-flight-debug]" >&2
        exit 2
        ;;
esac
if [ "${1:-wings}" = tile-flight ] || [ "${1:-wings}" = mission-flight ] || [ "${1:-wings}" = mission-flight-debug ]; then
    exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -romtype ASCII8 -script tools/pixel_display.tcl
fi
exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -script tools/pixel_display.tcl
