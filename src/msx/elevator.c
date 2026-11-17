#include "elevator.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_SCENE)
#include "../core/flight.h"
#include "../core/carrier.h"
#include "../generated/elevator.h"
#include "terrain_renderer.h"
#include "scenery_load.h"
#include "vdp.h"
#include "vdp_ring.h"
#ifdef WINGS_P1_FLIGHT
static u8 s_Depth[2];
static u16 s_Camera[2];
void Elevator_Load(void) WINGS_BANKED
{
    u8 i,row,width,height,line[32];
    u16 offset=0,address;
    s_Depth[0]=s_Depth[1]=255;
    for (i=0;i<5;++i)
    {
        width=i ? 16 : 32;height=i ? 7 : 40;
        address=g_ElevatorY[i]*128+g_ElevatorX[i]/2;
        for (row=0;row<height;++row)
        {
            Scenery_Read(15,offset,line,width);offset+=width;
            VDP_WriteVRAM(line,address,0,width);address+=128;
        }
    }
}
static void Copy(u8 page,u16 camera,u8 index,u16 origin,u8 y,u8 height,u8 width)
{
    u16 left=(camera+8)&65534u,right=(camera+257)&65534u;
    if (left<origin) left=origin;
    if (right>origin+width) right=origin+width;
    if (left>=right) return;
    /* The close-view pan moves the carrier down; the view ends at row 172. */
    y+=g_PanRows;
    {
        u8 bottom=index ? CARRIER_WELL_BOTTOM+g_PanRows : 172;
        if (bottom>172) bottom=172;
        if (y>=bottom) return;
        if (y+height>bottom) height=bottom-y;
    }
    VDP_RING_SET(g_ElevatorX[index]+left-origin, g_ElevatorY[index], (u16)page*256+y, height,
                 index ? VDP_CMD_LMMM + VDP_OP_TIMP : VDP_CMD_HMMM);
    Vdp_RingCopy((u8)left, right-left);
}
void Elevator_Draw(u8 page,u16 camera,u8 depth,u8 cleared) WINGS_BANKED
{
    u16 left=(camera+8)&65534u,right=(camera+257)&65534u;
    u8 i;
    if (left<CARRIER_X-28u) left=CARRIER_X-28u;
    if (right>CARRIER_X+36u) right=CARRIER_X+36u;
    if (left>=right) {s_Depth[page]=255;return;}
    if (!cleared && s_Depth[page]==depth &&
        (s_Camera[page]==camera || (s_Camera[page]>=CARRIER_X-220u && s_Camera[page]<=CARRIER_X-36u && camera>=CARRIER_X-220u && camera<=CARRIER_X-36u)))
    {s_Camera[page]=camera;return;}
    s_Depth[page]=depth;s_Camera[page]=camera;
    g_DirtyRange.left=left;g_DirtyRange.right=right;g_DirtyRange.page=page;
    g_DirtyRange.first=13;g_DirtyRange.last=14;
    Terrain_DirtyOverlay();
    Copy(page,camera,0,CARRIER_X-28u,112,40,64);   /* OVERLAY_TOPS in tools/convert_mission.py */
    for (i=0;i<4;++i)
        Copy(page,camera,i+1,CARRIER_X-28u+(i&1)*32,129+depth+(i>=2 ? 7 : 0),i<2 ? 7 : 6,32);
}
#endif
