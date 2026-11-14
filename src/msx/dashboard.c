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
static u8 s_Status[2][3]; /* weapon, stock, lives last shown per page */
u32 g_HudScore[2];        /* score shown per page (the panel shows 0) */
// The baked panel shows 30 bombs, three lives, bombs and a new plane's
// gauges (oil frame 16, fuel frame 22, lamps dark). Dial entries hold the
// frame plus HUD_LIT when the lit variant is shown; the _LIT slots are unused.
#define HUD_LIT 32
static const u8 s_HudDefault[HUD_ELEMENT_COUNT] = {3, 0, 3, 0, HUD_NEEDLE_NEW_OIL, HUD_NEEDLE_FULL, 255, 255};

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
        s_Status[page][0] = s_Status[page][1] = s_Status[page][2] = 255;
        g_HudScore[page] = 0;
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
    /* Texture phase from the signed position, so the waves run on
     * continuously into the sea left of the map (negative x). */
    u16 left, part, seam, position, sx, sy, limit, start_left = (u16)((int16_t)start % 96 + 96) % 96;
    while (height)
    {
        take = height;
        if (special && row < 9 && row + take > 9) take = 9 - row;

        position = start; left = start_left;
        while ((int16_t)(end - position) > 0)
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
    u16 source_x, source_y;
    /* Signed world x: bands that reach either end of the map continue over
     * the open sea beyond it. */
    int16_t left, right, start = 0, end = 0, band_start, band_end;
    int16_t visible_left = (int16_t)((camera + 8) & 65534u);
    int16_t visible_right = (int16_t)((camera + 257) & 65534u);
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
        band_start = band->start ? (int16_t)band->start : -32768;
        band_end = band->end < MISSION_SURFACE_WIDTH ? (int16_t)band->end : 32767;
        left = band_start > visible_left ? band_start : visible_left;
        right = band_end < visible_right ? band_end : visible_right;
        if (left >= right) continue;
        // Away from shore all intervals clip to the same viewport bounds.
        // Merge them before issuing commands; preserve the transparency split.
        if (height && start == left && end == right && row + height == band->row
            && (row < 2) == (band->row < 2))
            height += band->height;
        else
        {
            if (height) DrawWaterBand(page, source_x, source_y, (u16)start, (u16)end, row, height, frame);
            start = left; end = right; row = band->row; height = band->height;
        }
    }
    if (height) DrawWaterBand(page, source_x, source_y, (u16)start, (u16)end, row, height, frame);
}

// Copy one pre-rendered value of a HUD element into the dashboard rows.
// Read the whole variant first (at most two bank reads; Scenery_Read takes up
// to 255 bytes), then write it row by row.
#define HUD_PATCH_MAX 288
static u8 s_Patch[HUD_PATCH_MAX];
static void Patch(u8 page, u8 element, u8 value)
{
    u8 row, bytes = g_HudBytes[element];
    u16 size = g_HudSize[element];
    u16 offset = g_HudOffset[element] + (u16)value * size;
    u16 address = ((u16)page * 256 + 172 + g_HudRow[element]) * 128 + g_HudColumn[element];
    const u8* source = s_Patch;
    if (size > 255)
    {
        Scenery_Read(g_HudBank[element], offset, s_Patch, 255);
        Scenery_Read(g_HudBank[element], offset + 255, s_Patch + 255, (u8)(size - 255));
    }
    else Scenery_Read(g_HudBank[element], offset, s_Patch, (u8)size);
    for (row = 0; row < g_HudHeight[element]; ++row)
    {
        VDP_WriteVRAM(source, address, 0, bytes);
        source += bytes; address += 128;
    }
}

static void Show(u8 page, u8 element, u8 value)
{
    if (s_Hud[page][element] != value) { Patch(page, element, value); s_Hud[page][element] = value; }
}

void Dashboard_Status(u8 page, u8 weapon, u8 stock, u8 lives) WINGS_BANKED
{
    /* Called every render: skip the divisions when nothing changed. */
    if (s_Status[page][0] == weapon && s_Status[page][1] == stock && s_Status[page][2] == lives) return;
    s_Status[page][0] = weapon; s_Status[page][1] = stock; s_Status[page][2] = lives;
    Show(page, HUD_AMMO_TENS, stock / 10);
    Show(page, HUD_AMMO_UNITS, stock % 10);
    Show(page, HUD_LIVES, lives > 9 ? 9 : lives);
    Show(page, HUD_WEAPON, weapon);
}



/* Frames 0..22 are the original needle positions; a lit lamp selects the
 * dial's lit variants (the needle is drawn over the lamp, as in the original).
 * A dial patch costs ~5 ms, so at most one dial changes per rendered page;
 * the needles move one frame per 12.5 Hz tick, so the deferral is invisible.
 * gauges: in = wanted {oil frame, fuel frame, lamps}; out = shown on page. */
