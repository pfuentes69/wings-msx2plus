#include "mission.h"
#include "mission_surfaces.h"
#ifndef WINGS_MAP_RECORD   /* the ROM: msx/map_record.c, the runs in the map's bank */

/* The last run found: the plane (or camera) stays in one most frames. */
static uint16_t s_Start = 0, s_End = 0, s_Word = 0;   /* RAM is not cleared at boot */

uint16_t Mission_Query(int16_t x)
{
    uint8_t low = 0, high = MISSION_SURFACE_RUNS, middle;
    if (x < 0 || x >= MISSION_SURFACE_WIDTH) return 0;
    if ((uint16_t)x >= s_Start && (uint16_t)x < s_End) return s_Word;
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if (x < g_MissionSurfaceRuns[middle].end) high = middle;
        else low = middle + 1;
    }
    s_Start = low ? g_MissionSurfaceRuns[low - 1].end : 0;
    s_End = g_MissionSurfaceRuns[low].end;
    return s_Word = g_MissionSurfaceRuns[low].word;
}

#endif
