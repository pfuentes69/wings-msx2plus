#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Default: the game (mission ROM). "wings" is the original 32 KiB viewer.
target="${1:-mission-flight}"
case "$target" in
    wings)
        ./build.sh
        rom=out/wings.rom
        ;;
    hardware-scroll|mission-flight|mission-flight-debug)
        ./build.sh "projname=$target"
        rom="out/$target/$target.rom"
        ;;
    *)
        echo "Usage: $0 [mission-flight|mission-flight-debug|wings|hardware-scroll]" >&2
        exit 2
        ;;
esac
if [ "$target" = mission-flight ] || [ "$target" = mission-flight-debug ]; then
    exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -romtype ASCII8 -script tools/pixel_display.tcl
fi
exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -script tools/pixel_display.tcl
