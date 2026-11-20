/* For host tests that build the flight model but not the crash
 * (src/core/crash.c): crash modes stand still. */
#include "../../src/core/crash.h"
CrashState g_Crash;
void Crash_Tick(FlightState* flight, uint16_t world)
{
    (void)flight; (void)world;
    g_Crash.dx = g_Crash.dy = 0;
}
