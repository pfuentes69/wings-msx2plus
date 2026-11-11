#include "dashboard.h"
#include "vdp.h"
#include "vdp_inl.h"
#include "scenery_load.h"
#include "../generated/dashboard.h"
#include "../generated/mission_surfaces.h"

static u8 s_Row[128], s_Count, s_Value, s_Pilot[2];
static u8 s_WaveBackdropValid[2], s_WaveHeave[2];
static const u8* s_Input;

static void Expand(u16 x, u16 y, u16 width, u8 height)
{
    u8 row, column, bytes = width / 2;
    u16 address = y * 128 + x / 2;
    for (row = 0; row < height; ++row)
    {
        for (column = 0; column < bytes; ++column)
        {
            if (!s_Count) { s_Count = *s_Input++; s_Value = *s_Input++; }
            s_Row[column] = s_Value; --s_Count;
        }
        VDP_WriteVRAM(s_Row, address, y >= 512 ? 1 : 0, bytes);
        address += 128;
    }
}

void Dashboard_Load(void)
{
    u8 page, frame, row, piece;
    u16 x, y, offset = 0;
    for (page = 0; page < 2; ++page)
    {
        s_Pilot[page] = 255;
        s_WaveBackdropValid[page] = 0;
        s_Input = g_DashboardPanel; s_Count = 0;
        Expand(0, (u16)page * 256 + 172, 256, 40);
    }
    s_Input = g_PilotRLE; s_Count = 0;
    for (frame = 0; frame < 24; ++frame)
        Expand(g_PilotX[frame], g_PilotY[frame], 48, 24);
    s_Input = g_FarPlaneRLE; s_Count = 0;
    for (frame = 0; frame < FAR_PLANE_COUNT; ++frame)
        Expand(g_FarShapes[frame].atlas_x, g_FarShapes[frame].atlas_y, 16, 5);
    for (frame = 0; frame < 12; ++frame)
    {
        x = frame >= 4 && frame < 8 ? 144 : 48;
        y = 212 + (frame & 3) * 11 + (frame >= 8 ? 256 : 0);
        for (row = 0; row < 11; ++row)
        {
            Scenery_Read(11, offset, s_Row, 48); offset += 48;
            if ((frame & 3) == 3 && row >= 9)
            {
                piece = frame >> 2;
                VDP_WriteVRAM(s_Row,
                    (g_WaveTailY[piece] + row - 9 - 512) * 128 + g_WaveTailX[piece] / 2, 1, 48);
            }
            else VDP_WriteVRAM(s_Row, y * 128 + x / 2, 0, 48);
            ++y;
        }
    }
}

u8 Dashboard_Draw(u8 page, u8 area, u8 altitude)
{
    u8 profile = area * 8 + (altitude >> 5);
    if (s_Pilot[page] != profile)
    {
        VDP_CommandHMMM(g_PilotX[profile], g_PilotY[profile], 108,
                        (u16)page * 256 + 183, 48, 24);
        s_Pilot[page] = profile;
    }
    return profile;
}

const AircraftShape* Dashboard_FarShape(u8 frame) { return &g_FarShapes[g_FarPoseForFrame[frame]]; }

void Dashboard_RestoreWaves(u8 page, u8 reset)
{
    if (reset) s_WaveBackdropValid[page] = 0;
    else if (s_WaveBackdropValid[page])
        if (s_WaveHeave[page])
            VDP_CommandHMMM(0, g_WaveBackdropY[page], 0, (u16)page * 256 + 159, 256, 4);
        else
            VDP_CommandHMMM(0, g_WaveBackdropY[page] + 2, 0, (u16)page * 256 + 161, 256, 2);
}

static void DrawWaterBand(u8 page, u16 source_x, u16 source_y,
                          u16 start, u16 end, u8 row, u8 height, u8 frame)
{
    u8 take, piece, special = (frame & 3) == 3;
    u16 left, part, seam, position, sx, sy, limit, start_left = start % 96;
    while (height)
    {
        take = height;
        if (special && row < 9 && row + take > 9) take = 9 - row;

        position = start; left = start_left;
        while (position < end)
        {
            sx = source_x + left; sy = source_y + row; limit = 96 - left;
            if (special && row >= 9)
            {
                piece = frame >> 2;
                sx = g_WaveTailX[piece] + left; sy = g_WaveTailY[piece] + row - 9;
            }
            part = end - position; if (part > limit) part = limit;
            seam = 256 - (position & 255); if (part > seam) part = seam;
            if (row < 2)
                VDP_CommandLMMM(sx, sy, position & 255,
                    (u16)page * 256 + 161 + row - s_WaveHeave[page], part, take, VDP_OP_TIMP);
            else if ((position & 1) || part == 1)
            {
                part = 1;
                VDP_CommandLMMM(sx, sy, position & 255,
                    (u16)page * 256 + 161 + row - s_WaveHeave[page], 1, take, VDP_OP_IMP);
            }
            else
            {
                part &= 65534u;
                VDP_CommandHMMM(sx, sy, position & 255,
                    (u16)page * 256 + 161 + row - s_WaveHeave[page], part, take);
            }
            position += part; left += part; if (left == 96) left = 0;
        }
        row += take; height -= take;
    }
}

void Dashboard_Waves(u8 page, u16 camera, u8 frame, u8 heave)
{
    const MissionWaterBand* band = g_MissionWaterBands;
    u8 region, row = 0, height = 0;
    u16 left, right, start = 0, end = 0, source_x, source_y;
    u16 visible_left = (camera + 8) & 65534u;
    u16 visible_right = (camera + 257) & 65534u;
    s_WaveHeave[page] = heave;
    if (heave)
        VDP_CommandHMMM(0, (u16)page * 256 + 159, 0, g_WaveBackdropY[page], 256, 4);
    else
        VDP_CommandHMMM(0, (u16)page * 256 + 161, 0, g_WaveBackdropY[page] + 2, 256, 2);
    s_WaveBackdropValid[page] = 1;
    source_x = frame >= 4 && frame < 8 ? 144 : 48;
    source_y = 212 + (frame & 3) * 11 + (frame >= 8 ? 256 : 0);
    for (region = 0; region < MISSION_WATER_REGIONS; ++region, ++band)
    {
        left = band->start > visible_left ? band->start : visible_left;
        right = band->end < visible_right ? band->end : visible_right;
        if (left >= right) continue;
        // Away from shore all intervals clip to the same viewport bounds.
        // Merge them before issuing commands; preserve the transparency split.
        if (height && start == left && end == right && row + height == band->row
            && (row < 2) == (band->row < 2))
            height += band->height;
        else
        {
            if (height) DrawWaterBand(page, source_x, source_y, start, end, row, height, frame);
            start = left; end = right; row = band->row; height = band->height;
        }
    }
    if (height) DrawWaterBand(page, source_x, source_y, start, end, row, height, frame);
}
