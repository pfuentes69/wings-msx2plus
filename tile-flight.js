// Original-art tile scene in a 64 KiB ASCII8 ROM; main code remains in banks 0..3.
ProjModules = ["src/world_flight", "src/core/world", "src/core/flight", "src/core/aircraft",
    "src/msx/terrain_renderer", "src/generated/hellcat_frames", "src/generated/terrain"];
Target = "ROM_ASCII8";
ROMSize = 64;
ROMMainSegments = 4;
AddROMSignature = true;
LibModules = ["bios", "vdp", "input"];
CompileOpt += " -DTILE_TERRAIN";
OutDir = `${ProjDir}out/tile-flight/`;
require("fs").mkdirSync(OutDir, { recursive: true });
const terrain = JSON.parse(require("fs").readFileSync(`${ProjDir}assets_msx/terrain/manifest.json`, "utf8"));
RawFiles = terrain.mapper_banks.map(bank => ({ offset: bank * 8192, file: `assets_msx/terrain/bank_${bank}.bin` }));
