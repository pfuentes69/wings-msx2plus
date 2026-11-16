#include "dashboard.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)
#include "vdp.h"
#include "vdp_inl.h"
#include "../generated/dashboard_tables.h"
#include "../generated/mission_surfaces.h"
#include "wave_band.h"
extern u8 g_PanRows;   /* terrain_renderer.h */

/* The animated wave strip (rows 161..171), banked apart from the rest of
 * the dashboard (segment 3 is full). */
static u8 s_WaveBackdropValid[2], s_WaveHeave[2];
/* Open sea: the view lies left of s_SeaLeft or right of s_SeaRight, where
 * every band covers it; the strip's rows. */
static u8 s_WaveRows;
static int16_t s_SeaLeft, s_SeaRight;

void Waves_Init(void) WINGS_BANKED
{
    const MissionWaterBand* band = g_MissionWaterBands;
    u8 region;
    s_WaveBackdropValid[0] = s_WaveBackdropValid[1] = 0;
    s_SeaLeft = 32767; s_SeaRight = -32768; s_WaveRows = 0;
    for (region = 0; region < MISSION_WATER_REGIONS; ++region, ++band)
    {
        if (band->row + band->height > s_WaveRows) s_WaveRows = band->row + band->height;
        if (!band->start && (int16_t)band->end < s_SeaLeft) s_SeaLeft = (int16_t)band->end;
        if (band->end >= MISSION_SURFACE_WIDTH && (int16_t)band->start > s_SeaRight) s_SeaRight = (int16_t)band->start;
    }
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

/* One band through the Z80 band loop (src/msx/wave_band.c). */
static void DrawWaterBand(u8 page, u16 source_x, u16 source_y,
                          u16 start, u16 end, u8 row, u8 height, u8 frame)
{
    WaveBand* b = &g_WaveBand;
    u8 piece = frame >> 2;
    b->source_x = source_x; b->source_y = source_y;
    b->special = (frame & 3) == 3;
    if (b->special) { b->tail_x = g_WaveTailX[piece]; b->tail_y = g_WaveTailY[piece] - 9; }
    b->start = start; b->end = end;
    b->dy = (u16)page * 256 + 161 - s_WaveHeave[page];
    b->row = row; b->height = height;
    Waves_DrawBand();
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
    /* Panned a tile row or more, the wave strip (rows 161..171) is below
     * the view (docs/altitude-view.md). */
    if (g_PanRows) { s_WaveBackdropValid[page] = 0; return; }
    if (heave)
        VDP_CommandHMMM(0, (u16)page * 256 + 159, 0, g_WaveBackdropY[page], 256, 4);
    else
        VDP_CommandHMMM(0, (u16)page * 256 + 161, 0, g_WaveBackdropY[page] + 2, 256, 2);
    s_WaveBackdropValid[page] = 1;
    source_x = frame >= 4 && frame < 8 ? 144 : 48;
    source_y = 212 + (frame & 3) * 11 + (frame >= 8 ? 256 : 0);
    /* Where every band covers the view (open sea, the carrier) they merge
     * into the same two groups: skip the band walk (~13,000 T-states). */
    if (visible_left >= s_SeaRight || visible_right <= s_SeaLeft)
    {
        DrawWaterBand(page, source_x, source_y, (u16)visible_left, (u16)visible_right, 0, 2, frame);
        DrawWaterBand(page, source_x, source_y, (u16)visible_left, (u16)visible_right, 2, s_WaveRows - 2, frame);
        return;
    }
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
