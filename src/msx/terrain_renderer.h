#pragma once
#include "core.h"
#include "../generated/mission_tiles.h"
void Terrain_Load(void);
void Terrain_LoadEnd(void);
void Terrain_InitPage(u8 page);
void Terrain_DrawColumn(u16 world, u8 page);
/* The map's tiles for the column at world x in the current view (map rows;
 * out holds TERRAIN_MAP_ROWS entries). */
void Terrain_DecodeColumn(u16 world, u16* out);
extern u8 g_TerrainFar;
extern u8 g_PanRows;
extern u8 g_TerrainMap[TERRAIN_MAP_BYTES];

/* Dynamic overlays mark their affected tile rows for repaint on ring reuse.
 * Requires first <= last. */
void Terrain_DirtyOverlayColumn(u8 page, u16 world, u8 first, u8 last);
/* Per page and ring column: the tile ids shown and the map column drawn
 * (65535 when invalid). */
extern u16 g_TerrainCached[2][32][TERRAIN_MAP_ROWS];
extern u16 g_TerrainColumns[2][32];
