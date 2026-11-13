// Renderer/training harness only; release mission-flight has no R/T shortcuts.
const { layoutCheck } = require("./mission-flight.js");
CompileOpt += " -DWINGS_DEBUG_CONTROLS=1";
OutDir = `${ProjDir}out/mission-flight-debug/`;
require("fs").mkdirSync(OutDir, { recursive: true });
PostBuildScripts = layoutCheck();
