#include "step_batch.h"
#include "../core/world.h"
#include "../core/combat.h"
#include "../core/engine.h"
WINGS_CODE_SEGMENT(WINGS_SEGMENT_FLIGHT)

/* The step loop's state (world_flight.c). */
extern WorldState s_World;
extern uint8_t s_EngineSteps, s_AnimTick, s_ContactBottom, s_ContactSurface;
extern CombatState g_Combat;

/* The step loop's contact gate: at y the plane may touch the surface (the
 * exact, banked check then runs). */
static uint8_t MayTouch(FlightVertical y)
{
    int16_t base = (int16_t)WINGS_FLIGHT_MAX_Y - (int16_t)(y >> 8) - s_ContactBottom;
    return base < (int16_t)s_ContactSurface + 1 || base <= 0;
}

uint8_t Step_Batch(uint8_t left, uint8_t weapons) WINGS_BANKED
{
    FlightState* f = &s_World.flight;
    uint8_t c = f->step, n;
    if (!c) return 0;
    n = FLIGHT_TICK_STEPS - c;
    if (n > left) n = left;
    if (n > (uint8_t)(ENGINE_TICK_STEPS - 1 - s_EngineSteps)) n = ENGINE_TICK_STEPS - 1 - s_EngineSteps;
    if (n > (uint8_t)(11 - s_AnimTick)) n = 11 - s_AnimTick;
    if (Combat_Required(&g_Combat, weapons) && n > (uint8_t)(5 - g_Combat.phase)) n = 5 - g_Combat.phase;
    if (n < 2) return 0;
    /* Each step moves at most |vy| + 1 Q8 units, and the gate only opens
     * lower down: if the lowest the run could reach is clear, all of it is. */
    if (!FLIGHT_ON_DECK(f))
    {
        uint16_t v = (uint16_t)(f->vy < 0 ? -f->vy : f->vy) + 1, reach = 0;
        uint8_t k = n;
        do reach += v; while (--k);
        if (MayTouch(f->y + reach)) return 0;
    }
    Flight_StepMany(f, &s_World.x, n);
    s_EngineSteps += n; s_AnimTick += n;
    /* The weapon clock (Combat_Tick) runs on; with nothing to advance, its
     * ticks do nothing. */
    c = g_Combat.phase + n;
    while (c >= 6) c -= 6;
    g_Combat.phase = c;
    return n;
}
