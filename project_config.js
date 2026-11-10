// External-project layout: game modules live in src/, MSXgl stays in MSXgl/.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

ProjName = "wings";
ProjModules = ["src/main", "src/core/flight", "src/core/aircraft", "src/generated/hellcat_frames"];
LibModules = ["bios", "vdp"];
Machine = "2P";
Target = "ROM_32K";
CustomISR = "VBLANK";
InstallRAMISR = "RAMISR_PAGE3";
// MSXgl reserves C000-C1C3 for the IM2 vector table and ISR automatically.
CheckVersion = true;
DoRun = false;
DoDeploy = false;
CompileOpt += " -Isrc";
GenCompileDB = true;

if (process.platform === "darwin") {
    // Resolve Homebrew's symlink so the SDCC libraries match the compiler.
    const sdcc = fs.realpathSync(execFileSync("which", ["sdcc"], { encoding: "utf8" }).trim());
    SDCCPath = `${path.dirname(path.dirname(sdcc))}/`;
    Compiler = sdcc;
    Linker = sdcc;
    Assembler = `${SDCCPath}bin/sdasz80`;
    MakeLib = `${SDCCPath}bin/sdar`;
    Hex2Bin = `${ProjDir}tools/.build/MSXhex`;
}