static u8 s_GaugeTurn;
static u8 GaugeKey(u8 frame, u8 lit)
{
    if (frame > HUD_NEEDLE_FULL) frame = HUD_NEEDLE_FULL; /* never index past the variants */
    return lit ? frame + HUD_LIT : frame;
}

void Dashboard_Gauges(u8 page, u8* gauges, u8 hold) WINGS_BANKED
{
    u8 oil = GaugeKey(gauges[0], gauges[2] & 1), fuel = GaugeKey(gauges[1], gauges[2] & 2);
    u8 change_oil = !hold && s_Hud[page][HUD_OIL_DIAL] != oil, change_fuel = !hold && s_Hud[page][HUD_FUEL_DIAL] != fuel;
    if (change_oil && change_fuel) { s_GaugeTurn ^= 1; change_oil = s_GaugeTurn; change_fuel = !s_GaugeTurn; }
    if (change_oil)
    {
        Patch(page, oil >= HUD_LIT ? HUD_OIL_DIAL_LIT : HUD_OIL_DIAL, oil & (HUD_LIT - 1));
        s_Hud[page][HUD_OIL_DIAL] = oil;
    }
    if (change_fuel)
    {
        Patch(page, fuel >= HUD_LIT ? HUD_FUEL_DIAL_LIT : HUD_FUEL_DIAL, fuel & (HUD_LIT - 1));
        s_Hud[page][HUD_FUEL_DIAL] = fuel;
    }
    oil = s_Hud[page][HUD_OIL_DIAL]; fuel = s_Hud[page][HUD_FUEL_DIAL];
    gauges[0] = oil & (HUD_LIT - 1); gauges[1] = fuel & (HUD_LIT - 1);
    gauges[2] = (oil >= HUD_LIT ? 1 : 0) | (fuel >= HUD_LIT ? 2 : 0);
}

/* The score: six digits, right-aligned with blank leading zeros, white (15)
 * on the panel's black (11), on a 7-pixel pitch (so neighbours share bytes):
 * the whole 42-pixel field is rebuilt and written when the score changes. */
#define SCORE_BACK 11
#define SCORE_INK 15
static const u32 s_Powers[HUD_SCORE_DIGITS] = {100000UL, 10000UL, 1000UL, 100UL, 10UL, 1UL};
/* Two pixels (bit 1 left, bit 0 right) as one byte. */
static const u8 s_Pair[4] = {
    SCORE_BACK << 4 | SCORE_BACK, SCORE_BACK << 4 | SCORE_INK,
    SCORE_INK << 4 | SCORE_BACK, SCORE_INK << 4 | SCORE_INK};
static u8 s_ScoreField[7][HUD_SCORE_DIGITS * 7 / 2];
void Dashboard_Score(u8 page, u32 score) WINGS_BANKED
{
    u8 digit[HUD_SCORE_DIGITS], i, row, lead = 1;
    u16 address;
    if (g_HudScore[page] == score) return;
    g_HudScore[page] = score;
    if (score > 999999UL) score = 999999UL;
    for (i = 0; i < HUD_SCORE_DIGITS; ++i)
    {
        u8 d = 0;
        while (score >= s_Powers[i]) { score -= s_Powers[i]; ++d; }
        if (d || i == HUD_SCORE_DIGITS - 1) lead = 0;
        digit[i] = lead ? 255 : d;
    }
    /* Digits pair up into byte-aligned 14-pixel cells: the first digit's 6
     * pixels fill 3 bytes, then the gap and the second digit fill 4 (its
     * pixels start on an odd nibble). Each byte is two pixels from s_Pair. */
    for (row = 0; row < 7; ++row)
    {
        u8* out = s_ScoreField[row];
        for (i = 0; i < HUD_SCORE_DIGITS; i += 2)
        {
            u8 a = digit[i] == 255 ? 0 : g_HudDigitRows[digit[i] * 7 + row];
            u8 b = digit[i + 1] == 255 ? 0 : g_HudDigitRows[digit[i + 1] * 7 + row];
            *out++ = s_Pair[(a >> 4) & 3];
            *out++ = s_Pair[(a >> 2) & 3];
            *out++ = s_Pair[a & 3];
            *out++ = s_Pair[(b >> 5) & 1];          /* gap, then b's first pixel */
            *out++ = s_Pair[(b >> 3) & 3];
            *out++ = s_Pair[(b >> 1) & 3];
            *out++ = s_Pair[(b << 1) & 2];          /* b's last pixel, then gap */
        }
    }
    address = ((u16)page * 256 + 172 + HUD_SCORE_Y) * 128 + HUD_SCORE_X / 2;
    for (row = 0; row < 7; ++row, address += 128)
        VDP_WriteVRAM(s_ScoreField[row], address, 0, HUD_SCORE_DIGITS * 7 / 2);
}
typedef char DashboardScorePairs[(HUD_SCORE_DIGITS % 2 == 0) ? 1 : -1];
