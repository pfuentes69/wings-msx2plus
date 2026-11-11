// ./build.sh projname=world-flight
ProjModules = ["src/world_flight", "src/core/world", "src/core/flight",
    "src/core/aircraft", "src/generated/hellcat_frames"];
OutDir = `${ProjDir}out/world-flight/`;
require("fs").mkdirSync(OutDir, { recursive: true });
