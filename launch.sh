#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Default: the game (mission ROM). "wings" is the original 32 KiB viewer.
case "${1:-mission-flight}" in
    wings)
        ./build.sh
        rom=out/wings.rom
        ;;
    hardware-scroll|mission-flight|mission-flight-debug)
        ./build.sh "projname=$1"
        rom="out/$1/$1.rom"
        ;;
    *)
        echo "Usage: $0 [mission-flight|mission-flight-debug|wings|hardware-scroll]" >&2
        exit 2
        ;;
esac
if [ "${1:-mission-flight}" = mission-flight ] || [ "${1:-mission-flight}" = mission-flight-debug ]; then
    exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -romtype ASCII8 -script tools/pixel_display.tcl
fi
exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -script tools/pixel_display.tcl
