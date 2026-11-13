#pragma once
#include "core.h"
#include "../generated/hellcat_frames.h"
#include "../generated/dashboard_tables.h"
void Dashboard_LoadTables(void);
void Dashboard_Load(void);
u8 Dashboard_Draw(u8 page, u8 area, u8 altitude);
void Dashboard_Waves(u8 page, u16 camera, u8 frame, u8 heave);
void Dashboard_RestoreWaves(u8 page, u8 reset);
const AircraftShape* Dashboard_FarShape(u8 frame);

extern const u8 g_DashboardPalette[32];

void Dashboard_Status(u8 page, u8 weapon, u8 stock, u8 lives);
