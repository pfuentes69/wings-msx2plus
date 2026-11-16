#include "ship.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)
#include "vdp.h"
#include "vdp_inl.h"
#include "vdp_ring.h"
#include "../generated/ship.h"
#include "../core/flight.h"
#include "../core/carrier.h"
#ifdef WINGS_P1_FLIGHT
extern CarrierState g_Carrier;
#endif
#include "scenery_load.h"
#include "terrain_renderer.h"

u8 g_ShipHeave, g_ShipFrame;
/* Heave step: one pixel every 90 simulation ticks (0.6 s), a full 0,1,2,1
 * cycle in 2.4 s. Halved from 45 ticks on the user's comparison with the
 * original (2026-11-14); the original's own timing is not recovered. */
#define SHIP_BOB_TICKS 90
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
    if (s_BobTick >= SHIP_BOB_TICKS)
    {
        s_BobTick -= SHIP_BOB_TICKS; s_BobPhase = (s_BobPhase + 1) & 3;
        g_ShipHeave = s_BobPhase == 3 ? 1 : s_BobPhase;
    }
}

/* Positions and rows: OVERLAY_TOPS in tools/convert_mission.py. */
void Ship_Draw(u8 page, u16 camera) WINGS_BANKED
{
    u8 piece, index;
    u16 left, right, origin;
    if (camera + 256 <= 6906 || camera >= 6938) return;
    for (piece = 0; piece < 6; ++piece)
    {
        origin = 6906 + (piece & 1) * 16;
        left = (camera + 8) & 65534u; if (left < origin) left = origin;
        right = (camera + 257) & 65534u; if (right > origin + 16) right = origin + 16;
        if (left >= right) continue;
        index = g_ShipFrame * 6 + piece;
        VDP_RING_SET(g_ShipX[index] + left - origin, g_ShipY[index],
                     (u16)page * 256 + 46 + g_PanRows + (piece >> 1) * 14, 14, VDP_CMD_HMMM);
        Vdp_RingCopy((u8)left, right - left);
    }
}

#ifdef WINGS_P1_FLIGHT
/* Each frame contains the source figure over its exact static deck backdrop.
 * Replacing the whole rectangle erases old arms before the plane is composited. */
static u16 s_CrewCamera[2] = {65535u, 65535u};
void Ship_DrawCrew(u8 page, u16 camera, u8 cleared) WINGS_BANKED
{
    u8 piece, index, mark, y, height;
    u16 origin, left, right, column;
    /* Terrain columns are only redrawn when the camera moves or the page is
     * rebuilt, so the overlay rows need re-marking only then (per page). */
    mark = cleared || s_CrewCamera[page] != camera;
    s_CrewCamera[page] = camera;
    for (piece=0; piece<4; ++piece)
    {
        origin = piece < 2 ? 6958 : 7334;
        left = (camera+8)&65534u; if (left < origin) left=origin;
        right = (camera+257)&65534u; if (right > origin+22) right=origin+22;
        if (left>=right) continue;
        if (mark)
            for (column=left&65528u; column<right; column+=8)
                Terrain_DirtyOverlayColumn(page,column,11,13);
        index = (piece < 2 ? 0 : 16) + g_CrewFrame*2 + (piece&1);
        if (piece<2 && g_Carrier.stage!=CARRIER_DECK) index=CREW_IDLE_PIECE+(piece&1);
        /* Panned down, the lower figure rows leave the view at row 172.
         * Positions and rows: OVERLAY_TOPS in tools/convert_mission.py. */
        y=116+g_PanRows+(piece&1)*7; height=7;
        if (y>=172) continue;
        if (y+height>172) height=172-y;
        VDP_RING_SET(g_CrewX[index] + left-origin, g_CrewY[index], (u16)page*256+y, height, VDP_CMD_HMMM);
        Vdp_RingCopy((u8)left, right-left);
    }
}
#endif
