#include "dashboard.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_HUD)
#include "vdp.h"
#include "vdp_inl.h"
#include "scenery_load.h"
#include "../generated/dashboard.h"
#include "../generated/mission_surfaces.h"

static u8 s_Row[128], s_Count, s_Value, s_Pilot[2];
static u8 s_WaveBackdropValid[2], s_WaveHeave[2];
static u8 s_Stream[64], s_StreamPos;
static u16 s_StreamOffset;
// Value currently shown per page for each pre-rendered HUD element.
static u8 s_Hud[2][HUD_ELEMENT_COUNT];
// The baked panel shows 30 bombs, three lives, bombs, full gauges, lamps off.
static const u8 s_HudDefault[HUD_ELEMENT_COUNT] = {3, 0, 3, 0, 0, 0, HUD_NEEDLE_FULL, HUD_NEEDLE_FULL};

static void Input(u16 offset)
{
    s_StreamOffset = offset; s_StreamPos = 64; s_Count = 0;
}

static u8 Next(void)
{
    if (s_StreamPos == 64)
    {
        Scenery_Read(DASHBOARD_BANK, s_StreamOffset, s_Stream, 64);
        s_StreamOffset += 64; s_StreamPos = 0;
    }
    return s_Stream[s_StreamPos++];
}

static void Expand(u16 x, u16 y, u16 width, u8 height)
{
    u8 row, column, bytes = width / 2;
    u16 address = y * 128 + x / 2;
    for (row = 0; row < height; ++row)
    {
        for (column = 0; column < bytes; ++column)
        {
            if (!s_Count) { s_Count = Next(); s_Value = Next(); }
            s_Row[column] = s_Value; --s_Count;
        }
        VDP_WriteVRAM(s_Row, address, y >= 512 ? 1 : 0, bytes);
        address += 128;
    }
}

void Dashboard_LoadTables(void) WINGS_BANKED
{
    u16 offset;
    for (offset=0;offset<DASHBOARD_TABLE_BYTES;offset+=64)
        Scenery_Read(7,offset,g_DashboardTables+offset,64);
    for (offset=0;offset<512;offset+=128)
        Scenery_Read(7,AIRCRAFT_TABLE_OFFSET+offset,(u8*)g_AircraftShapes+offset,128);
    Scenery_Read(7,AIRCRAFT_TABLE_OFFSET+512,(u8*)g_AircraftShapes+512,sizeof(g_AircraftShapes)-512);
}

void Dashboard_Load(void) WINGS_BANKED
{
    u8 page, frame, row, piece;
    u16 x, y, offset = 0;
    for (page = 0; page < 2; ++page)
    {
        s_Pilot[page] = 255;
        for (frame = 0; frame < HUD_ELEMENT_COUNT; ++frame) s_Hud[page][frame] = s_HudDefault[frame];
        s_WaveBackdropValid[page] = 0;
        Input(DASHBOARDPANEL_OFFSET);
        Expand(0, (u16)page * 256 + 172, 256, 40);
    }
    Input(PILOTRLE_OFFSET);
    for (frame = 0; frame < 24; ++frame)
        Expand(g_PilotX[frame], g_PilotY[frame], 48, 24);
    Input(FARPLANERLE_OFFSET);
    for (frame = 0; frame < FAR_PLANE_COUNT; ++frame)
        Expand(g_FarShapes[frame].atlas_x, g_FarShapes[frame].atlas_y, 16, 5);
    Input(BOMBRLE_OFFSET);
    for (frame = 0; frame < 5; ++frame)
        Expand(g_BombX[frame], g_BombY[frame], 8, 8);
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

u8 Dashboard_Draw(u8 page, u8 area, u8 altitude) WINGS_BANKED
{
    u8 profile = area * 8 + (altitude >> 5);
    if (s_Pilot[page] != profile)
    {
        VDP_CommandHMMM(g_PilotX[profile], g_PilotY[profile], HUD_PILOT_X,
                        (u16)page * 256 + 172 + HUD_PILOT_Y, HUD_PILOT_WIDTH, 24);
        s_Pilot[page] = profile;
    }
    return profile;
}

void Dashboard_CopyPalette(u8* destination) WINGS_BANKED
{
    u8 i;
    for (i = 0; i < 32; ++i) destination[i] = g_DashboardPalette[i];
}

void Dashboard_RestoreWaves(u8 page, u8 reset) WINGS_BANKED
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

void Dashboard_Waves(u8 page, u16 camera, u8 frame, u8 heave) WINGS_BANKED
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

// Copy one pre-rendered value of a HUD element into the dashboard rows.
static void Patch(u8 page, u8 element, u8 value)
{
    u8 row, bytes = g_HudBytes[element];
    u16 offset = g_HudOffset[element] + (u16)value * g_HudSize[element];
    u16 address = ((u16)page * 256 + 172 + g_HudRow[element]) * 128 + g_HudColumn[element];
    for (row = 0; row < g_HudHeight[element]; ++row)
    {
        Scenery_Read(g_HudBank[element], offset, s_Row, bytes);
        VDP_WriteVRAM(s_Row, address, 0, bytes);
        offset += bytes; address += 128;
    }
    s_Hud[page][element] = value;
}

static void Show(u8 page, u8 element, u8 value)
{
    if (s_Hud[page][element] != value) Patch(page, element, value);
}

void Dashboard_Status(u8 page, u8 weapon, u8 stock, u8 lives) WINGS_BANKED
{
    Show(page, HUD_AMMO_TENS, stock / 10);
    Show(page, HUD_AMMO_UNITS, stock % 10);
    Show(page, HUD_LIVES, lives > 9 ? 9 : lives);
    Show(page, HUD_WEAPON, weapon);
}

/* Levels are 0..255; the 23 original needle frames sweep empty..full. A lamp
 * is lit only at or below the critical frame, where no needle overlaps it.
 * Redrawing a dial restores its lamp to off, so the lamp follows the dial. */
static void Gauge(u8 page, u8 dial, u8 lamp, u8 level, u8 lit)
{
    u8 frame = ((u16)level * (HUD_NEEDLE_FULL + 1)) >> 8;
    if (s_Hud[page][dial] != frame)
    {
        Patch(page, dial, frame);
        s_Hud[page][lamp] = 0;
    }
    Show(page, lamp, lit && frame <= HUD_LAMP_CRITICAL_FRAME);
}

void Dashboard_Gauges(u8 page, u8 oil, u8 fuel, u8 lamps) WINGS_BANKED
{
    Gauge(page, HUD_OIL_DIAL, HUD_OIL_LAMP, oil, lamps & 1);
    Gauge(page, HUD_FUEL_DIAL, HUD_FUEL_LAMP, fuel, lamps & 2);
}
