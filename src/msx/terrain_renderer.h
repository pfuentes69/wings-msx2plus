#pragma once
#include "core.h"
#include "../generated/mission_tiles.h"
#include "column_ops.h"
void Terrain_Load(void);
void Terrain_LoadEnd(void);
void Terrain_InitPage(u8 page);
void Terrain_DrawColumn(u16 world, u8 page);
/* The map's tiles for the column at world x in the current view (map rows;
 * out holds TERRAIN_MAP_ROWS entries). */
void Terrain_DecodeColumn(u16 world, u16* out);
extern u8 g_TerrainFar;
extern u8 g_PanRows;
/* The first VRAM row overlays (the plane, weapons, smoke) may use on the
 * page being drawn. In the close-view pan the top lines (above the split)
 * show VRAM rows -heave .. fine - 1 at the heave-only scroll, so those rows
 * must stay sky: g_TopClip = fine there, else 0. */
extern u8 g_TopClip;
/* The map's column table: u16 offsets into the map in ROM bank
 * TERRAIN_MAP_BANK (the runs stay in ROM). */
extern u8 g_TerrainMap[TERRAIN_MAP_TABLE_BYTES];

/* Overlay repaint marks: Terrain_DirtyOverlay (column_ops.h). */
/* Per page and ring column: the tile ids shown and the map column drawn
 * (65535 when invalid). */
extern u16 g_TerrainCached[2][32][TERRAIN_MAP_ROWS];
extern u16 g_TerrainColumns[2][32];
