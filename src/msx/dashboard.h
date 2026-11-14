#pragma once
#include "core.h"
#include "banking.h"
#include "../generated/hellcat_frames.h"
#include "../generated/dashboard_tables.h"
void Dashboard_LoadTables(void) WINGS_BANKED;
void Dashboard_Load(void) WINGS_BANKED;
u8 Dashboard_Draw(u8 page, u8 area, u8 altitude) WINGS_BANKED;
void Dashboard_Waves(u8 page, u16 camera, u8 frame, u8 heave) WINGS_BANKED;
void Dashboard_RestoreWaves(u8 page, u8 reset) WINGS_BANKED;
/* Far-view shapes live in RAM tables; resident callers may use them directly. */
#define Dashboard_FarShape(frame) (&g_FarShapes[g_FarPoseForFrame[(frame)]])

/* The palette constant lives in the banked segment: copy it from there. */
void Dashboard_CopyPalette(u8* destination) WINGS_BANKED;

void Dashboard_Status(u8 page, u8 weapon, u8 stock, u8 lives) WINGS_BANKED;
/* Oil/fuel levels 0..255; lamps: bit 0 oil, bit 1 fuel warning lit this frame. */
void Dashboard_Gauges(u8 page, u8 oil, u8 fuel, u8 lamps) WINGS_BANKED;
