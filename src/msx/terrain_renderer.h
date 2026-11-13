#pragma once
#include "core.h"
void Terrain_Load(void);
void Terrain_LoadEnd(void);
void Terrain_InitPage(u8 page);
void Terrain_DrawColumn(u16 world, u8 page);
extern u8 g_TerrainFar;

/* Dynamic overlays mark their affected tile rows for repaint on ring reuse. */
void Terrain_DirtyOverlayColumn(u8 page, u16 world, u8 first, u8 last);
