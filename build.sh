#!/bin/sh
set -eu
cd "$(dirname "$0")"

# Prefer the host Node.js; the copied bundle may target a different OS.
if command -v node >/dev/null 2>&1; then
    node_bin=$(command -v node)
else
    node_bin=./MSXgl/tools/build/Node/node
fi

# The upstream build expects this directory even with an external project.
mkdir -p MSXgl/projects

if [ "$(uname -s)" = Darwin ]; then
    mkdir -p tools/.build
    if [ ! -x tools/.build/MSXhex ] ||
       [ MSXgl/tools/MSXtk/src/MSXhex.cpp -nt tools/.build/MSXhex ] ||
       [ MSXgl/tools/MSXtk/src/MSXtk.h -nt tools/.build/MSXhex ]; then
        "${CXX:-c++}" -std=c++17 -I MSXgl/tools/MSXtk/src \
            MSXgl/tools/MSXtk/src/MSXhex.cpp -o tools/.build/MSXhex
    fi
fi

exec "$node_bin" MSXgl/engine/script/js/build.js "$@"
