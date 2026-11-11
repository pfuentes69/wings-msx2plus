// Scenery fidelity prototype in a 128 KiB ASCII8 ROM.
const mission = JSON.parse(require("fs").readFileSync(`${ProjDir}assets_msx/mission_a/manifest.json`, "utf8"));
ProjModules = ["src/msx/scenery_load", "src/world_flight", "src/msx/mission_streamer", "src/core/world", "src/core/flight", "src/core/aircraft",
    "src/msx/dashboard", "src/msx/ship", "src/core/mission", "src/generated/mission_surfaces", "src/generated/hellcat_frames", "src/generated/mission_tiles"];
Target = "ROM_ASCII8";
CustomISR = "VHBLANK";
ROMSize = 128;
ROMMainSegments = 4;
AddROMSignature = true;
LibModules = ["bios", "vdp", "input"];
CompileOpt += ` -DTILE_TERRAIN -DMISSION_TERRAIN -DWINGS_PRESENT_TICKS=8 -DWINGS_FLIGHT_MAX_Y=1200u -DWINGS_FLIGHT_START_Y=1108u -DWINGS_WORLD_WIDTH=${mission.source_width}u -DWINGS_WORLD_START=${mission.reset_x}u`;
OutDir = `${ProjDir}out/mission-flight/`;
require("fs").mkdirSync(OutDir, { recursive: true });
RawFiles = mission.mapper_banks.map(bank => ({ offset: bank * 8192, file: `assets_msx/mission_a/bank_${bank}.bin` }));

for (let bank = 8; bank <= 10; ++bank) RawFiles.push({ offset: bank * 8192, file: `assets_msx/hellcat/mission_bank_${bank}.bin` });

RawFiles.push({ offset: 11 * 8192, file: "assets_msx/dashboard/waves.sc5" });
