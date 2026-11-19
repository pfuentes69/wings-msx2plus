// Mission ROM: 512 KiB ASCII8 with banked code; see docs/rom-banking.md.
// WINGS_MAP picks the map (a..o, default a): its converted assets in
// assets_msx/mission_<map>, its C tables in src/generated/map_<map>
// (tools/convert_mission.py --map). Maps other than a build to
// out/mission-flight-<map>/.
const map = process.env.WINGS_MAP || "a";
const mission = JSON.parse(require("fs").readFileSync(`${ProjDir}assets_msx/mission_${map}/manifest.json`, "utf8"));
ProjModules = ["src/msx/scenery_load", "src/msx/banking", "src/msx/vdp_ring", "src/msx/input_sampler", "src/core/controls", "src/core/carrier", "src/world_flight", "src/msx/mission_streamer", "src/msx/column_ops", "src/core/world", "src/core/flight", "src/core/aircraft",
    "src/msx/elevator", "src/msx/dashboard", "src/msx/waves", "src/msx/wave_band", "src/core/combat", "src/core/engine", "src/core/landing", "src/core/flight_model", "src/core/flight_steps", "src/msx/step_batch", "src/msx/rope", "src/core/smoke", "src/msx/smoke_draw", "src/msx/smoke_erase", "src/core/island", "src/core/soldiers", "src/core/ships", "src/core/planes", "src/core/fighters", "src/msx/screens", "src/generated/screens_art", "src/msx/screen_end", "src/generated/screen_end_art", "src/core/rockets", "src/core/rocket_move", "src/msx/message", "src/msx/sound", "src/msx/sound_update", "src/msx/sound_fm", "src/msx/terrain_patch", "src/core/game", "src/msx/menu", "src/msx/weapons", "src/msx/ship", "src/core/mission", `src/generated/map_${map}/mission_surfaces`, "src/generated/hellcat_frames", "src/generated/smoke_frames", "src/generated/smoke_erase_box", "src/generated/font", `src/generated/map_${map}/mission_tiles`];
Target = "ROM_ASCII8";
CustomISR = "VHBLANK";
ROMSize = 512;
// Segments 0..2 stay resident in windows 0..2; window 3 (A000h) is banked code.
ROMMainSegments = 3;
AddROMSignature = true;
LibModules = ["bios", "vdp", "input"];
CompileOpt += ` -DWINGS_BANKED_CODE -DTILE_TERRAIN -DMISSION_TERRAIN -DWINGS_PRESENT_TICKS=8 -DWINGS_FLIGHT_MAX_Y=1200u -DWINGS_FLIGHT_START_Y=1108u -DWINGS_WORLD_WIDTH=${mission.source_width}u -DWINGS_WORLD_START=${mission.reset_x}u -DWINGS_CARRIER_X=${mission.reset_x}u -I${ProjDir}src/generated/map_${map}`;
OutDir = map === "a" ? `${ProjDir}out/mission-flight/` : `${ProjDir}out/mission-flight-${map}/`;
require("fs").mkdirSync(OutDir, { recursive: true });
// The terrain: tile strips from bank 32, the column map from bank 40 (tools/convert_mission.py).
RawFiles = mission.tile_banks.concat(mission.map_banks).map(bank => ({ offset: bank * 8192, file: `assets_msx/mission_${map}/bank_${bank}.bin` }));

const aircraftBytes = JSON.parse(require("fs").readFileSync(`${ProjDir}assets_msx/hellcat/manifest.json`, "utf8")).animation.pixel_bytes;
for (let segment = 0; segment < Math.ceil(aircraftBytes / 8192); ++segment) {
    const bank = [8, 9, 10, 14, 4, 5, 6][segment];   // tools/convert_hellcat.py AIRCRAFT_BANKS
    RawFiles.push({ offset: bank * 8192, file: `assets_msx/hellcat/mission_bank_${bank}.bin` });
}

RawFiles.push({ offset: 7 * 8192, file: "assets_msx/dashboard/bank_7.bin" });

RawFiles.push({ offset: 11 * 8192, file: "assets_msx/dashboard/waves.sc5" });

RawFiles.push({ offset: 12 * 8192, file: "assets_msx/dashboard/bank_12.bin" });
// Pre-rendered HUD values: counters and oil dial in 17, fuel dial in 18,
// lit-lamp dials in 19 (oil) and 20 (fuel).
for (const bank of [17, 18, 19, 20])
    RawFiles.push({ offset: bank * 8192, file: `assets_msx/dashboard/bank_${bank}.bin` });

RawFiles.push({ offset: 13 * 8192, file: "assets_msx/ship/bank_13.bin" });
RawFiles.push({ offset: 15 * 8192, file: "assets_msx/elevator/bank_15.bin" });
// The briefing's frame (tools/convert_screens.py BRIEF_BANKS).
for (const bank of [51, 52])
    RawFiles.push({ offset: bank * 8192, file: `assets_msx/screens/bank_${bank}.bin` });

// Link each banked code segment at (segment << 16) | A000h, as listed in banking.h.
const banking = require("fs").readFileSync(`${ProjDir}src/msx/banking.h`, "utf8");
const codeSegments = [...banking.matchAll(/^#define WINGS_SEGMENT_\w+ (\d+)/gm)].map(m => Number(m[1]));
LinkOpt += codeSegments.map(s => ` -Wl-b_SEG${s}=0x${(s * 0x10000 + 0xA000).toString(16)}`).join("");
const dataBanks = RawFiles.map(raw => raw.offset / 8192);
// Fail the build if code leaves its window or collides with a data bank.
function layoutCheck() {
    return [`python3 "${ProjDir}tools/check_rom_layout.py" "${OutDir}${ProjName}.ihx" ` +
        `--rom-kib ${ROMSize} --code-segments ${codeSegments.join(",")} --data-banks ${dataBanks.join(",")}`];
}
PostBuildScripts = layoutCheck();
module.exports = { layoutCheck };
