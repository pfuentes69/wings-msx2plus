#include "terrain_patch.h"
#include "terrain_renderer.h"
#include "scenery_load.h"
#include "../generated/mission_tiles.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_COMBAT)

uint8_t g_TerrainDirty;

/* The map's column table (u16 offsets into the run data) is in RAM:
 * pointing a column at another column's runs swaps its terrain, and the
 * renderer's per-slot offset check redraws it. */
void Terrain_Remap(uint16_t column, uint16_t source) WINGS_BANKED
{
    uint16_t offset;
    if (source == column)
    {
        offset = TERRAIN_MAP_OFFSET + column * 2;
        Scenery_Read(4 + (offset >> 13), offset & 8191, g_TerrainMap + column * 2, 2);
    }
    else
    {
        g_TerrainMap[column * 2] = g_TerrainMap[source * 2];
        g_TerrainMap[column * 2 + 1] = g_TerrainMap[source * 2 + 1];
    }
    g_TerrainDirty = 3;
}
