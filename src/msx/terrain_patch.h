#ifndef WINGS_TERRAIN_PATCH_H
#define WINGS_TERRAIN_PATCH_H
#include <stdint.h>
#include "banking.h"

/* Pages whose visible terrain must be redrawn (bit per page): set when a
 * map column changes under the camera. */
extern uint8_t g_TerrainDirty;
/* Banked (segment 23). Show map column source in place of column; source ==
 * column restores the original from ROM. */
void Terrain_Remap(uint16_t column, uint16_t source) WINGS_BANKED;
/* Repaint tile rows first..last of the visible columns from the tile cache. */
/* Only VRAM rows clip_top .. clip_bottom - 1 (of the page) are painted. */
/* Sinking ships' hulls in the close view (docs/ship-sinking.md): world x
 * left..right (inclusive) comes down rows tile rows as columns are decoded
 * (mission_streamer.c, resident); g_SinkActive: any hull lowered. */
#define SINK_HULLS 4
typedef struct SinkHull { uint16_t left, right; uint8_t rows; } SinkHull;
extern SinkHull g_SinkHull[SINK_HULLS];
extern uint8_t g_SinkActive;
/* Banked (segment 30). Point map column at the column record whose offset
 * is the u16 at map byte entry (a sinking stage's distant column). */
void Terrain_RemapEntry(uint16_t column, uint16_t entry) WINGS_BANKED;
void Terrain_RepaintBand(uint8_t page, uint16_t camera, uint8_t first, uint8_t last,
                         uint8_t clip_top, uint8_t clip_bottom) WINGS_BANKED;
#endif
