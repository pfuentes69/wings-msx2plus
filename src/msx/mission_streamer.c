#include "terrain_renderer.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "system.h"
#include "scenery_load.h"
#include "../generated/mission_tiles.h"
#include "column_ops.h"

u8 g_TerrainFar;
static u8 s_Map[TERRAIN_MAP_BYTES];
/* The tile ids each page shows per ring column, and the map column drawn
 * there (65535: invalid). Shared with the smoke eraser (smoke_draw.c). */
u16 g_TerrainCached[2][32][TERRAIN_MAP_ROWS];
u16 g_TerrainColumns[2][32];
// One extra entry holds a sentinel (65534) that never matches the cache,
// which only holds tile IDs or 65535; Column_Equal stops there.
#define TERRAIN_SENTINEL 65534u
typedef char TerrainSentinelFree[(TERRAIN_TILE_COUNT < TERRAIN_SENTINEL) ? 1 : -1];
static u16 s_Decoded[TERRAIN_MAP_ROWS + 1];

// Scenery_Read restores the resident bank before each upload call.
void Terrain_Load(void)
{
    u16 tile, offset, address, i;
    u8 row, scratch[64], count;
    s_Decoded[TERRAIN_MAP_ROWS] = TERRAIN_SENTINEL;
    for (tile = 0; tile < TERRAIN_TILE_COUNT; ++tile)
    {
        offset = tile * 32;
        address = (g_MissionTileY[tile] - 512) * 128 + g_MissionTileX[tile] / 2;
        for (row = 0; row < 8; ++row)
        {
            Scenery_Read(4 + (offset >> 13), offset & 8191, scratch, 4);
            VDP_WriteVRAM(scratch, address, 1, 4);
            offset += 4; address += 128;
        }
    }
    for (i = 0; i < TERRAIN_MAP_BYTES; i += count)
    {
        count = TERRAIN_MAP_BYTES - i > 64 ? 64 : TERRAIN_MAP_BYTES - i;
        offset = TERRAIN_MAP_OFFSET + i;
        Scenery_Read(4 + (offset >> 13), offset & 8191, s_Map + i, count);
    }
}

void Terrain_LoadEnd(void) {}

void Terrain_InitPage(u8 page)
{
    u8 column, row;
    for (column = 0; column < 32; ++column)
    {
        g_TerrainColumns[page][column] = 65535u;
        for (row = 0; row < TERRAIN_MAP_ROWS; ++row)
            g_TerrainCached[page][column][row] = 0; // VRAM was cleared to the all-sky tile.
    }
}

/* Map columns of open sea (x 5000, between the islands and the carrier),
 * drawn for every column beyond the map's ends: the ocean goes on, as in the
 * original. tests/test_mission.py checks that both are plain sea. */
#define TERRAIN_SEA_COLUMN 625u
#define TERRAIN_FAR_SEA_COLUMN 78u

void Terrain_DrawColumn(u16 world, u8 page)
{
    u8 slot = (world & 255) >> 3;
    u16 column = world >> 3;
    if (g_TerrainFar)
        column = (column < TERRAIN_MAP_COLUMNS - TERRAIN_FAR_COLUMN ? column : TERRAIN_FAR_SEA_COLUMN) + TERRAIN_FAR_COLUMN;
    else if (column >= TERRAIN_FAR_COLUMN) column = TERRAIN_SEA_COLUMN;
    column *= 2;
    u16 offset = s_Map[column] | ((u16)s_Map[column + 1] << 8);
    u16* cached;
    u16* decoded;
    u16 tile, source_y, dest_y = (u16)page * 256 + 24;
    u8 row, count, height, color, i;
    if (g_TerrainColumns[page][slot] == offset) return;
    g_TerrainColumns[page][slot] = offset;
    // All runs/offsets are bounded and round-trip checked during generation.
    Column_Decode(s_Map + offset, s_Decoded);
    cached = g_TerrainCached[page][slot];
    decoded = s_Decoded;
#ifndef WINGS_TERRAIN_C
    /* Hand-written Z80 (column_ops.c): SDCC's version of the loop below cost
     * ~900 T-states per tile run before the VDP setup. */
    g_ColumnX = world & 255; g_ColumnY = dest_y;
    Column_Runs(cached, decoded);
    (void)row; (void)count; (void)height; (void)color; (void)i; (void)tile; (void)source_y;
#else
    row = 0;
    for (;;)
    {
        count = Column_Equal(cached, decoded); // unchanged rows; stops at the sentinel
        row += count;
        if (row >= TERRAIN_MAP_ROWS) break;
        cached += count;
        decoded += count;
        dest_y += count * 8;
        tile = *decoded;
        count = 1;
        color = g_MissionTileColors[tile];
        if (color != 255)
        {
            while (row + count < TERRAIN_MAP_ROWS && decoded[count] == tile) ++count;
        }
        else
        {
            // Consecutive IDs are stacked vertically within an atlas column.
            while (row + count < TERRAIN_MAP_ROWS && count < g_MissionTileLimit[tile] &&
                   decoded[count] == tile + count) ++count;
        }
        height = count * 8;
        if (dest_y % 256 + height > 172) height = 172 - dest_y % 256;
        if (color != 255)
            VDP_CommandHMMV(world & 255, dest_y, 8, height, color * 17);
        else
        {
            source_y = g_MissionTileY[tile];
            VDP_CommandHMMM(g_MissionTileX[tile], source_y, world & 255, dest_y, 8, height);
        }
        // The next command waits before submission; update the cache in parallel.
        for (i = 0; i < count; ++i) *cached++ = *decoded++;
        row += count;
        dest_y += count * 8;
    }
#endif
}

/* Column_Runs writes these directly. */
typedef char ColumnRunsCommands[(VDP_CMD_HMMM == 0xD0 && VDP_CMD_HMMV == 0xC0) ? 1 : -1];
typedef char ColumnRunsLayout[(sizeof(VDP_Command) == 15 && sizeof(g_VDP_Command.SX) == 2) ? 1 : -1];

void Terrain_DirtyOverlayColumn(u8 page, u16 world, u8 first, u8 last)
{
    u8 slot=(world&255)>>3, count=last-first+1;
    u16* cached=&g_TerrainCached[page][slot][first]; // index once; SDCC re-multiplies per row otherwise
    g_TerrainColumns[page][slot]=65535u;
    do *cached++=65535u; while (--count);
}
