// Independent renderer experiment; ./build.sh projname=hardware-scroll
ProjModules = ["src/hardware_scroll"];
OutDir = `${ProjDir}out/hardware-scroll/`;
require("fs").mkdirSync(OutDir, { recursive: true });
