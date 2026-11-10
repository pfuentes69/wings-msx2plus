#pragma once

// Build target and machine are supplied by project_config.js through MSXgl.
// Other options currently use the library's config_default.h defaults.
#define BIOS_CALL_MAINROM BIOS_CALL_DIRECT
#define BIOS_CALL_SUBROM BIOS_CALL_INTERSLOT
#define BIOS_CALL_DISKROM BIOS_CALL_INTERSLOT
#define BIOS_USE_VDP TRUE

// SCREEN 5 only; use the BIOS VBlank ISR and its register mirrors.
#define VDP_USE_MODE_G4 TRUE
#define VDP_USE_PALETTE16 TRUE
#define VDP_USE_SPRITE FALSE
#define VDP_USE_COMMAND FALSE
#define VDP_VRAM_ADDR VDP_VRAM_ADDR_17
#define VDP_INIT_50HZ VDP_INIT_AUTO
