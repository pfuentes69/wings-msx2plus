#pragma once

// Build target and machine are supplied by project_config.js through MSXgl.
// Other options currently use the library's config_default.h defaults.
#define BIOS_CALL_MAINROM BIOS_CALL_DIRECT
#define BIOS_CALL_SUBROM BIOS_CALL_INTERSLOT
#define BIOS_CALL_DISKROM BIOS_CALL_INTERSLOT
#define BIOS_USE_VDP TRUE
