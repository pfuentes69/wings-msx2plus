#include "ship.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/ship.h"

u8 g_ShipHeave, g_ShipFrame;
static u8 s_BobTick, s_BobPhase, s_FlagTick;

void Ship_Load(void)
{
    u8 piece, row, column, count = 0, value = 0, buffer[8];
    const u8* input = g_ShipRLE;
    u16 address;
    g_ShipHeave = g_ShipFrame = s_BobTick = s_BobPhase = s_FlagTick = 0;
    for (piece = 0; piece < 24; ++piece)
    {
        address = (g_ShipY[piece] - 512) * 128 + g_ShipX[piece] / 2;
        for (row = 0; row < 14; ++row)
        {
            for (column = 0; column < 8; ++column)
            {
                if (!count) { count = *input++; value = *input++; }
                buffer[column] = value; --count;
            }
            VDP_WriteVRAM(buffer, address, 1, 8); address += 128;
        }
    }
}

void Ship_Advance(u8 ticks)
{
    s_FlagTick += ticks;
    while (s_FlagTick >= 30) { s_FlagTick -= 30; g_ShipFrame = (g_ShipFrame + 1) & 3; }
    s_BobTick += ticks;
    if (s_BobTick >= 45)
    {
        s_BobTick -= 45; s_BobPhase = (s_BobPhase + 1) & 3;
        g_ShipHeave = s_BobPhase == 3 ? 1 : s_BobPhase;
    }
}

void Ship_Draw(u8 page, u16 camera)
{
    u8 piece, index;
    u16 left, right, origin, sx, width, part, ring;
    if (camera + 256 <= 6906 || camera >= 6938) return;
    for (piece = 0; piece < 6; ++piece)
    {
        origin = 6906 + (piece & 1) * 16;
        left = (camera + 8) & 65534u; if (left < origin) left = origin;
        right = (camera + 257) & 65534u; if (right > origin + 16) right = origin + 16;
        if (left >= right) continue;
        index = g_ShipFrame * 6 + piece;
        sx = g_ShipX[index] + left - origin;
        width = right - left; ring = left & 255;
        while (width)
        {
            part = width; if (part > 256 - ring) part = 256 - ring;
            VDP_CommandHMMM(sx, g_ShipY[index], ring,
                (u16)page * 256 + 46 + (piece >> 1) * 14, part, 14);
            sx += part; width -= part; ring = 0;
        }
    }
}
