#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Default: the game (mission ROM), map a; WINGS_MAP=j for map j.
# "wings" is the original 32 KiB viewer. -n: run the ROM already built,
# without building (./launch.sh -n, WINGS_MAP=j ./launch.sh -n).
build=1
if [ "${1:-}" = -n ]; then build=0; shift; fi
target="${1:-mission-flight}"
case "$target" in
    wings)
        [ "$build" = 0 ] || ./build.sh
        rom=out/wings.rom
        ;;
    hardware-scroll|mission-flight|mission-flight-debug)
        [ "$build" = 0 ] || ./build.sh "projname=$target"
        rom="out/$target/$target.rom"
        # WINGS_MAP=j ./launch.sh: another map (docs/maps.md; j has the ships).
        if [ "$target" = mission-flight ] && [ -n "${WINGS_MAP:-}" ] && [ "$WINGS_MAP" != a ]; then
            rom="out/mission-flight-$WINGS_MAP/mission-flight.rom"
        fi
        ;;
    *)
        echo "Usage: $0 [-n] [mission-flight|mission-flight-debug|wings|hardware-scroll]" >&2
        exit 2
        ;;
esac
if [ ! -f "$rom" ]; then echo "$rom is not built yet: run without -n" >&2; exit 1; fi
if [ "$target" = mission-flight ] || [ "$target" = mission-flight-debug ]; then
    exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -romtype ASCII8 -script tools/pixel_display.tcl
fi
exec openmsx -machine Panasonic_FS-A1WX-512K -cart "$rom" -script tools/pixel_display.tcl
