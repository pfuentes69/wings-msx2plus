#include "terrain_renderer.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "system.h"
#include "rom_mapper.h"
#include "../generated/terrain.h"

static u8 s_Map[TERRAIN_MAP_BYTES];
static u8 s_Cached[2][32][4];

// This function and the VDP upload routine must stay outside 6000h..7FFFh.
// The verifier checks their linked addresses before launching the ROM.
void Terrain_Load(void)
{
    u16 tile, offset, address, i;
    u8 row, bank = 255, next;
    const u8* source;
    for (tile = 0; tile < TERRAIN_TILE_COUNT; ++tile)
    {
        offset = tile * 128;
        next = 4 + (offset >> 13);
        if (next != bank) { SET_BANK_SEGMENT(1, next); bank = next; }
        source = (const u8*)(0x6000 + (offset & 8191));
        address = ((tile & 63) >> 4) * 16 * 128 + 180u * 128 + (tile & 15) * 8;
        if (tile >= 64) address += 32768u;
        for (row = 0; row < 16; ++row)
        {
            VDP_WriteVRAM(source, address, 1, 8);
            source += 8;
            address += 128;
        }
    }
    for (i = 0; i < TERRAIN_MAP_BYTES; ++i)
    {
        offset = TERRAIN_MAP_OFFSET + i;
        next = 4 + (offset >> 13);
        if (next != bank) { SET_BANK_SEGMENT(1, next); bank = next; }
        s_Map[i] = *((const u8*)(0x6000 + (offset & 8191)));
    }
    SET_BANK_SEGMENT(1, 1);
}
void Terrain_LoadEnd(void) {}

void Terrain_InitPage(u8 page)
{
    u8 column, row;
    VDP_CommandHMMV(0, (u16)page * 256 + 208, 256, 4, 0x11);
    VDP_CommandWait();
    for (column = 0; column < 32; ++column)
        for (row = 0; row < 4; ++row)
            s_Cached[page][column][row] = 255;
}

void Terrain_DrawColumn(u16 world, u8 page)
{
    u8 slot = (world & 255) >> 3, row, tile;
    const u8* column = s_Map + (world >> 4) * TERRAIN_MAP_ROWS + 1;
    u8* cached = s_Cached[page][slot];
    u16 source_y, dest_y = (u16)page * 256 + 144;
    // The converter enforces uniform sky above and ocean below these four rows.
    for (row = 0; row < 4; ++row, dest_y += 16, ++cached)
    {
        tile = *column++;
        if (*cached == tile) continue;
        source_y = 512 + 180 + (tile & 48);
        if (tile >= 64) source_y += 256;
        VDP_CommandHMMM((tile & 15) * 16 + (world & 8), source_y,
                        world & 255, dest_y, 8, 16);
        VDP_CommandWait();
        *cached = tile;
    }
}
