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
#endif
