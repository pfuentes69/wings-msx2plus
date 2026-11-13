#include "ship.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/ship.h"
#include "../core/flight.h"
#include "../core/carrier.h"
#ifdef WINGS_P1_FLIGHT
extern CarrierState g_Carrier;
#endif
#include "scenery_load.h"
#include "terrain_renderer.h"

u8 g_ShipHeave, g_ShipFrame;
static u8 s_BobTick, s_BobPhase, s_FlagTick;
#ifdef WINGS_P1_FLIGHT
u8 g_CrewFrame;
static u8 s_CrewTick;
#endif

void Ship_Load(void) WINGS_BANKED
{
    u8 piece, row, buffer[8];
    u16 address;
    g_ShipHeave = g_ShipFrame = s_BobTick = s_BobPhase = s_FlagTick = 0;
    for (piece = 0; piece < 24; ++piece)
    {
        address = (g_ShipY[piece] - 512) * 128 + g_ShipX[piece] / 2;
        for (row = 0; row < 14; ++row)
        {
            Scenery_Read(13, SHIP_PIXELS_OFFSET+(u16)piece*112+row*8,buffer,8);
            VDP_WriteVRAM(buffer, address, 1, 8); address += 128;
        }
    }
#ifdef WINGS_P1_FLIGHT
    g_CrewFrame = s_CrewTick = 0;
    for (piece = 0; piece < CREW_PIECES; ++piece)
    {
        for (row = 0; row < 7; ++row)
        {
            u8 line[11];
            Scenery_Read(13, (u16)(piece >> 1)*154 + (piece & 1)*77 + row*11, line, 11);
            VDP_WriteVRAM(line, (g_CrewY[piece]-512+row)*128+g_CrewX[piece]/2, 1, 11);
        }
    }
#endif
}

void Ship_Advance(u8 ticks) WINGS_BANKED
{
#ifdef WINGS_P1_FLIGHT
    s_CrewTick += ticks;
    while (s_CrewTick >= 15) { s_CrewTick -= 15; g_CrewFrame = (g_CrewFrame+1)&7; }
#endif
    s_FlagTick += ticks;
    while (s_FlagTick >= 30) { s_FlagTick -= 30; g_ShipFrame = (g_ShipFrame + 1) & 3; }
    s_BobTick += ticks;
    if (s_BobTick >= 45)
    {
        s_BobTick -= 45; s_BobPhase = (s_BobPhase + 1) & 3;
        g_ShipHeave = s_BobPhase == 3 ? 1 : s_BobPhase;
    }
}

void Ship_Draw(u8 page, u16 camera) WINGS_BANKED
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

#ifdef WINGS_P1_FLIGHT
/* Each frame contains the source figure over its exact static deck backdrop.
 * Replacing the whole rectangle erases old arms before the plane is composited. */
void Ship_DrawCrew(u8 page, u16 camera) WINGS_BANKED
{
    u8 piece, index;
    u16 origin, left, right, sx, ring, width, part, column;
    for (piece=0; piece<4; ++piece)
    {
        origin = piece < 2 ? 6958 : 7334;
        left = (camera+8)&65534u; if (left < origin) left=origin;
        right = (camera+257)&65534u; if (right > origin+22) right=origin+22;
        if (left>=right) continue;
        for (column=left&65528u; column<right; column+=8)
            Terrain_DirtyOverlayColumn(page,column,11,13);
        index = (piece < 2 ? 0 : 16) + g_CrewFrame*2 + (piece&1);
        if (piece<2 && g_Carrier.stage!=CARRIER_DECK) index=CREW_IDLE_PIECE+(piece&1);
        sx = g_CrewX[index] + left-origin;
        ring=left&255; width=right-left;
        while (width)
        {
            part=width; if (ring+part>256) part=256-ring;
            VDP_CommandHMMM(sx,g_CrewY[index],ring,(u16)page*256+116+(piece&1)*7,part,7);
            width-=part; sx+=part; ring=0;
        }
    }
}
#endif
