#include "mission.h"
#include "../generated/mission_surfaces.h"

uint16_t Mission_Query(int16_t x)
{
    uint8_t low = 0, high = MISSION_SURFACE_RUNS, middle;
    if (x < 0 || x >= MISSION_SURFACE_WIDTH) return 0;
    while (low < high)
    {
        middle = low + ((high - low) >> 1);
        if (x < g_MissionSurfaceRuns[middle].end) high = middle;
        else low = middle + 1;
    }
    return g_MissionSurfaceRuns[low].word;
}
