#include "dashboard.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_HUD)
#include "vdp.h"
#include "vdp_inl.h"
#include "scenery_load.h"
#include "../generated/dashboard.h"
#include "cockpit.h"
#include "mission_surfaces.h"
extern u8 g_PanRows;   /* terrain_renderer.h */

static u8 s_Row[128], s_Count, s_Value;
static u8 s_Stream[64], s_StreamPos;
static u16 s_StreamOffset;
// Value currently shown per page for each pre-rendered HUD element.
static u8 s_Hud[2][HUD_ELEMENT_COUNT];
static u8 s_Status[2][3]; /* weapon, stock, lives last shown per page */
u32 g_HudScore[2];        /* score shown per page (the panel shows 0) */
/* The score s_ScoreField (Dashboard_Score) holds: the second page reuses it (composing took
 * most of the redraw's ~20 ms, paid on each page). */
static u32 s_FieldScore;
static u8 s_FieldValid;
// The baked panel shows 30 bombs, three lives, bombs and a new plane's
// gauges (oil frame 16, fuel frame 22, lamps dark). Dial entries hold the
// frame plus HUD_LIT when the lit variant is shown; the _LIT slots are unused.
#define HUD_LIT 32
static const u8 s_HudDefault[HUD_ELEMENT_COUNT] = {3, 0, 3, 0, HUD_NEEDLE_NEW_OIL, HUD_NEEDLE_FULL, 255, 255, 0, 0, 0};

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

/* A page whose dashboard rows were drawn over (a full-screen menu): the
 * panel again, and its values redrawn when next shown. */
void Dashboard_Restore(u8 page) WINGS_BANKED
{
    u8 frame;
    g_Cockpit.shown[page] = 255;
    for (frame = 0; frame < HUD_ELEMENT_COUNT; ++frame) s_Hud[page][frame] = s_HudDefault[frame];
    s_Status[page][0] = s_Status[page][1] = s_Status[page][2] = 255;
    g_HudScore[page] = 0;
    s_FieldValid = 0;
    Input(DASHBOARDPANEL_OFFSET);
    Expand(0, (u16)page * 256 + 172, 256, 40);
}

void Dashboard_Load(void) WINGS_BANKED
{
    u8 page, frame, row, piece;
    u16 x, y, offset = 0;
    Waves_Init();
    s_FieldValid = 0;
    g_Cockpit.generation = 255;   /* RAM is not cleared at boot */
    for (page = 0; page < 2; ++page)
    {
        g_Cockpit.shown[page] = 255;
        for (frame = 0; frame < HUD_ELEMENT_COUNT; ++frame) s_Hud[page][frame] = s_HudDefault[frame];
        s_Status[page][0] = s_Status[page][1] = s_Status[page][2] = 255;
        g_HudScore[page] = 0;
        Input(DASHBOARDPANEL_OFFSET);
        Expand(0, (u16)page * 256 + 172, 256, 40);
    }
    Cockpit_Load();
    Input(FARPLANERLE_OFFSET);
    for (frame = 0; frame < FAR_PLANE_COUNT; ++frame)
        Expand(g_FarShapes[frame].atlas_x, g_FarShapes[frame].atlas_y, 16, 5);
    Input(BOMBRLE_OFFSET);
    for (frame = 0; frame < BOMB_FRAMES; ++frame)
        Expand(g_BombX[frame], g_BombY[frame], 8, BOMB_HEIGHT);
    Input(ARROWRLE_OFFSET);
    Expand(HUD_ARROW0_ATLAS_X, HUD_ARROW0_ATLAS_Y, 16, HUD_ARROW_HEIGHT);
    Expand(HUD_ARROW1_ATLAS_X, HUD_ARROW1_ATLAS_Y, 16, HUD_ARROW_HEIGHT);
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

void Dashboard_CopyPalette(u8* destination) WINGS_BANKED
{
    u8 i;
    for (i = 0; i < 32; ++i) destination[i] = g_DashboardPalette[i];
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

/* Kills (HUD-07, 0xf178): two digits, capped at 99, and an icon a kill up
 * to HUD_KILL_ICONS_MAX (the original shows 14: the MSX panel has room
 * for 8). */
void Dashboard_Kills(u8 page, u8 kills) WINGS_BANKED
{
    /* Show skips an element whose value the page already shows. */
    if (kills > 99) kills = 99;
    Show(page, HUD_KILLS_TENS, kills / 10);
    Show(page, HUD_KILLS_UNITS, kills % 10);
    Show(page, HUD_KILL_ICONS, kills > HUD_KILL_ICONS_MAX ? HUD_KILL_ICONS_MAX : kills);
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
static const u8 s_Blank7[7] = {0, 0, 0, 0, 0, 0, 0};   /* a leading blank: no pixels (in ROM) */
void Dashboard_Score(u8 page, u32 score) WINGS_BANKED
{
    const u8* rows[HUD_SCORE_DIGITS];
    const u8* pa;
    const u8* pb;
    u8* out;
    u8 i, row, lead = 1, a, b;
    u16 address;
    u32 power;
    if (g_HudScore[page] == score) return;
    g_HudScore[page] = score;
    if (s_FieldValid && s_FieldScore == score) goto write;
    s_FieldScore = score; s_FieldValid = 1;
    if (score > 999999UL) score = 999999UL;
    /* Each digit's 7 glyph rows (no multiplications: SDCC calls for them). */
    for (i = 0; i < HUD_SCORE_DIGITS; ++i)
    {
        power = s_Powers[i];
        pa = g_HudDigitRows;
        while (score >= power) { score -= power; pa += 7; }
        if (pa != g_HudDigitRows || i == HUD_SCORE_DIGITS - 1) lead = 0;
        rows[i] = lead ? s_Blank7 : pa;
    }
    /* Digits pair up into byte-aligned 14-pixel cells: the first digit's 6
     * pixels fill 3 bytes, then the gap and the second digit fill 4 (its
     * pixels start on an odd nibble). Each byte is two pixels from s_Pair. */
    for (i = 0; i < HUD_SCORE_DIGITS; i += 2)
    {
        pa = rows[i]; pb = rows[i + 1];
        out = &s_ScoreField[0][0] + (i >> 1) * 7;
        for (row = 0; row < 7; ++row, out += HUD_SCORE_DIGITS * 7 / 2 - 7)
        {
            a = *pa++; b = *pb++;
            *out++ = s_Pair[(a >> 4) & 3];
            *out++ = s_Pair[(a >> 2) & 3];
            *out++ = s_Pair[a & 3];
            *out++ = s_Pair[(b >> 5) & 1];          /* gap, then b's first pixel */
            *out++ = s_Pair[(b >> 3) & 3];
            *out++ = s_Pair[(b >> 1) & 3];
            *out++ = s_Pair[(b << 1) & 2];          /* b's last pixel, then gap */
        }
    }
write:
    address = ((u16)page * 256 + 172 + HUD_SCORE_Y) * 128 + HUD_SCORE_X / 2;
    for (row = 0; row < 7; ++row, address += 128)
        VDP_WriteVRAM(s_ScoreField[row], address, 0, HUD_SCORE_DIGITS * 7 / 2);
}
typedef char DashboardScorePairs[(HUD_SCORE_DIGITS % 2 == 0) ? 1 : -1];
