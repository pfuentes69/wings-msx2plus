#pragma once
#include "core.h"
#include "banking.h"
#include "../generated/hellcat_frames.h"
#include "../generated/dashboard_tables.h"
void Dashboard_LoadTables(void) WINGS_BANKED;
/* The dashboard on pages first..1, and the art it uses; at boot. */
void Dashboard_Load(u8 first) WINGS_BANKED;
/* The wave strip's frames back into VRAM (after "THE END" drew over them). */
void Dashboard_LoadWaves(void) WINGS_BANKED;
void Dashboard_Waves(u8 page, u16 camera, u8 frame, u8 heave) WINGS_BANKED;
void Dashboard_RestoreWaves(u8 page, u8 reset) WINGS_BANKED;
/* waves.c (segment 21): the band layout; no wave backdrop saved yet. */
void Waves_Init(void) WINGS_BANKED;
/* Far-view shapes live in RAM tables; resident callers may use them directly. */
#define Dashboard_FarShape(frame) (&g_FarShapes[g_FarPoseForFrame[(frame)]])

/* The palette constant lives in the banked segment: copy it from there. */
void Dashboard_CopyPalette(u8* destination) WINGS_BANKED;

void Dashboard_Status(u8 page, u8 weapon, u8 stock, u8 lives) WINGS_BANKED;
void Dashboard_Kills(u8 page, u8 kills) WINGS_BANKED;
/* The six-digit score field; redrawn only when the value changes. */
void Dashboard_Score(u8 page, u32 score) WINGS_BANKED;
extern u32 g_HudScore[2];  /* what each page shows */
/* gauges: in {oil frame, fuel frame, lamps (bit 0 oil, bit 1 fuel)} wanted;
 * out: what the page shows (at most one dial changes per call). */
/* hold: redraw nothing this page (a heavy frame); gauges still reports what
 * the page shows. */
void Dashboard_Gauges(u8 page, u8* gauges, u8 hold) WINGS_BANKED;
/* The dashboard's rows on this page again, after a full-screen menu. */
void Dashboard_Restore(u8 page) WINGS_BANKED;
