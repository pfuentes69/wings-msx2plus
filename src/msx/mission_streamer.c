#include "terrain_renderer.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "system.h"
#include "scenery_load.h"
#include "../generated/mission_tiles.h"

u8 g_TerrainFar;
static u8 s_Map[TERRAIN_MAP_BYTES];
static u16 s_Cached[2][32][TERRAIN_MAP_ROWS];
static u16 s_ColumnOffsets[2][32];
static u16 s_Decoded[TERRAIN_MAP_ROWS];

// Scenery_Read restores the resident bank before each upload call.
void Terrain_Load(void)
{
    u16 tile, offset, address, i;
    u8 row, scratch[64], count;
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
        s_ColumnOffsets[page][column] = 65535u;
        for (row = 0; row < TERRAIN_MAP_ROWS; ++row)
            s_Cached[page][column][row] = 0; // VRAM was cleared to the all-sky tile.
    }
}

void Terrain_DrawColumn(u16 world, u8 page)
{
    u16 column = ((world >> 3) + (g_TerrainFar ? TERRAIN_FAR_COLUMN : 0)) * 2;
    u16 offset = s_Map[column] | ((u16)s_Map[column + 1] << 8);
    const u8* run = s_Map + offset;
    u16* cached = s_Cached[page][(world & 255) >> 3];
    u16* decoded = s_Decoded;
    u16 tile, source_y, dest_y = (u16)page * 256 + 24;
    u8 row = 0, count, height, color, i;
    if (s_ColumnOffsets[page][(world & 255) >> 3] == offset) return;
    s_ColumnOffsets[page][(world & 255) >> 3] = offset;
    // All runs/offsets are bounded and round-trip checked during generation.
    while (decoded < s_Decoded + TERRAIN_MAP_ROWS)
    {
        count = *run++;
        tile = *run++;
        tile |= (u16)*run++ << 8;
        while (count--)
            *decoded++ = tile;
    }
    row = 0;
    decoded = s_Decoded;
    while (row < TERRAIN_MAP_ROWS)
    {
        tile = *decoded;
        if (*cached == tile)
        {
            ++cached;
            ++decoded;
            ++row;
            dest_y += 8;
            continue;
        }
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
}

void Terrain_DirtyOverlayColumn(u8 page, u16 world, u8 first, u8 last)
{
    u8 slot=(world&255)>>3, row;
    s_ColumnOffsets[page][slot]=65535u;
    for (row=first; row<=last; ++row) s_Cached[page][slot][row]=65535u;
}
