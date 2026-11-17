#include "terrain_patch.h"
#include "terrain_renderer.h"
#include "scenery_load.h"
#include "mission_tiles.h"
#include "vdp.h"
#include "vdp_inl.h"
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
        offset = column * 2;   /* the table starts the map's first bank */
        Scenery_Read(TERRAIN_MAP_BANK + (offset >> 13), offset & 8191, g_TerrainMap + column * 2, 2);
    }
    else
    {
        g_TerrainMap[column * 2] = g_TerrainMap[source * 2];
        g_TerrainMap[column * 2 + 1] = g_TerrainMap[source * 2 + 1];
    }
    g_TerrainDirty = 3;
}

/* Repaint map rows first..last of the 33 columns a page shows, from its
 * tile cache (no map decode), at the page's pan: solid tiles merge into one
 * fill per run, a row of one tile is painted once and doubled, atlas tiles
 * copy one by one. For the rows a close-view pan step uncovers. */
/* 1 when all 32 ring slots hold the same valid tile in this row. */
static uint8_t Uniform(const u16* cell, u16* tile)
{
    uint8_t count = 31;
    u16 first = *cell;
    if (first >= TERRAIN_TILE_COUNT) return 0;
    do { cell += TERRAIN_MAP_ROWS; if (*cell != first) return 0; } while (--count);
    *tile = first;
    return 1;
}

void Terrain_RepaintBand(uint8_t page, uint16_t camera, uint8_t first, uint8_t last,
                         uint8_t clip_top, uint8_t clip_bottom) WINGS_BANKED
{
    uint8_t row, count, color, run_color = 0, ring, height, start_ring, skip;
    u16 y, tile, run_x = 0, run_width, source;
    const u16* cell;
    const u16* column0 = g_TerrainCached[page][0];
    camera &= 65528u;
    start_ring = camera & 255;
    for (row = first; row <= last; ++row)
    {
        y = 24 + g_PanRows + row * 8;
        if (y >= 172 || y >= clip_bottom) break;
        height = y + 8 > clip_bottom ? clip_bottom - y : 8;
        skip = 0;   /* tile rows above clip_top */
        if (y < clip_top)
        {
            if (y + height <= clip_top) continue;
            skip = clip_top - y; y = clip_top; height -= skip;
        }
        y += (u16)page * 256;
        ring = start_ring; run_width = 0; count = 33;
        cell = column0 + (u16)(ring >> 3) * TERRAIN_MAP_ROWS + row;
        if (Uniform(column0 + row, &tile))
        {
            /* Open sea: every column shows the same tile. Paint one and
             * double it across the page (5 copies instead of 32). */
            color = TERRAIN_TILE_COLOR(tile);
            if (color != 255) { VDP_CommandHMMV(0, y, 256, height, color * 17); continue; }
            source = Terrain_TileY(tile) + skip;
            VDP_CommandHMMM(g_TileSourceX, source, 0, y, 8, height);
            for (run_width = 8; run_width < 256; run_width <<= 1)
                VDP_CommandHMMM(0, y, run_width, y, run_width, height);
            continue;
        }
        do
        {
            tile = *cell;
            color = tile < TERRAIN_TILE_COUNT ? TERRAIN_TILE_COLOR(tile) : 254;
            if (run_width && (!ring || color != run_color))
            {
                VDP_CommandHMMV(run_x, y, run_width, height, run_color * 17);
                run_width = 0;
            }
            if (color != 254)
            {
                if (color != 255)
                {
                    if (!run_width) { run_x = ring; run_color = color; }
                    run_width += 8;
                }
                else
                {
                    source = Terrain_TileY(tile) + skip;
                    VDP_CommandHMMM(g_TileSourceX, source, ring, y, 8, height);
                }
            }
            ring += 8;
            if (ring) cell += TERRAIN_MAP_ROWS; else cell = column0 + row;
        } while (--count);
        if (run_width) VDP_CommandHMMV(run_x, y, run_width, height, run_color * 17);
    }
}
